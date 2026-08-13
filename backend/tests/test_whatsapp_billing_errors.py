"""A missing payment method must stop the campaign, not skip one number.

If it were treated like any other send failure, a 2,000-row batch would grind
through every recipient collecting the same error — thousands of failed rows,
a tenant with no idea what to fix, and a quality rating hit for nothing.
"""
from app.services import whatsapp_errors as we


def test_known_billing_code_is_billing():
    assert we.is_billing(131042) is True


def test_billing_is_detected_from_the_message_when_the_code_is_unfamiliar():
    # Meta has used more than one code for this; the wording is the safety net.
    assert we.is_billing(9999, "Business does not have a valid payment method") is True
    assert we.is_billing(None, "billing issue on the WhatsApp account") is True


def test_ordinary_failures_are_not_billing():
    assert we.is_billing(131026) is False
    assert we.is_billing(131047, "24 hours have passed") is False


def test_billing_codes_are_not_marked_permanent():
    """Permanent means "suppress this number forever". Billing is fixable, so
    suppressing the recipient would silently lose them once the card is added."""
    assert we.is_permanent(131042) is False


def test_pacing_and_server_errors_are_retryable_but_bad_numbers_are_not():
    assert we.is_retryable(131049) is True
    assert we.is_retryable(131000) is True
    assert we.is_retryable(131026) is False
