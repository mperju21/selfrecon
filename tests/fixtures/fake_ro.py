"""Fake Romanian test data, generated at test time.

Romania has no fictional phone range, so phone numbers come from `phonenumbers`
example numbers and are never hard-coded. CNPs use century digit 3/4 (born
1800-1899, so nobody alive) with a valid checksum. ID card series is always XX.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

import phonenumbers
from phonenumbers import PhoneNumberFormat, PhoneNumberType

from tools.check_identifiers import cnp_checksum

FAKE_NAMES = ("Ștefănița Testescu", "Ionuț Exemplaru", "Mădălina Testescu-Probescu")
FAKE_FORMER_NAMES = ("Ștefănița Fictivescu",)
FAKE_ADDRESS = "Strada Exemplului nr. 0, bl. X0, ap. 0, București"
FAKE_ID_SERIES = "XX"
BUCHAREST_SECTOR_1 = 41


def ro_phone(kind: int = PhoneNumberType.MOBILE) -> phonenumbers.PhoneNumber:
    number = phonenumbers.example_number_for_type("RO", kind)
    if number is None:
        raise LookupError(f"phonenumbers has no RO example for {kind}")
    return number


def ro_phone_e164(kind: int = PhoneNumberType.MOBILE) -> str:
    return phonenumbers.format_number(ro_phone(kind), PhoneNumberFormat.E164)


def ro_phone_national(kind: int = PhoneNumberType.MOBILE) -> str:
    return phonenumbers.format_number(ro_phone(kind), PhoneNumberFormat.NATIONAL)


def fake_cnp(
    *,
    female: bool = False,
    year: int = 1850,
    month: int = 6,
    day: int = 15,
    county: int = BUCHAREST_SECTOR_1,
    serial: int = 1,
) -> str:
    """A CNP for someone born in the 1800s, with a valid checksum."""
    if not 1800 <= year <= 1899:
        raise ValueError("fake CNPs must be born 1800-1899")
    first12 = f"{4 if female else 3}{year % 100:02d}{month:02d}{day:02d}{county:02d}{serial:03d}"
    return first12 + str(cnp_checksum(first12))


def random_fake_cnp(rng: random.Random) -> str:
    return fake_cnp(
        female=rng.random() < 0.5,
        year=rng.randint(1800, 1899),
        month=rng.randint(1, 12),
        day=rng.randint(1, 28),
        county=rng.randint(1, 46),
        serial=rng.randint(1, 999),
    )


@dataclass(frozen=True)
class FakeIdCard:
    series: str
    number: str

    def __str__(self) -> str:
        return f"{self.series}{self.number}"


def fake_id_card(rng: random.Random) -> FakeIdCard:
    return FakeIdCard(FAKE_ID_SERIES, f"{rng.randint(0, 999_999):06d}")
