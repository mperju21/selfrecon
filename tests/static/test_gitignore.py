"""Secrets, databases, runtime data and exports must never be picked up by git."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        "workspace.db",
        "x.sqlite",
        "data/workspace.db",
        "exports/r.pdf",
        "evidence/s1/blob",
        ".DS_Store",
    ],
)
def test_sensitive_paths_are_ignored(path: str) -> None:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", path], cwd=ROOT, check=False
    )
    assert result.returncode == 0, f"{path} is not ignored"
