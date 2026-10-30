"""Fake identities for tests. Reserved domains and fictional NANP numbers only."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class FakeIdentity:
    label: str
    name: str
    emails: tuple[str, ...]
    usernames: tuple[str, ...]
    phones: tuple[str, ...]
    former_names: tuple[str, ...] = field(default=())


ALICE = FakeIdentity(
    label="Alice",
    name="Alice Testperson",
    emails=("alice.testperson@example.com", "alice@mail.example"),
    usernames=("fake_alice", "fake_alice_t"),
    phones=("+1 202 555 0143",),
)

BOB = FakeIdentity(
    label="Bob",
    name="Bob Exampleton",
    emails=("bob.exampleton@example.org", "bob@inbox.invalid"),
    usernames=("fake_bob",),
    phones=("+1 415 555 0123",),
    former_names=("Bob Placeholder",),
)

ALL = (ALICE, BOB)
