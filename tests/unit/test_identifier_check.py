"""Tests for tools/check_identifiers.py.

Real-looking values are assembled at runtime so this file itself stays clean.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import phonenumbers
import pytest
from phonenumbers import PhoneNumberFormat, PhoneNumberType, format_number

from tests.fixtures.fake_identities import ALICE, BOB
from tests.fixtures.fake_ro import fake_cnp, ro_phone, ro_phone_e164, ro_phone_national
from tools.check_identifiers import (
    MAX_FILE_BYTES,
    cnp_checksum,
    is_valid_cnp,
    load_allowlist,
    main,
    private_paths_in_index,
    scan_files,
    scan_text,
)

AT = "@"
URL_AT = "%" + "40"
HTML_AT = "&#" + "64;"


def kinds(text: str, allow: set[str] | None = None) -> list[str]:
    return [f.kind for f in scan_text("x.txt", text, allow or set())]


def living_person_cnp() -> str:
    """Same shape as a fake CNP but with century digit 1, so the checker must flag it."""
    first12 = "1" + fake_cnp()[1:12]
    return first12 + str(cnp_checksum(first12))


# --- emails -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "email",
    [
        *ALICE.emails,
        *BOB.emails,
        "someone@sub.example.net",
        "x@host.test",
        "UPPER@EXAMPLE.COM",
    ],
)
def test_reserved_emails_pass(email: str) -> None:
    assert kinds(f"contact: {email}") == []


@pytest.mark.parametrize("domain", ["mailbox.ro", "example.com.ro", "notexample.com"])
def test_other_emails_are_flagged(domain: str) -> None:
    assert kinds(f"contact: someone{AT}{domain}") == ["email"]


def test_decorators_and_handles_are_not_emails() -> None:
    assert kinds("@pytest.mark.leak\nuser @someone said hi") == []


# --- phones -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "number", [*ALICE.phones, *BOB.phones, "+1 202 555 0100", "+1 (212) 555-0199", "2025550143"]
)
def test_fictional_nanp_passes(number: str) -> None:
    assert kinds(f"call {number}") == []


def test_other_555_numbers_are_flagged() -> None:
    assert kinds("call +1 202 555 " + "1234") == ["phone"]


def test_romanian_numbers_are_flagged_in_every_format() -> None:
    international = format_number(ro_phone(), PhoneNumberFormat.INTERNATIONAL)
    for text in (ro_phone_e164(), ro_phone_national(), international):
        assert kinds(f"tel: {text}") == ["phone"], text


def test_hashes_versions_and_dates_are_not_phones() -> None:
    text = (
        "sha256:0723456789abcdef0723456789abcdef version 1.20.3045 "
        "2026-10-30 12:00:00 uuid 07234567-89ab-4cde-8f01-234567890abc"
    )
    assert kinds(text) == []


# --- CNP ----------------------------------------------------------------------------------


def test_fake_cnp_is_valid_and_allowed() -> None:
    cnp = fake_cnp(female=True, year=1876, month=2, day=29)
    assert is_valid_cnp(cnp)
    assert kinds(f"cnp {cnp}") == []


def test_cnp_of_a_possibly_living_person_is_flagged() -> None:
    cnp = living_person_cnp()
    assert is_valid_cnp(cnp)
    assert kinds(f"cnp {cnp}") == ["cnp"]


@pytest.mark.parametrize(
    "value",
    [
        "1730000000000",  # millisecond timestamp: month 00
        "1234567890123",  # bad checksum or date
        "0123456789012",  # first digit 0 is never a CNP
    ],
)
def test_cnp_shaped_non_cnps_pass(value: str) -> None:
    assert kinds(value) == []


def test_cnp_inside_longer_digit_run_is_ignored() -> None:
    assert kinds("9" + living_person_cnp() + "9") == []


# --- overrides ----------------------------------------------------------------------------


def test_inline_override_exempts_one_kind_with_a_reason() -> None:
    cnp = living_person_cnp()
    assert kinds(f"{cnp}  # identifier-allow[cnp]: checksum test vector") == []
    assert kinds(f"{cnp}  // identifier-allow[cnp]: checksum test vector") == []
    assert kinds(f"{cnp}  <!-- identifier-allow[cnp]: checksum test vector -->") == []


@pytest.mark.parametrize(
    "suffix",
    [
        "# identifier-allow[cnp]:",  # no reason
        "# identifier-allow[cnp]: x",  # reason too short
        "# identifier-allow: checksum test vector",  # no kind
        "identifier-allow[cnp]: not in a comment",  # no comment marker
        "# identifier-allow[email]: wrong kind named",
    ],
)
def test_inline_override_rejects_loose_forms(suffix: str) -> None:
    assert kinds(f"{living_person_cnp()}  {suffix}") == ["cnp"]


def test_inline_override_does_not_cover_other_kinds_on_the_line() -> None:
    line = f"{living_person_cnp()} someone{AT}mailbox.ro  # identifier-allow[cnp]: test vector"
    assert kinds(line) == ["email"]


def test_allowlist_by_exact_value(tmp_path: Path) -> None:
    org_email = f"office{AT}authority.ro"
    org_phone = ro_phone_e164()
    (tmp_path / ".identifier-allowlist").write_text(
        f"# public contacts\n{org_email}  # public authority contact\n"
        f"{org_phone}  # public authority switchboard\n",
        encoding="utf-8",
    )
    (tmp_path / "pack.yaml").write_text(
        f"email: {org_email}\nphone: {ro_phone_national()}\nother: someone{AT}authority.ro\n",
        encoding="utf-8",
    )
    findings, errors = scan_files(tmp_path, ["pack.yaml", ".identifier-allowlist"])
    assert errors == []
    assert [f.kind for f in findings] == ["email"]
    assert findings[0].line == 3


def test_allowlist_entry_without_reason_is_an_error(tmp_path: Path) -> None:
    (tmp_path / ".identifier-allowlist").write_text(f"office{AT}authority.ro\n", encoding="utf-8")
    _, errors = load_allowlist(tmp_path)
    assert len(errors) == 1


def test_findings_are_masked() -> None:
    cnp = living_person_cnp()
    [finding] = scan_text("f.py", cnp, set())
    assert cnp not in str(finding)


def test_binary_and_missing_files_are_skipped(tmp_path: Path) -> None:
    (tmp_path / "blob.bin").write_bytes(b"\0" + living_person_cnp().encode())
    findings, errors = scan_files(tmp_path, ["blob.bin", "deleted.txt"])
    assert findings == []
    assert errors == []


def test_oversized_files_are_errors(tmp_path: Path) -> None:
    (tmp_path / "big.json").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    _, errors = scan_files(tmp_path, ["big.json"])
    assert len(errors) == 1


def test_utf16_text_is_scanned(tmp_path: Path) -> None:
    (tmp_path / "export.csv").write_text(f"cnp,{living_person_cnp()}\n", encoding="utf-16")
    findings, _ = scan_files(tmp_path, ["export.csv"])
    assert [f.kind for f in findings] == ["cnp"]


# --- encodings and formats (privacy review) -----------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        f"ionuț{AT}mailbox.ro",  # diacritic in the local part
        f"someone{AT}mäil.ro",  # IDN domain
        f"someone{URL_AT}mailbox.ro",  # URL-encoded @
        f"someone{HTML_AT}mailbox.ro",  # HTML entity
    ],
)
def test_encoded_and_unicode_emails_are_flagged(text: str) -> None:
    assert kinds(text) == ["email"]


@pytest.mark.parametrize("region", ["MD", "GB", "FR", "HU", "BG", "UA"])
def test_national_format_numbers_of_nearby_countries_are_flagged(region: str) -> None:
    number = phonenumbers.example_number_for_type(region, PhoneNumberType.MOBILE)
    assert number is not None
    national = format_number(number, PhoneNumberFormat.NATIONAL)
    assert kinds(f"tel: {national}") == ["phone"], region


def test_romanian_numbers_glued_to_letters_or_url_encoded_are_flagged() -> None:
    digits = format_number(ro_phone(), PhoneNumberFormat.NATIONAL).replace(" ", "")
    assert kinds(f"tel{digits}") == ["phone"]
    assert kinds("https://wa.me/?p=%2B" + ro_phone_e164()[1:]) == ["phone"]


@pytest.mark.parametrize("sep", [" ", ".", "-"])
def test_cnp_with_separators_is_flagged(sep: str) -> None:
    cnp = living_person_cnp()
    grouped = sep.join([cnp[0], cnp[1:7], cnp[7:]])
    assert kinds(f"cnp {grouped}") == ["cnp"]


def test_lockfile_hashes_are_not_flagged() -> None:
    digits = format_number(ro_phone(), PhoneNumberFormat.NATIONAL).replace(" ", "")
    line = f'hash = "sha256:ab{digits}cdef0123456789abcdef{living_person_cnp()}ab"'
    assert kinds(line) == []


# --- private paths ------------------------------------------------------------------------


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def test_private_paths_in_index_are_detected(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / ".git" / "info" / "exclude").write_text("/kit.md\n/notes/\n", encoding="utf-8")
    (tmp_path / "kit.md").write_text("private", encoding="utf-8")
    (tmp_path / "public.md").write_text("public", encoding="utf-8")
    _git(tmp_path, "add", "public.md")
    assert private_paths_in_index(tmp_path) == []

    _git(tmp_path, "add", "-f", "kit.md")
    assert private_paths_in_index(tmp_path) == ["kit.md"]


def test_commit_message_mode_flags_identifiers_and_allows_coauthor_trailer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / ".identifier-allowlist").write_text(
        f"noreply{AT}anthropic.com  # co-author trailer\n", encoding="utf-8"
    )
    msg = tmp_path / ".git" / "COMMIT_EDITMSG"
    monkeypatch.chdir(tmp_path)

    msg.write_text(f"Fix parser\n\nCo-Authored-By: Claude <noreply{AT}anthropic.com>\n")
    assert main(["--commit-msg", ".git/COMMIT_EDITMSG"]) == 0

    msg.write_text(f"Fix parser for someone{AT}mailbox.ro\n")
    assert main(["--commit-msg", ".git/COMMIT_EDITMSG"]) == 1


def test_private_only_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / ".git" / "info" / "exclude").write_text("/kit.md\n", encoding="utf-8")
    (tmp_path / "kit.md").write_text("private", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["--private-only"]) == 0
    _git(tmp_path, "add", "-f", "kit.md")
    assert main(["--private-only"]) == 1


# --- second privacy review ----------------------------------------------------------------


@pytest.mark.parametrize("region", ["RO", "MD", "GB", "DE", "IT"])
@pytest.mark.parametrize("spaced", [True, False])
def test_international_00_prefix_is_flagged(region: str, spaced: bool) -> None:
    number = phonenumbers.example_number_for_type(region, PhoneNumberType.MOBILE)
    assert number is not None
    intl = format_number(number, PhoneNumberFormat.INTERNATIONAL)  # "+cc ..."
    text = "00" + intl[1:]
    if not spaced:
        text = text.replace(" ", "").replace("-", "")
    assert kinds(f"tel: {text}") == ["phone"], text


def test_doubly_url_encoded_at_is_flagged() -> None:
    assert kinds("someone%" + "2540mailbox.ro") == ["email"]


def test_punycode_tld_is_flagged() -> None:
    assert kinds(f"someone{AT}mail.xn--p1ai") == ["email"]


def test_identifiers_glued_to_short_hex_runs_are_flagged() -> None:
    assert kinds("abcdefa" + living_person_cnp()) == ["cnp"]
    digits = format_number(ro_phone(), PhoneNumberFormat.NATIONAL).replace(" ", "")
    assert kinds("deadbeefcafe" + digits) == ["phone"]


def test_commit_msg_mode_ignores_git_comment_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _git(tmp_path, "init", "-q")
    msg = tmp_path / ".git" / "COMMIT_EDITMSG"
    monkeypatch.chdir(tmp_path)
    msg.write_text(f"Fix parser\n# Author: Someone <someone{AT}mailbox.ro>\n")
    assert main(["--commit-msg", ".git/COMMIT_EDITMSG"]) == 0
    msg.write_text(f"Fix parser for someone{AT}mailbox.ro\n")
    assert main(["--commit-msg", ".git/COMMIT_EDITMSG"]) == 1


def test_00_inside_a_hash_is_not_a_phone() -> None:
    line = 'url = "https://files.example/2b/e2/b0c140fe50fa39dd249e382f7733af6f816c90021fe7959a0b026f86237f/x.whl"'
    assert kinds(line) == []
