"""WhatsApp connection for an organization (Embedded Signup).

Admin-only: connecting a WhatsApp Business Account authorises Pinzo to send
messages that bill the organization's own Meta payment method, so it is not a
choice an ordinary member should be able to make.

The callback is deliberately NOT here — Meta redirects the browser back to the
frontend (pinzo.io/whatsapp/callback), which posts the code to /connect below.
Keeping the exchange server-side means the code never round-trips through a
page the customer could bookmark or share.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import admin_required, get_current_user, require_feature
from app.core import plan_config
from app.core.security import decrypt_token
from app.db.session import get_db
from app.models.user import User
from app.models.whatsapp_account import WhatsAppAccount
from app.services import whatsapp_onboarding_service as onboarding
from app.services.whatsapp_service import WhatsAppError

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectStart(BaseModel):
    url: str


class ConnectComplete(BaseModel):
    code: str
    state: str | None = None


class WhatsAppStatus(BaseModel):
    connected: bool
    status: str
    status_detail: str | None = None
    display_phone_number: str | None = None
    verified_name: str | None = None
    quality_rating: str | None = None
    messaging_tier: str | None = None
    template_status: str | None = None
    can_send: bool


@router.get("/connect-url", response_model=ConnectStart,
             dependencies=[Depends(require_feature(plan_config.FEATURE_REVIEW_REQUESTS))])
def get_connect_url(current_user: User = Depends(admin_required)):
    """Where to send the admin to start Meta's hosted signup."""
    try:
        return ConnectStart(url=onboarding.build_connect_url(current_user.organization_id))
    except WhatsAppError as err:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(err))


@router.post("/connect", response_model=WhatsAppStatus,
             dependencies=[Depends(require_feature(plan_config.FEATURE_REVIEW_REQUESTS))])
def complete_connect(
    payload: ConnectComplete,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    """Exchange the signup code and run onboarding.

    The organization comes from the SESSION, not from the signed state — the
    state is a cross-check, not the authority, so a replayed code can never
    attach an account to a different organization than the one logged in.
    """
    if payload.state:
        state_org = onboarding.read_state(payload.state)
        if state_org is not None and state_org != current_user.organization_id:
            logger.warning("[whatsapp] state org %s != session org %s",
                           state_org, current_user.organization_id)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="This connection was started by a different account.")

    try:
        account = onboarding.complete_signup(db, current_user.organization_id, payload.code)
    except WhatsAppError as err:
        logger.error("[whatsapp] connect failed for org %s: %s",
                     current_user.organization_id, err)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(err))

    return _to_status(account)


class TemplateResult(BaseModel):
    template_name: str
    template_status: str
    created: bool
    message: str


@router.post("/template", response_model=TemplateResult,
             dependencies=[Depends(require_feature(plan_config.FEATURE_REVIEW_REQUESTS))])
def create_template(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    """Create the review-request template on this organization's WABA.

    A button, not an editor. Pinzo authors the copy — the tenant cannot write
    their own — because template text is a policy surface: incentivised wording
    ("review us for 10% off") breaches Google's review policy AND reads as
    marketing spam to Meta, and the tenant's own number pays for both. The
    structure is equally load-bearing: two body variables and a dynamic URL
    button whose suffix is the recipient token. Change either and sends fail.

    Onboarding already does this automatically; this exists for the cases where
    that isn't enough — a template Meta rejected, one deleted by mistake, or a
    tenant connected before the template existed.
    """
    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.organization_id == current_user.organization_id,
    ).first()
    if not account or not account.waba_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Connect WhatsApp before creating the message template.")

    try:
        name, result = onboarding.ensure_review_template_versioned(
            account.waba_id, decrypt_token(account.access_token), onboarding._redirect_base(),
        )
    except WhatsAppError as err:
        logger.error("[whatsapp] template creation failed for org %s: %s",
                     current_user.organization_id, err)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(err))

    existed = result.get("status") == "EXISTS"
    new_status = "APPROVED" if existed else (result.get("status") or "PENDING")

    # Do NOT repoint a working account at a PENDING template: sends use
    # account.template_name, so switching to one Meta hasn't approved yet would
    # silently break sending for however long the review takes. Keep the
    # approved one in service; the hourly sync (or the webhook) promotes the new
    # one once it is approved.
    had_working_template = (account.template_status == "APPROVED" and account.template_name)
    if not had_working_template or new_status == "APPROVED":
        account.template_name = name
        account.template_status = new_status
        if account.status == WhatsAppAccount.STATUS_NUMBER_REGISTERED:
            account.status = (WhatsAppAccount.STATUS_READY if new_status == "APPROVED"
                              else WhatsAppAccount.STATUS_TEMPLATE_PENDING)
    db.commit()

    return TemplateResult(
        template_name=account.template_name,
        template_status=account.template_status,
        created=not existed,
        message=(
            "This template already exists on your WhatsApp account."
            if existed else
            f"Template '{name}' submitted to Meta for approval — usually under an hour. "
            + ("Your current approved template stays in use until then."
               if had_working_template else
               "Sending unlocks automatically once it's approved.")
        ),
    )


@router.get("/status", response_model=WhatsAppStatus)
def get_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Current connection state, for the settings screen.

    Readable by any member: the send limit and quality rating explain why a
    campaign is paced the way it is, and hiding that from non-admins just
    generates questions for the admin.
    """
    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.organization_id == current_user.organization_id,
    ).first()
    if not account:
        return WhatsAppStatus(connected=False, status="not_connected", can_send=False)
    return _to_status(account)


@router.delete("/disconnect", status_code=status.HTTP_204_NO_CONTENT,
             dependencies=[Depends(require_feature(plan_config.FEATURE_REVIEW_REQUESTS))])
def disconnect(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    """Forget the stored credentials.

    Deletes our copy only — the client's WABA, number and templates are theirs
    and stay untouched on Meta, which is the correct behaviour for something we
    never owned.
    """
    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.organization_id == current_user.organization_id,
    ).first()
    if account:
        db.delete(account)
        db.commit()
    return None


def _to_status(account: WhatsAppAccount) -> WhatsAppStatus:
    return WhatsAppStatus(
        connected=True,
        status=account.status,
        status_detail=account.status_detail,
        display_phone_number=account.display_phone_number,
        verified_name=account.verified_name,
        quality_rating=account.quality_rating,
        messaging_tier=account.messaging_tier,
        template_status=account.template_status,
        can_send=account.can_send,
    )
