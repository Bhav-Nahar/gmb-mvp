"""Review-request campaigns: send to a list, upload a CSV, read the results.

Sending is always enqueued, never done in the request. A batch is paced at a
couple of seconds per message to protect the tenant's quality rating, so even a
modest list outlives an HTTP request — and a timeout mid-send would leave nobody
able to say which customers were messaged.

The consent checkbox is not decoration. WhatsApp requires opt-in from the
recipient, and the difference between a legitimate customer list and a purchased
one is invisible to us and to Meta until the complaints arrive. Recording who
confirmed it, and when, is what makes that answerable later.
"""
import csv
import io
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import (admin_required, get_current_user, get_user_location_ids,
                          staff_required)
from app.core.authorization import assert_location_access
from app.db.session import get_db
from app.models.activity_log import ActivityLog
from app.models.location import Location
from app.models.review import Review
from app.models.review_request import ReviewRequest
from app.models.user import User
from app.models.review_suppression import ReviewSuppression
from app.models.whatsapp_account import WhatsAppAccount
from app.services import review_request_service as rr
# Message accounting lives with the sender, not here: the batch task enforces the
# same ceiling this endpoint displays, and two copies of "what counts as billable"
# would drift apart immediately.
from app import tasks_whatsapp as wa_tasks
# Dispatch through the CONFIGURED app instance, exactly as every other endpoint
# here does. Not task.delay(): FastAPI runs sync endpoints in a threadpool, and
# Celery's current_app is thread-local — in a worker thread @shared_task
# resolves to the auto-created default app and publishes to amqp://localhost,
# which fails as "[Errno 111] Connection refused" and looks like Redis is down.
from app.worker import celery

logger = logging.getLogger(__name__)
router = APIRouter()

# One upload is one campaign. Beyond this it is not a customer list any more,
# and a tenant's first send should not be their biggest.
MAX_RECIPIENTS = 2000

# Header names people actually use. Matched case-insensitively so a file
# exported from anywhere has a chance of working without editing.
PHONE_HEADERS = {"phone", "mobile", "number", "phone number", "contact", "whatsapp"}
NAME_HEADERS = {"name", "customer", "customer name", "first name", "full name"}


class Recipient(BaseModel):
    phone: str
    name: Optional[str] = None


class SendRequest(BaseModel):
    location_id: int
    recipients: list[Recipient] = Field(min_length=1)
    # Deliberately required and defaulted to False: an attestation you can
    # forget to make is not an attestation.
    consent_confirmed: bool = False


class SendAccepted(BaseModel):
    batch_id: str
    queued: int
    # Set when the campaign lands inside quiet hours and the first message waits
    # until morning. Both entry points return it — the CSV upload never calls
    # preflight, so it has no other way to learn this.
    starts_at: Optional[datetime] = None


class CampaignStats(BaseModel):
    total: int
    sent: int
    delivered: int
    read: int
    clicked: int
    failed: int
    skipped: int
    click_rate: float
    # Google never says who left a review, so this is the location's total over
    # the same window — an outcome, not an attribution. Stated that way in the UI.
    reviews_in_period: Optional[int] = None


def _scope(db: Session, user: User, q, column, location_id: Optional[int]):
    """Restrict a read query to the locations this user may see.

    An explicit location_id is authorized outright (403 if it isn't theirs) rather
    than silently filtered to nothing — a Store Manager poking at another store's
    id deserves an answer, not an empty list that reads like "no campaigns yet".
    """
    if location_id:
        assert_location_access(db, user, location_id)
        return q.filter(column == location_id)
    allowed = get_user_location_ids(user, db)  # None = whole org (Owner/Admin)
    return q if allowed is None else q.filter(column.in_(allowed))


def _guard(db: Session, user: User, location_id: int) -> Location:
    # Store/Regional Managers send for their OWN stores only. Owners and Admins
    # pass through unrestricted; the org filter below still applies to everyone.
    assert_location_access(db, user, location_id)

    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == user.organization_id,
    ).first()
    if not location:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")

    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.organization_id == user.organization_id,
    ).first()
    if not account or not account.can_send:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail=_not_ready_reason(account))
    return location


# Each blocker names the ONE thing to do next. "WhatsApp is not ready" sends a
# tenant to support; "send yourself a test message first" does not.
def _not_ready_reason(account: Optional[WhatsAppAccount]) -> str:
    if not account:
        return "Connect WhatsApp in Settings before sending review requests."
    blocker = account.setup_blocker
    if blocker == "webhooks":
        return ("Pinzo isn't receiving updates from your WhatsApp account yet, so opt-outs and "
                "delivery reports would be lost. Open Settings → WhatsApp and press "
                "“Check again”.")
    if blocker == "test_send":
        return ("Send yourself a test message first — Settings → WhatsApp. It's one message, "
                "and it proves your Meta payment method and template work before your "
                "customers see anything.")
    return (account.status_detail
            or "WhatsApp isn't ready yet — see Settings → WhatsApp.")


def _dispatch(db: Session, user: User, location: Location,
              recipients: list[dict], source: str) -> SendAccepted:
    # Duplicates inside one upload are the same person twice, not two customers.
    # Left in, they would each consume a send and the second would be capped
    # anyway — noise in the report for no benefit.
    seen: set[str] = set()
    unique: list[dict] = []
    for row in recipients:
        key = "".join(ch for ch in str(row.get("phone", "")) if ch.isdigit())
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(row)

    if not unique:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No usable phone numbers were found.")
    if len(unique) > MAX_RECIPIENTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"That's {len(unique)} numbers — the limit per campaign is {MAX_RECIPIENTS}.",
        )

    batch_id = f"rr_{uuid.uuid4().hex[:12]}"

    # The consent record. Stored on the existing activity log rather than a new
    # table: it is an audit fact about a user action, which is what that log is.
    db.add(ActivityLog(
        organization_id=user.organization_id,
        location_id=location.id,
        actor_user_id=user.id,
        entity_type="ReviewCampaign",
        action="whatsapp_review_campaign_started",
        payload={
            "batch_id": batch_id,
            "recipients": len(unique),
            "source": source,
            # WHO confirmed consent and WHEN. The whole point of writing this is
            # to be able to answer that months later, when someone asks.
            "consent_confirmed": True,
            "confirmed_by_user_id": user.id,
            "confirmed_at": datetime.now(timezone.utc).isoformat(),
        },
    ))
    db.commit()

    celery.send_task(
        "app.tasks_whatsapp.send_review_batch_task",
        kwargs={
            "organization_id": user.organization_id,
            "location_id": location.id,
            "recipients": unique,
            "batch_id": batch_id,
            "source": source,
        },
    )
    logger.info("[review-campaign] queued %s (%s recipients) for org %s",
                batch_id, len(unique), user.organization_id)
    # The task itself re-checks and defers; this is only what the UI promises.
    delay = wa_tasks.seconds_until_send_window()
    return SendAccepted(batch_id=batch_id, queued=len(unique),
                        starts_at=(datetime.now(timezone.utc) + timedelta(seconds=delay)
                                   if delay else None))


@router.post("/send", response_model=SendAccepted, status_code=status.HTTP_202_ACCEPTED)
def send(payload: SendRequest, db: Session = Depends(get_db),
         current_user: User = Depends(staff_required)):
    if not payload.consent_confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=("Please confirm these are your own customers who agreed to be contacted. "
                    "WhatsApp requires opt-in, and messaging a bought list will get your "
                    "number restricted."),
        )
    location = _guard(db, current_user, payload.location_id)
    return _dispatch(db, current_user, location,
                     [r.model_dump() for r in payload.recipients], "manual")


@router.post("/upload", response_model=SendAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_csv(
    location_id: int = Form(...),
    consent_confirmed: bool = Form(False),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    if not consent_confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Please confirm these are your own customers who agreed to be contacted.",
        )
    location = _guard(db, current_user, location_id)

    raw = await file.read()
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="That file is too large — please upload under 2MB.")
    try:
        text = raw.decode("utf-8-sig")     # -sig: Excel writes a BOM, which breaks the header
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="That file has no header row.")

    headers = {(h or "").strip().lower(): h for h in reader.fieldnames}
    phone_col = next((headers[h] for h in headers if h in PHONE_HEADERS), None)
    name_col = next((headers[h] for h in headers if h in NAME_HEADERS), None)
    if not phone_col:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=("No phone column found. Name one column "
                    f"{' or '.join(sorted(PHONE_HEADERS))}."),
        )

    recipients = [
        {"phone": (row.get(phone_col) or "").strip(),
         "name": (row.get(name_col) or "").strip() if name_col else None}
        for row in reader
        if (row.get(phone_col) or "").strip()
    ]
    return _dispatch(db, current_user, location, recipients, "csv")


class PreflightRequest(BaseModel):
    recipients: list[Recipient] = Field(min_length=1)


class PreflightRow(BaseModel):
    phone: str
    name: Optional[str] = None
    will_send: bool
    reason: Optional[str] = None


class Preflight(BaseModel):
    will_send: int
    will_skip: int
    rows: list[PreflightRow]
    # None when sending starts immediately. Otherwise sending is inside quiet
    # hours and the campaign will wait — the UI has to say so, or a 10pm upload
    # returns 202 and looks broken until morning.
    starts_at: Optional[datetime] = None


@router.post("/preflight", response_model=Preflight)
def preflight(payload: PreflightRequest, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    """Say what will happen BEFORE sending.

    Without this, a tenant uploads 300 numbers, sees "40 skipped" afterwards and
    suspects the product ate their list. The same three checks the sender applies
    are applied here, read-only, so the answer matches what actually happens.
    """
    org_id = current_user.organization_id
    rows: list[PreflightRow] = []
    seen: set[str] = set()
    for r in payload.recipients:
        phone = rr.normalize_phone(r.phone)
        if not phone:
            rows.append(PreflightRow(phone=r.phone, name=r.name, will_send=False,
                                     reason="Not a valid phone number"))
            continue
        if phone in seen:
            rows.append(PreflightRow(phone=phone, name=r.name, will_send=False,
                                     reason="Duplicate in this list"))
            continue
        seen.add(phone)
        if rr.is_suppressed(db, org_id, phone):
            rows.append(PreflightRow(phone=phone, name=r.name, will_send=False,
                                     reason="Opted out or on your do-not-contact list"))
        elif rr.recently_messaged(db, org_id, phone):
            rows.append(PreflightRow(phone=phone, name=r.name, will_send=False,
                                     reason=rr._cooldown_message()))
        else:
            rows.append(PreflightRow(phone=phone, name=r.name, will_send=True))

    delay = wa_tasks.seconds_until_send_window()
    return Preflight(will_send=sum(1 for r in rows if r.will_send),
                     will_skip=sum(1 for r in rows if not r.will_send),
                     rows=rows,
                     starts_at=(datetime.now(timezone.utc) + timedelta(seconds=delay)
                                if delay else None))


class HistoryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    customer_name: Optional[str] = None
    status: str
    error_detail: Optional[str] = None
    created_at: datetime
    clicked_at: Optional[datetime] = None


@router.get("/history", response_model=list[HistoryRow])
def history(location_id: Optional[int] = None, batch_id: Optional[str] = None,
            limit: int = 100, db: Session = Depends(get_db),
            current_user: User = Depends(get_current_user)):
    """Per-recipient outcomes. "Did Mrs Sharma get her message" is the question
    support actually gets asked, and aggregate counts cannot answer it."""
    q = db.query(ReviewRequest).filter(
        ReviewRequest.organization_id == current_user.organization_id)
    q = _scope(db, current_user, q, ReviewRequest.location_id, location_id)
    if batch_id:
        q = q.filter(ReviewRequest.batch_id == batch_id)
    return q.order_by(ReviewRequest.id.desc()).limit(min(limit, 500)).all()


class SuppressionRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    reason: str
    note: Optional[str] = None
    created_at: datetime


class SuppressionCreate(BaseModel):
    phone: str
    note: Optional[str] = None


@router.get("/suppressions", response_model=list[SuppressionRow])
def list_suppressions(db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    return db.query(ReviewSuppression).filter(
        ReviewSuppression.organization_id == current_user.organization_id,
    ).order_by(ReviewSuppression.id.desc()).limit(1000).all()


@router.post("/suppressions", response_model=SuppressionRow,
             status_code=status.HTTP_201_CREATED)
def add_suppression(payload: SuppressionCreate, db: Session = Depends(get_db),
                    current_user: User = Depends(admin_required)):
    phone = rr.normalize_phone(payload.phone)
    if not phone:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="That doesn't look like a phone number.")
    rr.suppress(db, current_user.organization_id, phone,
                ReviewSuppression.REASON_MANUAL, note=payload.note)
    row = db.query(ReviewSuppression).filter(
        ReviewSuppression.organization_id == current_user.organization_id,
        ReviewSuppression.phone == phone,
    ).first()
    return row


@router.delete("/suppressions/{suppression_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_suppression(suppression_id: int, db: Session = Depends(get_db),
                       current_user: User = Depends(admin_required)):
    """Only manual entries can be removed. An opt-out is the recipient's
    decision, not the tenant's — letting it be deleted would turn a compliance
    record into a formality and put the tenant's number at risk."""
    row = db.query(ReviewSuppression).filter(
        ReviewSuppression.id == suppression_id,
        ReviewSuppression.organization_id == current_user.organization_id,
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if row.reason == ReviewSuppression.REASON_OPT_OUT:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=("This customer asked to stop receiving messages, so they can't be "
                    "removed from the list."),
        )
    db.delete(row)
    db.commit()


class UsageMonth(BaseModel):
    month: str
    billable_messages: int
    monthly_limit: int
    remaining: int
    billed_by: str
    note: str


@router.get("/usage", response_model=UsageMonth)
def usage(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Messages Meta will bill this org for, this calendar month, and the ceiling.

    Pinzo charges a flat subscription and takes no cut of messaging — Meta bills
    the tenant directly on their own WhatsApp account. This number is therefore
    an estimate for the tenant's own planning, not an invoice: it counts what we
    handed to Meta, and Meta's own price per message is the authority.

    Reminders are counted. Each one is a separately billed message, and leaving
    them out under-reported the tenant's bill by up to three times — the fastest
    way to lose someone's trust is for their card to be charged more than we
    showed them.
    """
    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.organization_id == current_user.organization_id,
    ).first()
    count = wa_tasks.billable_this_month(db, current_user.organization_id)
    limit = wa_tasks.monthly_limit(account) if account else wa_tasks.DEFAULT_MONTHLY_LIMIT

    return UsageMonth(
        month=datetime.now(timezone.utc).strftime("%B %Y"),
        billable_messages=count,
        monthly_limit=limit,
        remaining=max(0, limit - count),
        billed_by="Meta",
        note=("Meta bills these to your WhatsApp Business Account at their marketing-message "
              "rate, reminders included \u2014 each one is a separate message. Pinzo adds no markup "
              "and takes no per-message fee. Sending stops at the monthly limit above so a "
              "mistaken upload can't run up your Meta bill. See exact charges in "
              "WhatsApp Manager \u2192 Insights."),
    )


@router.get("/stats", response_model=CampaignStats)
def stats(location_id: Optional[int] = None, batch_id: Optional[str] = None, days: int = 30,
          db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Counts for a campaign or a location.

    Click rate is measured against messages that were actually DELIVERED, not
    everything queued — dividing by sends that failed or were skipped would
    understate the campaign and hide a delivery problem behind a content one.
    """
    q = db.query(ReviewRequest.status, func.count(ReviewRequest.id)).filter(
        ReviewRequest.organization_id == current_user.organization_id,
    )
    q = _scope(db, current_user, q, ReviewRequest.location_id, location_id)
    if batch_id:
        q = q.filter(ReviewRequest.batch_id == batch_id)
    else:
        q = q.filter(ReviewRequest.created_at >= datetime.now(timezone.utc) - timedelta(days=days))

    counts = dict(q.group_by(ReviewRequest.status).all())
    clicked = counts.get(ReviewRequest.STATUS_CLICKED, 0)
    delivered = (counts.get(ReviewRequest.STATUS_DELIVERED, 0)
                 + counts.get(ReviewRequest.STATUS_READ, 0) + clicked)

    since = datetime.now(timezone.utc) - timedelta(days=days)
    rq = db.query(func.count(Review.id)).filter(
        Review.organization_id == current_user.organization_id,
        Review.review_created_at >= since,
    )
    rq = _scope(db, current_user, rq, Review.location_id, location_id)

    return CampaignStats(
        reviews_in_period=rq.scalar() or 0,
        total=sum(counts.values()),
        sent=counts.get(ReviewRequest.STATUS_SENT, 0),
        delivered=delivered,
        read=counts.get(ReviewRequest.STATUS_READ, 0) + clicked,
        clicked=clicked,
        failed=counts.get(ReviewRequest.STATUS_FAILED, 0),
        skipped=counts.get(ReviewRequest.STATUS_SKIPPED, 0),
        click_rate=round(clicked / delivered * 100, 1) if delivered else 0.0,
    )
