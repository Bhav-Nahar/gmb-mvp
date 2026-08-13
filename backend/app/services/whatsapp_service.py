"""WhatsApp Cloud API client — sends on behalf of a tenant's own WABA.

Every call takes a `WhatsAppAccount`, never global credentials: Pinzo is a Meta
Tech Provider, so each organization's messages go out on their own number with
their own token and their own quality rating. There is deliberately no
module-level token here — a shared one would let one tenant's sending behaviour
throttle or ban everyone else's.

Synchronous (httpx.Client) because the callers are Celery tasks working through
a queue of recipients. FastAPI request handlers should not call `send_template`
directly; they enqueue.

The two WhatsApp rules that shape this file:
  1. Outside the 24-hour customer-service window, only an approved TEMPLATE can
     be sent. A review request is always cold contact — the customer has not
     just messaged us — so there is no free-form send path here at all.
  2. Templates live on the WABA that will send them, so each tenant gets their
     own copy created and approved at onboarding.
"""
import logging
import re
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.security import decrypt_token
from app.models.whatsapp_account import WhatsAppAccount

logger = logging.getLogger(__name__)

GRAPH_VERSION = getattr(settings, "WHATSAPP_GRAPH_VERSION", "v21.0")
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"
TIMEOUT = 25.0


class WhatsAppError(Exception):
    """A Graph API failure, with Meta's own error code preserved.

    The code is the useful part: 131047 (outside the 24h window), 131026 (not a
    WhatsApp user), 132001 (template missing) each need a different response
    from us, and the message text alone is not reliable enough to branch on.
    """

    def __init__(self, message: str, code: Optional[int] = None,
                 subcode: Optional[int] = None, detail: Optional[str] = None,
                 user_title: Optional[str] = None, user_msg: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.subcode = subcode
        self.detail = detail
        # Meta puts the ACTUAL reason in error_user_title/error_user_msg and
        # leaves `message` as a generic "Invalid parameter". Dropping these was
        # the difference between "Invalid parameter" and "the template name is
        # being deleted, try again in a minute".
        self.user_title = user_title
        self.user_msg = user_msg


def _raise_meta_error(path: str, status_code: int, body: dict[str, Any]) -> None:
    """Meta's generic `message` is rarely the useful part — prefer the fields
    written for humans, and keep the codes for programmatic branching."""
    err = body.get("error") or {}
    human = err.get("error_user_msg") or err.get("message") or "unknown error"
    title = err.get("error_user_title")
    raise WhatsAppError(
        f"WhatsApp {path} -> {status_code}: {title + ': ' if title else ''}{human}",
        code=err.get("code"),
        subcode=err.get("error_subcode"),
        detail=(err.get("error_data") or {}).get("details"),
        user_title=title,
        user_msg=err.get("error_user_msg"),
    )


def normalize_phone(raw: str, default_country_code: str = "91") -> Optional[str]:
    """E.164 digits with no leading '+', which is the exact format Meta's `to`
    field expects. Returns None when the input cannot be a phone number, so
    callers skip the row rather than sending somewhere unintended.

    A bare 10-digit number gets `default_country_code` — India for now, but it
    is a parameter because Pinzo already serves multiple markets and hardcoding
    +91 would silently mangle every non-Indian number.
    """
    if not raw:
        return None
    digits = re.sub(r"\D", "", str(raw))
    if not digits:
        return None
    if len(digits) == 10:
        digits = f"{default_country_code}{digits}"
    elif len(digits) == 11 and digits.startswith("0"):
        digits = f"{default_country_code}{digits[1:]}"
    # Shortest plausible international number is 11 digits with a country code;
    # E.164 caps at 15. Anything outside that is data entry, not a number.
    if len(digits) < 11 or len(digits) > 15:
        return None
    return digits


def _token(account: WhatsAppAccount) -> str:
    token = decrypt_token(account.access_token)
    if not token:
        raise WhatsAppError("This organization has no WhatsApp access token stored")
    return token


def _post(path: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT) as client:
        res = client.post(
            f"{GRAPH}{path}",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
    try:
        body = res.json()
    except ValueError:
        body = {"raw": res.text[:250]}

    if res.status_code >= 400:
        _raise_meta_error(path, res.status_code, body)
    return body


def _get(path: str, token: str, params: Optional[dict] = None) -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT) as client:
        res = client.get(
            f"{GRAPH}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
        )
    body = res.json() if res.content else {}
    if res.status_code >= 400:
        _raise_meta_error(path, res.status_code, body)
    return body


def send_template(
    account: WhatsAppAccount,
    to: str,
    template_name: str,
    *,
    language: str = "en",
    body_params: Optional[list[str]] = None,
    button_url_param: Optional[str] = None,
) -> str:
    """Send one approved template. Returns Meta's message id (wamid).

    `button_url_param` is the suffix for a dynamic URL button — for review
    requests this is the recipient's token, which turns the fixed
    `https://pinzo.io/r/` base into that person's own link. Meta indexes
    buttons from 0 and wants the index as a STRING; both are easy to get wrong
    and fail with an unhelpful component-mismatch error.
    """
    if not account.phone_number_id:
        raise WhatsAppError("This organization has no WhatsApp phone number registered")

    components: list[dict[str, Any]] = []
    if body_params:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(p or "")} for p in body_params],
        })
    if button_url_param:
        components.append({
            "type": "button",
            "sub_type": "url",
            "index": "0",
            "parameters": [{"type": "text", "text": str(button_url_param)}],
        })

    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {"name": template_name, "language": {"code": language}},
    }
    if components:
        payload["template"]["components"] = components

    body = _post(f"/{account.phone_number_id}/messages", _token(account), payload)
    messages = body.get("messages") or []
    if not messages:
        raise WhatsAppError(f"WhatsApp accepted the request but returned no message id: {body}")
    return messages[0]["id"]


def create_template(account: WhatsAppAccount, payload: dict[str, Any]) -> dict[str, Any]:
    """Create a message template on the tenant's WABA (onboarding).

    Returns {id, status, category}. Approval is asynchronous — usually minutes,
    sometimes a day — so the caller stores the status and polls rather than
    assuming the template is usable on return.
    """
    if not account.waba_id:
        raise WhatsAppError("This organization has no WhatsApp Business Account id")
    return _post(f"/{account.waba_id}/message_templates", _token(account), payload)


def get_phone_number_info(account: WhatsAppAccount) -> dict[str, Any]:
    """Quality rating and send tier for the account's number.

    These are what explain a throttle to a tenant ("you can send N more today")
    instead of leaving them to discover it as an unexplained stall. Field names
    have shifted across Graph versions, so callers must tolerate any of them
    being absent rather than assuming the shape.
    """
    if not account.phone_number_id:
        return {}
    return _get(
        f"/{account.phone_number_id}",
        _token(account),
        {"fields": "display_phone_number,verified_name,quality_rating,messaging_limit_tier"},
    )


def get_template_status(account: WhatsAppAccount, name: str) -> Optional[str]:
    """PENDING | APPROVED | REJECTED, or None when the template does not exist."""
    if not account.waba_id:
        return None
    body = _get(f"/{account.waba_id}/message_templates", _token(account),
                {"name": name, "limit": 1})
    data = body.get("data") or []
    return data[0].get("status") if data else None
