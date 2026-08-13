"""Meta error codes in plain English.

Meta's codes are opaque to anyone who has not memorised them — a tenant seeing
"131047" learns nothing, files a ticket, and waits. Mapping them at the edge is
the difference between a self-service explanation and a support conversation.

`permanent` marks the codes where retrying is pointless AND the number should
be suppressed: continuing to send to a number that cannot receive burns the
tenant's quality rating for a delivery that will never happen.
"""
from typing import NamedTuple, Optional


class ErrorMeaning(NamedTuple):
    message: str
    permanent: bool
    # A billing problem is neither permanent nor retryable-by-us: nothing we do
    # fixes it, and it blocks EVERY send on that account rather than one number.
    # It has to stop the campaign and tell the tenant to add a payment method.
    billing: bool = False
    # Worth trying again shortly (Meta pacing, transient server error) as opposed
    # to a fault in the message itself.
    retryable: bool = False


_CODES: dict[int, ErrorMeaning] = {
    131026: ErrorMeaning(
        "This number isn't on WhatsApp, or can't receive messages.", True),
    131047: ErrorMeaning(
        "More than 24 hours have passed since this customer last messaged, so only an "
        "approved template can be delivered.", True),
    131049: ErrorMeaning(
        "Meta limited this message to protect the user experience. Try again later, or "
        "reduce how many messages you send at once.", False, retryable=True),
    131000: ErrorMeaning("Something went wrong at Meta's end. It's worth retrying.", False,
                         retryable=True),
    # Billing. Codes observed for "no payment method / business not eligible to
    # send paid messages"; the text check below is the safety net, because Meta
    # has used more than one code for this over time.
    131042: ErrorMeaning(
        "WhatsApp can't send because there's no valid payment method on your WhatsApp "
        "Business Account. Add one in Meta Business Settings → WhatsApp Accounts → "
        "Payment settings, then try again.", False, billing=True),
    131045: ErrorMeaning(
        "WhatsApp rejected the send for an account setup or certificate issue. Check your "
        "WhatsApp Business Account in Meta Business Settings.", False),
    132000: ErrorMeaning(
        "The template's variables don't match what was approved — the message was rejected.", False),
    132001: ErrorMeaning(
        "That template doesn't exist on this WhatsApp account, or isn't approved yet.", False),
    132005: ErrorMeaning("The template text is too long for one of its fields.", False),
    132007: ErrorMeaning("The template was rejected by Meta and can't be used.", False),
    131031: ErrorMeaning(
        "This WhatsApp account has been restricted by Meta. Check WhatsApp Manager.", False),
    131030: ErrorMeaning(
        "This recipient isn't on your test number's allowed list. Add and verify it in "
        "the Meta app dashboard, or connect a live WhatsApp account.", False),
    130472: ErrorMeaning(
        "This user is in an experiment group that doesn't receive marketing messages.", True),
    133010: ErrorMeaning("The phone number isn't registered for sending yet.", False),
    368: ErrorMeaning(
        "Temporarily blocked for policy reasons — this usually follows too many blocks "
        "or reports from recipients.", False),
}

_FALLBACK = ErrorMeaning("WhatsApp could not deliver this message.", False)


def explain(code: Optional[int | str]) -> ErrorMeaning:
    try:
        return _CODES.get(int(code), _FALLBACK)
    except (TypeError, ValueError):
        return _FALLBACK


def is_permanent(code: Optional[int | str]) -> bool:
    return explain(code).permanent


def is_billing(code: Optional[int | str], text: str = "") -> bool:
    """Billing failures must pause the whole campaign, not skip one recipient.

    Meta has used several codes for "no payment method", so the message text is
    checked as well — getting this wrong means burning an entire batch's worth of
    failures against an account that cannot send at all.
    """
    if explain(code).billing:
        return True
    lowered = (text or "").lower()
    return any(term in lowered for term in
               ("payment method", "payment_method", "billing", "not eligible to send",
                "payment issue"))


def is_retryable(code: Optional[int | str]) -> bool:
    return explain(code).retryable
