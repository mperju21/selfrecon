"""Guard test 4 (see the testing conventions): the repository holds no real-looking identifiers
and no private files. Mirrors the pre-commit hook."""

from __future__ import annotations

from pathlib import Path

from tools.check_identifiers import private_paths_in_index, repo_files, scan_files

ROOT = Path(__file__).resolve().parents[2]


def test_no_real_looking_identifiers_in_repo() -> None:
    findings, errors = scan_files(ROOT, repo_files(ROOT))
    assert errors == []
    assert [str(f) for f in findings] == []


def test_no_private_files_tracked_or_staged() -> None:
    assert private_paths_in_index(ROOT) == []
