"""Keeps tests/fixtures/README.md true: how phonenumbers classifies the fake numbers."""

from __future__ import annotations

import phonenumbers
import pytest
from phonenumbers import PhoneNumberType

from tests.fixtures.fake_identities import ALL


@pytest.mark.parametrize("raw", [p for ident in ALL for p in ident.phones])
def test_fictional_nanp_numbers_are_valid_fixed_line_or_mobile(raw: str) -> None:
    number = phonenumbers.parse(raw, None)
    assert phonenumbers.is_possible_number(number)
    assert phonenumbers.is_valid_number(number)
    assert phonenumbers.number_type(number) == PhoneNumberType.FIXED_LINE_OR_MOBILE
