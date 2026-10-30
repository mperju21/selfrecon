"""Block real-looking personal identifiers and private paths from the repository.

Used by the pre-commit hooks (staged files, the commit message, the private-path check)
and by `tests/static/test_no_identifiers.py` (over every file git would track).

Allowed:
- emails on reserved domains: example.com/.org/.net (and subdomains), *.example, *.invalid, *.test
- fictional NANP numbers +1 NXX 555-0100..0199
- CNP-shaped numbers whose first digit is 3 or 4 (born 1800-1899)
- exact values listed in `.identifier-allowlist`, each with a `# reason`
- one kind on one line, marked by a comment `identifier-allow[<kind>]: <reason>`
  (kind: email, phone or cnp; comment starts with #, // or <!--)

Lines are URL- and HTML-decoded before matching, so `%40`, `&#64;` and `%2B` don't hide
anything. Findings are printed masked, so a real identifier is not echoed in full.

Usage:
  check_identifiers.py [FILE ...]            scan files (default: all repo files) + private paths
  check_identifiers.py --skip-private FILE   scan files only
  check_identifiers.py --commit-msg FILE     scan a commit message (git '#' comments ignored)
  check_identifiers.py --private-only        only check that no private file is staged/tracked
"""

from __future__ import annotations

import argparse
import html
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

import phonenumbers
from phonenumbers import Leniency, PhoneNumberFormat, PhoneNumberMatcher

ALLOWLIST_FILE = ".identifier-allowlist"
MAX_FILE_BYTES = 5 * 1024 * 1024
KINDS = ("email", "phone", "cnp")

INLINE_ALLOW = re.compile(
    r"(?:#|//|<!--)\s*identifier-allow\[(?P<kinds>[a-z]+(?:\s*,\s*[a-z]+)*)\]:\s*(?P<reason>\S.{2,})"
)

EMAIL = re.compile(
    r"(?<![\w.%+'-])[\w.%+'-]+@"
    r"(?P<domain>[\w-]+(?:\.[\w-]+)*\.(?:[^\W\d_]{2,}|xn--[A-Za-z0-9-]+))(?![\w-])"
)
RESERVED_EMAIL_DOMAINS = ("example.com", "example.org", "example.net")
RESERVED_EMAIL_TLDS = ("example", "invalid", "test")

# A CNP written plain or grouped with spaces, dots or dashes.
CNP_SHAPE = re.compile(r"(?<!\d)\d(?:[ .-]?\d){12}(?!\d)")
CNP_WEIGHTS = (2, 7, 9, 1, 4, 6, 3, 5, 8, 2, 7, 9)
FAKE_CNP_CENTURY_DIGITS = ("3", "4")

# National formats are only recognised for these regions; international (+, 00) forms
# are recognised for every country. DE and IT are left out on purpose: their national
# plans accept almost any 6-13 digit run, so CNPs and timestamps would match.
PHONE_REGIONS = ("RO", "MD", "US", "GB", "FR", "ES", "HU", "BG", "UA")
# Romanian-shaped numbers glued to letters (`tel0...`), which the matcher skips.
RO_GLUED = re.compile(r"(?<!\d)0[237]\d{8}(?!\d)")
# Hashes in lockfiles: 32+ hex characters including at least one letter.
HEX_TOKEN = re.compile(r"[0-9A-Fa-f]{32,}")
INTERNATIONAL_00 = re.compile(r"(?<![\d+])00(?=[1-9])")


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    kind: str
    masked: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.kind} {self.masked}"


def mask(value: str) -> str:
    if len(value) <= 4:
        return "•" * len(value)
    return value[0] + "•" * (len(value) - 2) + value[-1]


def cnp_checksum(first12: str) -> int:
    total = sum(int(d) * w for d, w in zip(first12, CNP_WEIGHTS, strict=True))
    rest = total % 11
    return 1 if rest == 10 else rest


def is_valid_cnp(value: str) -> bool:
    """13 digits, first digit 1-9, month 01-12, day 01-31, correct checksum."""
    if len(value) != 13 or not value.isdigit() or value[0] == "0":
        return False
    month, day = int(value[3:5]), int(value[5:7])
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return False
    return cnp_checksum(value[:12]) == int(value[12])


def is_reserved_email_domain(domain: str) -> bool:
    domain = domain.lower()
    if domain.rsplit(".", 1)[-1] in RESERVED_EMAIL_TLDS:
        return True
    return any(domain == d or domain.endswith("." + d) for d in RESERVED_EMAIL_DOMAINS)


def is_fictional_nanp(number: phonenumbers.PhoneNumber) -> bool:
    national = str(number.national_number)
    return (
        number.country_code == 1
        and len(national) == 10
        and national[3:6] == "555"
        and 100 <= int(national[6:]) <= 199
    )


def e164(number: phonenumbers.PhoneNumber) -> str:
    return phonenumbers.format_number(number, PhoneNumberFormat.E164)


def normalize_allowlist_value(value: str) -> str:
    value = value.strip()
    if "@" in value:
        return value.lower()
    try:
        number = phonenumbers.parse(value, "RO")
    except phonenumbers.NumberParseException:
        return re.sub(r"\D", "", value) or value
    return e164(number)


def load_allowlist(root: Path) -> tuple[set[str], list[str]]:
    """Return (normalized values, errors). Every entry needs a `# reason`."""
    path = root / ALLOWLIST_FILE
    values: set[str] = set()
    errors: list[str] = []
    if not path.exists():
        return values, errors
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        value, sep, reason = line.partition("#")
        if not sep or not reason.strip():
            errors.append(f"{ALLOWLIST_FILE}:{lineno}: entry has no '# reason'")
            continue
        values.add(normalize_allowlist_value(value))
    return values, errors


def inline_allowed_kinds(line: str) -> set[str]:
    m = INLINE_ALLOW.search(line)
    if not m:
        return set()
    return {k.strip() for k in m.group("kinds").split(",")} & set(KINDS)


def decode(line: str) -> str:
    """Undo URL and HTML encoding (also doubled, e.g. `%2540`) so encoding can't hide anything."""
    for _ in range(3):
        decoded = html.unescape(unquote(line))
        if decoded == line:
            break
        line = decoded
    return line


def is_international(raw: str) -> bool:
    return raw.lstrip("( ").startswith(("+", "00"))


def in_hex_token(line: str, start: int, end: int) -> bool:
    """True if [start, end) lies inside a long hex string (hashes in lockfiles)."""
    return any(
        m.start() <= start and end <= m.end() and re.search(r"[A-Fa-f]", m.group(0))
        for m in HEX_TOKEN.finditer(line)
    )


def scan_phones(line: str, allow: set[str]) -> Iterator[str]:
    # One report per position: the same digits are often valid in several regions.
    spans: list[tuple[int, int]] = []

    def report(number: phonenumbers.PhoneNumber, raw: str, start: int, end: int) -> Iterator[str]:
        if any(start < e and s < end for s, e in spans) or in_hex_token(line, start, end):
            return
        if is_fictional_nanp(number) or e164(number) in allow:
            spans.append((start, end))
            return
        spans.append((start, end))
        yield raw

    for region in PHONE_REGIONS:
        for match in PhoneNumberMatcher(line, region, leniency=Leniency.VALID):
            # National numbers in these regions have at most 12 digits; 13+ is CNP territory.
            raw = match.raw_string
            if not is_international(raw) and len(re.sub(r"\D", "", raw)) >= 13:
                continue
            yield from report(match.number, match.raw_string, match.start, match.end)

    # International forms: any possible number counts, even in ranges the metadata
    # doesn't know yet. Region ZZ only knows `+`, so `00` is rewritten to ` +` (same length,
    # offsets stay aligned).
    plus_line = INTERNATIONAL_00.sub(" +", line)
    for match in PhoneNumberMatcher(plus_line, "ZZ", leniency=Leniency.POSSIBLE):
        if match.raw_string.lstrip("( ").startswith("+"):
            yield from report(match.number, match.raw_string, match.start, match.end)

    for m in RO_GLUED.finditer(line):
        number = phonenumbers.parse(m.group(0), "RO")
        if phonenumbers.is_valid_number(number):
            yield from report(number, m.group(0), m.start(), m.end())


def scan_line(line: str, allow: set[str]) -> Iterator[tuple[str, str]]:
    """Yield (kind, value) for every disallowed identifier on one line."""
    text = decode(line)

    for m in EMAIL.finditer(text):
        if not is_reserved_email_domain(m.group("domain")) and m.group(0).lower() not in allow:
            yield "email", m.group(0)

    for raw in scan_phones(text, allow):
        yield "phone", raw

    for m in CNP_SHAPE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if (
            is_valid_cnp(digits)
            and digits[0] not in FAKE_CNP_CENTURY_DIGITS
            and digits not in allow
            and not in_hex_token(text, m.start(), m.end())
        ):
            yield "cnp", m.group(0)


def scan_text(path: str, text: str, allow: set[str]) -> list[Finding]:
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        allowed = inline_allowed_kinds(line)
        findings.extend(
            Finding(path, lineno, kind, mask(value))
            for kind, value in scan_line(line, allow)
            if kind not in allowed
        )
    return findings


@dataclass(frozen=True)
class FileText:
    text: str | None  # None: nothing to scan
    error: str | None = None
    note: str | None = None


def read_text_file(path: Path, label: str) -> FileText:
    """Decode a file for scanning. Oversized files are errors (fail closed)."""
    if not path.is_file():
        return FileText(None)
    if path.stat().st_size > MAX_FILE_BYTES:
        return FileText(None, error=f"{label}: larger than 5 MB, can't be checked; keep it out")
    data = path.read_bytes()
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return FileText(data.decode("utf-16", errors="replace"))
    if b"\0" in data[:8192]:
        return FileText(None, note=f"{label}: binary, not checked")
    return FileText(data.decode("utf-8", errors="replace"))


def scan_files(root: Path, paths: Iterable[str]) -> tuple[list[Finding], list[str]]:
    """Return (findings, errors). Notes about skipped binary files go to stderr."""
    allow, errors = load_allowlist(root)
    findings: list[Finding] = []
    for rel in paths:
        if rel == ALLOWLIST_FILE:
            continue
        result = read_text_file(root / rel, rel)
        if result.error:
            errors.append(result.error)
        if result.note:
            print(result.note, file=sys.stderr)
        if result.text is not None:
            findings.extend(scan_text(rel, result.text, allow))
    return findings, errors


def scan_commit_messages(root: Path, paths: Iterable[str]) -> tuple[list[Finding], list[str]]:
    """Like scan_files, but drops git's '#' comment lines (e.g. `# Author: ...`)."""
    allow, errors = load_allowlist(root)
    findings: list[Finding] = []
    for rel in paths:
        result = read_text_file(root / rel, rel)
        if result.error:
            errors.append(result.error)
        if result.text is not None:
            kept = "\n".join(
                "" if line.startswith("#") else line for line in result.text.splitlines()
            )
            findings.extend(scan_text(rel, kept, allow))
    return findings, errors


def git(root: Path, *args: str) -> list[str]:
    out = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def git_value(root: Path, *args: str) -> str:
    """Single-line git output (rev-parse doesn't support -z)."""
    out = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return out.stdout.strip()


def repo_files(root: Path) -> list[str]:
    """Every file git tracks or would track (respects .gitignore and info/exclude)."""
    return git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")


def private_paths_in_index(root: Path) -> list[str]:
    """Tracked or staged files that match `.git/info/exclude` (the private kit).

    The private paths are read from the exclude file, so no tracked file names them.
    """
    exclude_file = root / git_value(root, "rev-parse", "--git-path", "info/exclude")
    if not exclude_file.exists():
        return []
    return git(root, "ls-files", "-z", "--cached", "--ignored", f"--exclude-from={exclude_file}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Block real identifiers and private files.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--skip-private", action="store_true", help="only scan the given files")
    mode.add_argument("--private-only", action="store_true", help="only check private paths")
    mode.add_argument(
        "--commit-msg",
        action="store_true",
        help="scan a commit message file, ignoring git's '#' comment lines",
    )
    parser.add_argument("files", nargs="*")
    args = parser.parse_args(argv)

    root = Path(git_value(Path.cwd(), "rev-parse", "--show-toplevel"))
    findings: list[Finding] = []
    errors: list[str] = []
    if args.commit_msg:
        findings, errors = scan_commit_messages(root, args.files)
    elif not args.private_only:
        findings, errors = scan_files(root, args.files or repo_files(root))
    private = [] if args.skip_private or args.commit_msg else private_paths_in_index(root)

    for err in errors:
        print(err, file=sys.stderr)
    for path in private:
        print(
            f"{path}: private file is staged or tracked; unstage it (git rm --cached)",
            file=sys.stderr,
        )
    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        print(
            "\nReal-looking identifiers found. Use fake data (reserved domains, +1 NXX 555-01XX, "
            "generated Romanian data), add a public organisation contact to "
            f"{ALLOWLIST_FILE} with a reason, or mark one false positive with a comment "
            "'identifier-allow[<kind>]: <reason>' on the line.",
            file=sys.stderr,
        )
    return 1 if findings or errors or private else 0


if __name__ == "__main__":
    raise SystemExit(main())
