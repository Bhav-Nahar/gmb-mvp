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
from app.models.review_request import ReviewRequest
from app.models.user import User
from app.models.whatsapp_account import WhatsAppAccount
from app.services import review_request_service, whatsapp_onboarding_service as onboarding
from app.services.whatsapp_service import WhatsAppError

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectStart(BaseModel):
    # The JS-SDK popup is the flow Meta actually supports for Embedded Signup, so
    # the browser needs these two ids. Neither is secret — both travel in the
    # signup URL either way; only the app SECRET stays server-side.
    app_id: str
    config_id: str
    graph_version: str
    # Kept as a fallback for a browser where the SDK cannot open a popup.
    url: str


class ConnectComplete(BaseModel):
    code: str
    state: str | None = None
    # "sdk" codes never touched a redirect URI, and Meta rejects an exchange that
    # claims one they did not use. Defaults to the SDK flow because that is what
    # the dashboard button does.
    source: str = "sdk"


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
    # Meta's setup being finished is not the same as being able to run a
    # campaign, and a tenant staring at "Ready" with a disabled send button
    # deserves to be told which of the two remaining steps is outstanding.
    can_test: bool = False
    webhooks_ok: bool = False
    test_send_done: bool = False
    setup_blocker: str | None = None


@router.get("/connect-url", response_model=ConnectStart,
             dependencies=[Depends(require_feature(plan_config.FEATURE_REVIEW_REQUESTS))])
def get_connect_url(current_user: User = Depends(admin_required)):
    """Where to send the admin to start Meta's hosted signup."""
    try:
        return ConnectStart(
            app_id=onboarding.app_id(),
            config_id=onboarding.es_config_id(),
            graph_version=onboarding.graph_version(),
            url=onboarding.build_connect_url(current_user.organization_id),
        )
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
        account = onboarding.complete_signup(
            db, current_user.organization_id, payload.code,
            use_redirect_uri=(payload.source != "sdk"))
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

    # An existing template reports its REAL status (ensure_review_template reads
    # it back from Meta). Assuming "exists" meant "approved" is what let an
    # account go ready on a template Meta had actually rejected.
    existed = bool(result.get("existed"))
    new_status = result.get("status") or "PENDING"

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
            f"This template already exists on your WhatsApp account ({new_status.lower()})."
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


@router.post("/recheck", response_model=WhatsAppStatus,
             dependencies=[Depends(require_feature(plan_config.FEATURE_REVIEW_REQUESTS))])
def recheck(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    """"I've fixed it at Meta — look again."

    The way out of every blocked state, and the reason none of them is a
    one-way door. Whether a WhatsApp account has a working payment method is not
    something Meta exposes to us, so a tenant who has just added one is taken at
    their word and unparked: the next send either works or parks the account
    again with the same message. Optimism costs one message; refusing to believe
    them costs a support ticket and a database edit.
    """
    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.organization_id == current_user.organization_id,
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Connect WhatsApp first.")
    try:
        onboarding.refresh_account(db, account, unpark_payment=True)
    except WhatsAppError as err:
        logger.warning("[whatsapp] recheck failed for org %s: %s",
                       current_user.organization_id, err)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(err))
    return _to_status(account)


class TestSend(BaseModel):
    phone: str
    location_id: int


class TestSendResult(BaseModel):
    ok: bool
    message: str
    status: WhatsAppStatus


@router.post("/test-send", response_model=TestSendResult,
             dependencies=[Depends(require_feature(plan_config.FEATURE_REVIEW_REQUESTS))])
def test_send(
    payload: TestSend,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required),
):
    """Send one real review request to the admin's own phone.

    This is the gate on bulk sending, and it exists because three separate
    failures are invisible until a live message goes out: no payment method on
    the tenant's WhatsApp account, a template that is approved in our records but
    not at Meta, and a number that never finished registering. Discovered here,
    it is one message and a fix-it link. Discovered by a campaign, it is 300
    failures in front of the tenant's actual customers.

    It costs the tenant one marketing message. That is the cheapest possible
    version of this check, and there is no free one — Meta has no test mode for a
    live number.
    """
    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.organization_id == current_user.organization_id,
    ).first()
    if not account or not account.can_test:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(account.status_detail if account and account.status_detail
                    else "Finish connecting WhatsApp before sending a test message."),
        )

    try:
        row = review_request_service.send_review_request(
            db,
            organization_id=current_user.organization_id,
            location_id=payload.location_id,
            phone_raw=payload.phone,
            customer_name=(current_user.name or "there").split(" ")[0],
            source="test",
            is_test=True,
        )
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    db.refresh(account)
    if row.status == ReviewRequest.STATUS_SENT:
        message = ("Test message sent. Check your WhatsApp — tap the button to confirm the "
                   "review link works, then you're clear to run a campaign.")
    else:
        message = row.error_detail or "The test message could not be sent."
    return TestSendResult(ok=row.status == ReviewRequest.STATUS_SENT,
                          message=message, status=_to_status(account))


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
        can_test=account.can_test,
        webhooks_ok=bool(account.app_subscribed),
        test_send_done=account.verified_send_at is not None,
        setup_blocker=account.setup_blocker,
    )
