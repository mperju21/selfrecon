from __future__ import annotations

import random

import phonenumbers
import pytest
from phonenumbers import PhoneNumberType

from tests.fixtures.fake_ro import (
    FAKE_ADDRESS,
    FAKE_NAMES,
    fake_cnp,
    fake_id_card,
    random_fake_cnp,
    ro_phone,
)
from tools.check_identifiers import is_valid_cnp, scan_text


def test_random_fake_cnps_are_valid_1800s_and_pass_the_checker() -> None:
    rng = random.Random(1234)
    for _ in range(500):
        cnp = random_fake_cnp(rng)
        assert is_valid_cnp(cnp)
        assert cnp[0] in "34"
        assert scan_text("t", cnp, set()) == []


def test_fake_cnp_refuses_years_outside_1800s() -> None:
    with pytest.raises(ValueError, match="1800-1899"):
        fake_cnp(year=1950)


@pytest.mark.parametrize("kind", [PhoneNumberType.MOBILE, PhoneNumberType.FIXED_LINE])
def test_ro_phones_are_generated_and_valid(kind: int) -> None:
    number = ro_phone(kind)
    assert phonenumbers.region_code_for_number(number) == "RO"
    assert phonenumbers.number_type(number) == kind


def test_fake_id_card_uses_series_xx() -> None:
    card = fake_id_card(random.Random(7))
    assert card.series == "XX"
    assert len(card.number) == 6
    assert card.number.isdigit()


def test_fake_names_have_romanian_diacritics() -> None:
    joined = " ".join(FAKE_NAMES).lower()
    for letter in "ășț":  # comma-below forms, as in current official spelling
        assert letter in joined
    assert "ș" in FAKE_ADDRESS
