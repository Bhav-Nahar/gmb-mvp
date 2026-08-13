"""Phone normalisation for WhatsApp sends.

Pure logic, no network, no DB — this is the function that decides where a
message actually goes, and a wrong answer here means messaging a stranger.
"""
import pytest

from app.services.whatsapp_service import normalize_phone


@pytest.mark.parametrize("raw,expected", [
    ("9876543210", "919876543210"),            # bare Indian mobile
    ("+91 98765 43210", "919876543210"),       # already country-coded, spaced
    ("09876543210", "919876543210"),           # 0-prefixed, as people write it
    ("+91-98765-43210", "919876543210"),       # hyphenated
    ("919876543210", "919876543210"),          # already correct, unchanged
])
def test_indian_numbers_normalise_to_e164_digits(raw, expected):
    assert normalize_phone(raw) == expected


def test_non_indian_number_keeps_its_own_country_code():
    # 11+ digits are already international; the default must not be prepended.
    assert normalize_phone("+1 415 555 2671") == "14155552671"


def test_default_country_code_is_overridable():
    # Pinzo serves several markets, so the default is a parameter — a hardcoded
    # +91 would silently mangle every non-Indian 10-digit number.
    assert normalize_phone("4155552671", default_country_code="1") == "14155552671"


@pytest.mark.parametrize("raw", ["", None, "abc", "12345", "9" * 20])
def test_unusable_input_returns_none_rather_than_guessing(raw):
    # None makes the caller skip the row. Guessing would send someone else's
    # customer a message meant for a number that was never valid.
    assert normalize_phone(raw) is None
