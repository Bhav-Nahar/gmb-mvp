"""Embedded Signup — connecting a tenant's own WhatsApp Business Account.

Pinzo never owns a client's WABA. The client completes Meta's hosted signup,
Meta hands us a short-lived `code`, and we exchange it for a business token that
authorises us to act on *their* account. Their card pays Meta for every message.

The onboarding sequence, and why each step exists:

  1. exchange_code        code -> business access token (ours to keep, encrypted)
  2. discover_waba        which WABA that token actually grants — never trust a
                          client-supplied id, it comes from a browser
  3. fetch_phone_numbers  the number they picked during signup
  4. subscribe_app        without this, NO webhooks arrive for their WABA: no
                          delivery receipts, no opt-outs. Silent if skipped,
                          which is the worst kind of missing step
  5. register_number      activates the number for Cloud API sending
  6. ensure_template      templates live on the sending WABA, so every tenant
                          needs their own copy of the review-request template

Any step can fail on the client's side (unverified business, no payment method,
number still in the WhatsApp app). Each failure is recorded as a status on the
account row with a sentence the tenant can act on, rather than an exception
thrown into a support queue.
"""
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token_payload, encrypt_token
from app.models.whatsapp_account import WhatsAppAccount
from app.services.whatsapp_service import GRAPH, WhatsAppError, _raise_meta_error

logger = logging.getLogger(__name__)

TIMEOUT = 25.0

# The template every tenant gets. One text, approved separately on each WABA —
# the business name is a variable precisely so the copy never has to change per
# client (which would mean a fresh approval, and a day's wait, per onboarding).
REVIEW_TEMPLATE_NAME = "pinzo_review_request"


def _app_credentials() -> tuple[str, str]:
    app_id = (getattr(settings, "FACEBOOK_APP_ID", "") or "").strip()
    app_secret = (getattr(settings, "FACEBOOK_APP_SECRET", "") or "").strip()
    if not app_id or not app_secret:
        raise WhatsAppError("FACEBOOK_APP_ID / FACEBOOK_APP_SECRET are not configured")
    return app_id, app_secret


# ── State: which organization is coming back from Meta ────────────────────────
# The signup happens on Meta's domain, so the only thing that survives the round
# trip is the `state` we send. It is SIGNED (reusing the JWT helper) and short
# lived: an unsigned org id would let anyone attach their WhatsApp account to
# someone else's organization by editing a query parameter.

def make_state(organization_id: int) -> str:
    return create_access_token(subject=f"wa_signup:{organization_id}",
                               expires_delta=timedelta(minutes=30))


def read_state(state: str) -> Optional[int]:
    payload = decode_access_token_payload(state) or {}
    subject = str(payload.get("sub") or "")
    if not subject.startswith("wa_signup:"):
        return None
    try:
        return int(subject.split(":", 1)[1])
    except (ValueError, IndexError):
        return None


# Meta's hosted landing page runs the whole signup — including migrating a
# number that is currently in the WhatsApp Business app, which is the single
# biggest source of onboarding failure. `extras` is Meta's own opaque config
# blob copied verbatim from the generated link; do not hand-edit the versions.
_ES_LANDING = "https://business.facebook.com/messaging/whatsapp/onboard/"
_ES_EXTRAS = {
    "version": "v4",
    "sessionInfoVersion": "3",
    "featureType": "whatsapp_business_app_onboarding",
}


def build_connect_url(organization_id: int) -> str:
    """The Meta-hosted Embedded Signup URL to send the tenant to.

    The redirect back is configured on the Meta app itself (Redirect URI
    settings), not passed here — which is why whatsapp_redirect_uri() must keep
    matching what is registered there.

    `state` is appended in the hope Meta echoes it back, but nothing depends on
    it: /connect takes the organization from the SESSION and treats state only
    as a cross-check. That was the right call for security reasons and it pays
    off here too — a flow that silently drops state still works.
    """
    app_id, _ = _app_credentials()
    config_id = (getattr(settings, "WHATSAPP_ES_CONFIG_ID", "") or "").strip()
    if not config_id:
        raise WhatsAppError("WHATSAPP_ES_CONFIG_ID is not configured")

    query = urlencode({
        "app_id": app_id,
        "config_id": config_id,
        "extras": json.dumps(_ES_EXTRAS, separators=(",", ":")),
        "state": make_state(organization_id),
    })
    return f"{_ES_LANDING}?{query}"


def whatsapp_redirect_uri() -> str:
    """Must match the Redirect URI registered on the Meta app EXACTLY, trailing
    slash included — a mismatch fails the exchange with an error that does not
    say which side is wrong."""
    base = (getattr(settings, "FRONTEND_URL", "") or "https://pinzo.io").rstrip("/")
    return f"{base}/whatsapp/callback"


# ── Graph helpers ─────────────────────────────────────────────────────────────

def _get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT) as client:
        res = client.get(f"{GRAPH}{path}", params=params)
    body = res.json() if res.content else {}
    if res.status_code >= 400:
        _raise_meta_error(path, res.status_code, body)
    return body


def _post(path: str, token: str, payload: Optional[dict] = None) -> dict[str, Any]:
    with httpx.Client(timeout=TIMEOUT) as client:
        res = client.post(f"{GRAPH}{path}",
                          headers={"Authorization": f"Bearer {token}"},
                          json=payload or {})
    body = res.json() if res.content else {}
    if res.status_code >= 400:
        _raise_meta_error(path, res.status_code, body)
    return body


def exchange_code(code: str) -> str:
    """Short-lived signup code -> the client's business access token."""
    app_id, app_secret = _app_credentials()
    body = _get("/oauth/access_token", {
        "client_id": app_id,
        "client_secret": app_secret,
        "code": code,
        "redirect_uri": whatsapp_redirect_uri(),
    })
    token = body.get("access_token")
    if not token:
        raise WhatsAppError(f"Meta returned no access token for that code: {body}")
    return token


def discover_waba(business_token: str) -> Optional[str]:
    """Which WABA this token actually grants access to.

    Read from Meta's own view of the token rather than from anything the
    browser sent us: the granted scope is the authority on what we may touch,
    and a client-supplied id could point anywhere.
    """
    app_id, app_secret = _app_credentials()
    body = _get("/debug_token", {
        "input_token": business_token,
        "access_token": f"{app_id}|{app_secret}",
    })
    scopes = ((body.get("data") or {}).get("granular_scopes")) or []
    for scope in scopes:
        if scope.get("scope") == "whatsapp_business_management":
            targets = scope.get("target_ids") or []
            if targets:
                return str(targets[0])
    return None


def fetch_phone_numbers(waba_id: str, token: str) -> list[dict[str, Any]]:
    body = _get(f"/{waba_id}/phone_numbers", {"access_token": token})
    return body.get("data") or []


def subscribe_app(waba_id: str, token: str) -> None:
    """Subscribe our app to the client's WABA.

    Without this, their webhooks go nowhere — no delivery receipts, no read
    receipts, no marketing opt-outs. Nothing errors; the events simply never
    arrive, which is why it is done here rather than left to a later screen.
    """
    _post(f"/{waba_id}/subscribed_apps", token)


def register_number(phone_number_id: str, token: str, pin: Optional[str] = None) -> str:
    """Activate the number for Cloud API sending. Returns the PIN used.

    The PIN is two-factor for the number itself and is required again if the
    number is ever re-registered, so the caller stores it. Generated rather
    than asked for: a tenant inventing one will not remember it either.
    """
    pin = pin or f"{secrets.randbelow(1000000):06d}"
    _post(f"/{phone_number_id}/register", token,
          {"messaging_product": "whatsapp", "pin": pin})
    return pin


def ensure_review_template(waba_id: str, token: str, redirect_base: str) -> dict[str, Any]:
    """Create the review-request template on the tenant's WABA.

    The button's base URL is fixed at approval time and only its suffix varies,
    which is exactly why it points at Pinzo and not at Google: one approved
    template then serves every location the tenant owns.
    """
    payload = {
        "name": REVIEW_TEMPLATE_NAME,
        "language": "en",
        "category": "MARKETING",
        "components": [
            {
                "type": "BODY",
                "text": ("Hi {{1}}, thank you for choosing {{2}}! If we looked after you well, "
                         "would you mind leaving us a quick Google review? It takes about 30 "
                         "seconds and genuinely helps our team."),
                "example": {"body_text": [["Rahul", "Lucira Jewellery"]]},
            },
            {"type": "FOOTER", "text": "Reply STOP to opt out."},
            {
                "type": "BUTTONS",
                "buttons": [{
                    "type": "URL",
                    "text": "Leave a review",
                    "url": f"{redirect_base}/r/{{{{1}}}}",
                    "example": [f"{redirect_base}/r/abc123"],
                }],
            },
        ],
    }
    try:
        return _post(f"/{waba_id}/message_templates", token, payload)
    except WhatsAppError as err:
        # Meta reuses subcode 2388023 for two very different situations, and the
        # generic message ("Invalid parameter") distinguishes neither.
        text = f"{err.user_title or ''} {err.user_msg or ''} {err}".lower()
        if "already exists" in text:
            # Not a failure: a tenant reconnecting must not be blocked by their
            # own previous onboarding.
            logger.info("[wa-onboarding] template already exists on WABA %s", waba_id)
            return {"status": "EXISTS"}
        if "being deleted" in text:
            # Meta holds a deleted template's name for ~a minute before the
            # language slot frees up. Transient, and worth saying so plainly —
            # the alternative is a user retrying blind.
            raise WhatsAppError(
                "This template was recently deleted and Meta is still clearing the name. "
                "Wait about a minute and try again.",
                code=err.code, subcode=err.subcode,
            ) from err
        raise


def ensure_review_template_versioned(waba_id: str, token: str, redirect_base: str,
                                     max_versions: int = 6) -> tuple[str, dict[str, Any]]:
    """Create the review template, falling forward to a new version name.

    Meta does not allow editing an APPROVED template through the API, and it
    holds a deleted template's name in a "being deleted" state for a while
    afterwards. Both mean the canonical name can be unusable at the exact moment
    a tenant clicks the button. Rather than surface that as a failure, take the
    next free version — the name lives on the account row, so which one is in
    use is a stored fact, not a constant.

    Returns (name_used, meta_response).
    """
    global REVIEW_TEMPLATE_NAME
    base = REVIEW_TEMPLATE_NAME
    original = base

    for version in range(1, max_versions + 1):
        candidate = base if version == 1 else f"{base}_v{version}"
        REVIEW_TEMPLATE_NAME = candidate
        try:
            result = ensure_review_template(waba_id, token, redirect_base)
            if result.get("status") == "EXISTS":
                # Already there and usable — nothing to create.
                return candidate, result
            return candidate, result
        except WhatsAppError as err:
            # Match on Meta's SUBCODE, not prose: 2388023 covers both
            # "already exists" and "being deleted", and the message text gets
            # rewritten on the way up (which is exactly what broke the first
            # version of this check).
            text = f"{err.user_title or ''} {err.user_msg or ''} {err}".lower()
            name_unavailable = (
                err.subcode == 2388023
                or "already exists" in text
                or "deleted" in text
            )
            if name_unavailable:
                continue                      # that name is unusable; try the next
            raise
        finally:
            REVIEW_TEMPLATE_NAME = original

    raise WhatsAppError(
        "Could not create the message template — every name variant is currently "
        "held by Meta. This clears on its own; try again in a few minutes."
    )


def complete_signup(db, organization_id: int, code: str) -> WhatsAppAccount:
    """Run the whole sequence and persist the result.

    Partial success is normal and is stored as a status rather than rolled back:
    a tenant whose number registered but whose template is still pending should
    see "template pending", not "connection failed".
    """
    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.organization_id == organization_id,
    ).first()
    if not account:
        account = WhatsAppAccount(organization_id=organization_id)
        db.add(account)

    token = exchange_code(code)
    account.access_token = encrypt_token(token)
    account.connected_at = account.connected_at or datetime.now(timezone.utc)
    account.status = WhatsAppAccount.STATUS_CONNECTED
    account.status_detail = None
    db.commit()

    waba_id = discover_waba(token)
    if not waba_id:
        account.status_detail = ("Meta did not grant access to a WhatsApp Business Account. "
                                 "Re-run the connection and make sure an account is selected.")
        db.commit()
        return account
    account.waba_id = waba_id

    numbers = fetch_phone_numbers(waba_id, token)
    if numbers:
        account.phone_number_id = str(numbers[0].get("id") or "")
        account.display_phone_number = numbers[0].get("display_phone_number")
        account.verified_name = numbers[0].get("verified_name")
        account.quality_rating = numbers[0].get("quality_rating")
    db.commit()

    try:
        subscribe_app(waba_id, token)
    except WhatsAppError as err:
        # Not fatal to the connection, but it does mean no delivery receipts —
        # say so plainly rather than letting it look healthy.
        logger.warning("[wa-onboarding] subscribe failed for %s: %s", waba_id, err)
        account.status_detail = f"Connected, but webhook subscription failed: {err}"

    if account.phone_number_id:
        try:
            register_number(account.phone_number_id, token)
            account.status = WhatsAppAccount.STATUS_NUMBER_REGISTERED
        except WhatsAppError as err:
            account.status_detail = (
                f"The number could not be registered: {err}. This usually means it is still "
                "in use in the WhatsApp or WhatsApp Business app — delete it there first."
            )
            db.commit()
            return account
    db.commit()

    try:
        result = ensure_review_template(waba_id, token, _redirect_base())
        account.template_name = REVIEW_TEMPLATE_NAME
        account.template_status = result.get("status") or "PENDING"
        account.status = (WhatsAppAccount.STATUS_READY
                          if account.template_status in ("APPROVED", "EXISTS")
                          else WhatsAppAccount.STATUS_TEMPLATE_PENDING)
        if account.status == WhatsAppAccount.STATUS_TEMPLATE_PENDING:
            account.status_detail = ("Your review template is with Meta for approval — "
                                     "usually under an hour. Sending unlocks automatically.")
    except WhatsAppError as err:
        account.status_detail = f"Template creation failed: {err}"

    account.last_synced_at = datetime.now(timezone.utc)
    db.commit()
    return account


def _redirect_base() -> str:
    """Where the template's button points.

    Prefers REVIEW_LINK_BASE_URL over FRONTEND_URL: a template's button URL is
    frozen when Meta approves it, so one created on a dev machine would embed
    http://localhost:3000 forever and be unusable in production.
    """
    base = (getattr(settings, "REVIEW_LINK_BASE_URL", "")
            or getattr(settings, "FRONTEND_URL", "")
            or "https://pinzo.io")
    return base.rstrip("/")
