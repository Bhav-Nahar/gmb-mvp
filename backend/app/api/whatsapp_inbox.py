"""The WhatsApp inbox: read customer replies and answer them.

Two tables feed one thread. Outbound review requests live in `review_requests`
(they have their own delivery lifecycle, click tracking and token), everything
else lives in `whatsapp_messages`. They are merged here on read rather than
copied at write time — copying would mean two sources of truth for the same
message plus a backfill, and the merge is a sort.

The 24-hour rule is the thing to understand before changing anything here.
WhatsApp only permits free-form text within 24 hours of the customer's last
inbound message. Outside that window Meta rejects the send, so the API reports
`window_open` on every conversation and refuses the reply rather than letting
the UI discover it as a 400 from Meta.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.api.deps import admin_required, get_current_user, require_feature
from app.core import plan_config
from app.core.rate_limit import rate_limiter
from app.db.session import get_db
from app.models.review_request import ReviewRequest
from app.models.review_suppression import ReviewSuppression
from app.models.user import User
from app.models.whatsapp_account import WhatsAppAccount
from app.models.whatsapp_message import WhatsAppMessage
from app.services import review_request_service, whatsapp_service
from app.services.whatsapp_service import WhatsAppError, normalize_phone

logger = logging.getLogger(__name__)

# Owner/Admin only, for the whole router — reads included.
#
# A conversation here is (organization, phone) and carries NO location, because
# the WABA is one org-level number and a cold inbound belongs to no store. So
# there is no honest way to scope this inbox the way review campaigns scope
# themselves (`review_campaigns._scope`): any store-level role admitted here
# would read every customer in the org, including stores they do not manage.
# Everything else that acts on the tenant's WhatsApp number is already
# `admin_required` (see api/whatsapp.py), and this is stricter than that needs
# to be rather than looser.
#
# Widening this to let managers answer is a one-line change to `staff_required`
# — but it should be a deliberate decision about who may read customer messages,
# not a default.
router = APIRouter(dependencies=[
    Depends(require_feature(plan_config.FEATURE_REVIEW_REQUESTS)),
    Depends(admin_required),
])

WINDOW = timedelta(hours=24)

# One page of a thread. Long enough that nobody scrolls in practice, small
# enough that a runaway automation cannot return a megabyte.
THREAD_LIMIT = 200


class Message(BaseModel):
    id: str            # "m123" or "r123" — the two tables have colliding integer ids
    direction: str     # in | out
    body: str | None
    message_type: str
    status: str
    created_at: datetime
    # Set on review requests only, so the UI can label them as such instead of
    # showing an ordinary outbound bubble.
    kind: str = "message"


class Conversation(BaseModel):
    phone: str
    customer_name: str | None = None
    last_message: str | None = None
    last_message_at: datetime | None = None
    last_inbound_at: datetime | None = None
    window_open: bool
    suppressed: bool = False


class ReplyIn(BaseModel):
    body: str


def _account(db: Session, org_id: int) -> WhatsAppAccount:
    account = db.query(WhatsAppAccount).filter(
        WhatsAppAccount.organization_id == org_id,
    ).first()
    if not account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="WhatsApp is not connected for this organization")
    return account


def _window_open(last_inbound_at: Optional[datetime]) -> bool:
    if not last_inbound_at:
        return False
    # Postgres returns tz-aware, SQLite (tests) returns naive. Assume UTC for the
    # naive case rather than letting the subtraction raise.
    if last_inbound_at.tzinfo is None:
        last_inbound_at = last_inbound_at.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_inbound_at < WINDOW


@router.get("/conversations", response_model=list[Conversation])
def list_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    limit: int = Query(100, ge=1, le=500),
):
    """Every number this organization has exchanged messages with, newest first.

    A number that only ever received a review request and never replied still
    appears — a tenant looking for "did Ravi answer?" needs to find the thread
    whether or not there is an answer in it.
    """
    org_id = current_user.organization_id

    # Aggregate each side separately, then fold in Python. A UNION of two tables
    # with different shapes, grouped and re-sorted, is the kind of SQL that gets
    # rewritten wrong the first time someone touches it.
    rows: dict[str, dict[str, Any]] = {}

    msgs = (
        db.query(
            WhatsAppMessage.phone,
            func.max(WhatsAppMessage.created_at).label("last_at"),
            func.max(WhatsAppMessage.created_at).filter(
                WhatsAppMessage.direction == WhatsAppMessage.DIRECTION_IN
            ).label("last_in"),
        )
        .filter(WhatsAppMessage.organization_id == org_id)
        .group_by(WhatsAppMessage.phone)
        .all()
    )
    for phone, last_at, last_in in msgs:
        rows[phone] = {"phone": phone, "last_message_at": last_at, "last_inbound_at": last_in}

    reqs = (
        db.query(
            ReviewRequest.phone,
            func.max(ReviewRequest.created_at).label("last_at"),
        )
        .filter(ReviewRequest.organization_id == org_id)
        .group_by(ReviewRequest.phone)
        .all()
    )
    for phone, last_at in reqs:
        row = rows.setdefault(phone, {"phone": phone, "last_message_at": None,
                                      "last_inbound_at": None})
        if not row["last_message_at"] or last_at > row["last_message_at"]:
            row["last_message_at"] = last_at

    epoch = datetime.min.replace(tzinfo=timezone.utc)
    ordered = sorted(rows.values(),
                     key=lambda r: r["last_message_at"] or epoch,
                     reverse=True)[:limit]
    if not ordered:
        return []

    phones = [r["phone"] for r in ordered]

    # The three lookups below all take the same shape on purpose: group to one
    # row per phone in SQL, then join back. Fetching every row for these phones
    # and folding in Python is what this used to do, and it grew linearly with a
    # tenant's history on a query the UI runs every 15 seconds.
    previews = _latest_per_phone(
        db, WhatsAppMessage, WhatsAppMessage.body, org_id, phones)

    # Names come from review requests — the only place a customer name is ever
    # captured. Latest upload wins.
    names = _latest_per_phone(
        db, ReviewRequest, ReviewRequest.customer_name, org_id, phones,
        extra=ReviewRequest.customer_name.isnot(None))

    # One query, not one per conversation.
    suppressed = {
        row[0] for row in db.query(ReviewSuppression.phone).filter(
            ReviewSuppression.organization_id == org_id,
            ReviewSuppression.phone.in_(phones),
        ).all()
    }

    return [
        Conversation(
            phone=r["phone"],
            customer_name=names.get(r["phone"]),
            last_message=previews.get(r["phone"]),
            last_message_at=r["last_message_at"],
            last_inbound_at=r["last_inbound_at"],
            window_open=_window_open(r["last_inbound_at"]),
            suppressed=r["phone"] in suppressed,
        )
        for r in ordered
    ]


def _latest_per_phone(db: Session, model, column, org_id: int,
                      phones: list[str], extra=None) -> dict[str, Any]:
    """{phone: column} taken from each phone's most recent row.

    Written as a group-then-join rather than Postgres' DISTINCT ON so the same
    query runs under SQLite in the test suite. Both sides hit the
    (organization_id, phone, created_at) index, and it returns one row per
    phone instead of the tenant's whole history.
    """
    if not phones:
        return {}
    filters = [model.organization_id == org_id, model.phone.in_(phones)]
    if extra is not None:
        filters.append(extra)

    latest = (db.query(model.phone.label("phone"),
                       func.max(model.created_at).label("mx"))
              .filter(*filters).group_by(model.phone).subquery())

    rows = (db.query(model.phone, column)
            .join(latest, and_(model.phone == latest.c.phone,
                               model.created_at == latest.c.mx))
            .filter(*filters).all())
    return {phone: value for phone, value in rows if value}


@router.get("/needs-reply")
def needs_reply_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """How many conversations are waiting on the tenant, for the sidebar badge.

    "Waiting" is defined without any read state: the newest message in the
    thread is inbound, and the 24-hour window is still open. That is exactly the
    set where the tenant can still act and the clock is running, which is the
    only thing a badge should be shouting about. Read/unread would need
    per-message state and a mark-read call; this needs neither and cannot go
    stale.
    """
    org_id = current_user.organization_id
    cutoff = datetime.now(timezone.utc) - WINDOW

    rows = (db.query(
                WhatsAppMessage.phone,
                func.max(WhatsAppMessage.created_at).filter(
                    WhatsAppMessage.direction == WhatsAppMessage.DIRECTION_IN
                ).label("last_in"),
                func.max(WhatsAppMessage.created_at).filter(
                    WhatsAppMessage.direction == WhatsAppMessage.DIRECTION_OUT
                ).label("last_out"),
            )
            .filter(WhatsAppMessage.organization_id == org_id,
                    # Only threads with activity inside the window can qualify,
                    # so the scan is bounded by a day of messages rather than
                    # the tenant's whole history.
                    WhatsAppMessage.created_at >= cutoff)
            .group_by(WhatsAppMessage.phone)
            .all())

    waiting = 0
    for _phone, last_in, last_out in rows:
        if last_in is None or not _window_open(last_in):
            continue
        # Compare the two sides directly rather than testing whether the newest
        # message overall IS the newest inbound: those two timestamps can be
        # equal (SQLite truncates to the second, and a tie is possible in
        # Postgres), and an equality test then reads an answered thread as
        # unanswered. A tie counts as answered — the badge should under-nag.
        if last_out is None or last_in > last_out:
            waiting += 1
    return {"count": waiting}


@router.get("/conversations/{phone}", response_model=list[Message])
def get_thread(
    phone: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """One thread, oldest first, with sent review requests merged in.

    Without the merge the tenant sees the customer's "no it was closed when I
    came" with nothing above it and no idea what was asked.
    """
    org_id = current_user.organization_id
    # Stored E.164 has no leading '+'. Normalising means a client that passes
    # "+919..." gets its thread instead of a confusing empty one.
    phone = normalize_phone(phone) or phone
    out: list[Message] = []

    for m in (db.query(WhatsAppMessage)
              .filter(WhatsAppMessage.organization_id == org_id,
                      WhatsAppMessage.phone == phone)
              .order_by(WhatsAppMessage.created_at.desc())
              .limit(THREAD_LIMIT).all()):
        out.append(Message(
            id=f"m{m.id}", direction=m.direction, body=m.body,
            message_type=m.message_type, status=m.status, created_at=m.created_at,
        ))

    for r in (db.query(ReviewRequest)
              .filter(ReviewRequest.organization_id == org_id,
                      ReviewRequest.phone == phone,
                      # Queued and skipped requests never reached the customer,
                      # so they are not part of the conversation.
                      ReviewRequest.status.notin_([ReviewRequest.STATUS_QUEUED,
                                                   ReviewRequest.STATUS_SKIPPED]))
              .order_by(ReviewRequest.created_at.desc())
              .limit(THREAD_LIMIT).all()):
        out.append(Message(
            id=f"r{r.id}",
            direction=WhatsAppMessage.DIRECTION_OUT,
            body=None,              # the template body is not stored per-request
            message_type="template",
            status=r.status,
            created_at=r.sent_at or r.created_at,
            kind="review_request",
        ))

    out.sort(key=lambda m: m.created_at)
    return out[-THREAD_LIMIT:]


# A reply inside the 24-hour window is a service message and carries no
# per-message charge under Meta's current pricing, which is why it is not
# subject to the monthly spend ceiling that guards template sends
# (tasks_whatsapp.DEFAULT_MONTHLY_LIMIT). That makes the ceiling here a
# throughput one instead: a runaway script or a stuck retry loop would
# otherwise hammer Meta with no bound at all, and burn the tenant's quality
# rating even while each message is free. Generous enough that a human agent,
# or several, will never see it.
#
# ponytail: if Meta ever prices service messages, this needs to become a real
# spend cap counted out of whatsapp_messages, not a rate limit.
_reply_rate_limit = rate_limiter("whatsapp_inbox_reply", limit=60, window_seconds=60)


@router.post("/conversations/{phone}/reply", response_model=Message,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(_reply_rate_limit)])
def reply(
    phone: str,
    payload: ReplyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a free-form reply, inside the 24-hour window only."""
    org_id = current_user.organization_id
    phone = normalize_phone(phone) or phone
    account = _account(db, org_id)

    if account.status != WhatsAppAccount.STATUS_READY:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=account.status_detail or
                            "WhatsApp is not ready to send. Check your connection settings.")

    # An opt-out is a withdrawal of consent, not a preference weighed against
    # convenience. It outranks the open window.
    if review_request_service.is_suppressed(db, org_id, phone):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="This customer has opted out of messages from you.")

    last_in = (db.query(func.max(WhatsAppMessage.created_at))
               .filter(WhatsAppMessage.organization_id == org_id,
                       WhatsAppMessage.phone == phone,
                       WhatsAppMessage.direction == WhatsAppMessage.DIRECTION_IN)
               .scalar())
    if not _window_open(last_in):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The 24-hour reply window has closed. Send an approved template instead.")

    try:
        wamid = whatsapp_service.send_text(account, phone, payload.body)
    except WhatsAppError as err:
        logger.warning("[wa-inbox] reply failed for org %s: %s", org_id, err)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err))

    row = WhatsAppMessage(
        organization_id=org_id,
        phone=phone,
        direction=WhatsAppMessage.DIRECTION_OUT,
        body=payload.body.strip(),
        message_type="text",
        wamid=wamid,
        status=WhatsAppMessage.STATUS_SENT,
        sent_by_user_id=current_user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return Message(id=f"m{row.id}", direction=row.direction, body=row.body,
                   message_type=row.message_type, status=row.status,
                   created_at=row.created_at)
