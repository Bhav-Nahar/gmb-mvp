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
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_feature
from app.core import plan_config
from app.db.session import get_db
from app.models.review_request import ReviewRequest
from app.models.user import User
from app.models.whatsapp_account import WhatsAppAccount
from app.models.whatsapp_message import WhatsAppMessage
from app.services import review_request_service, whatsapp_service
from app.services.whatsapp_service import WhatsAppError

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[
    Depends(require_feature(plan_config.FEATURE_REVIEW_REQUESTS)),
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

    # Names come from review requests — the only place a customer name is ever
    # captured. Ordered ascending so the newest upload overwrites and wins.
    names: dict[str, str] = {}
    for phone, name in (db.query(ReviewRequest.phone, ReviewRequest.customer_name)
                        .filter(ReviewRequest.organization_id == org_id,
                                ReviewRequest.phone.in_(phones),
                                ReviewRequest.customer_name.isnot(None))
                        .order_by(ReviewRequest.created_at.asc()).all()):
        names[phone] = name

    previews: dict[str, str] = {}
    for phone, body in (db.query(WhatsAppMessage.phone, WhatsAppMessage.body)
                        .filter(WhatsAppMessage.organization_id == org_id,
                                WhatsAppMessage.phone.in_(phones))
                        .order_by(WhatsAppMessage.created_at.asc()).all()):
        if body:
            previews[phone] = body

    return [
        Conversation(
            phone=r["phone"],
            customer_name=names.get(r["phone"]),
            last_message=previews.get(r["phone"]),
            last_message_at=r["last_message_at"],
            last_inbound_at=r["last_inbound_at"],
            window_open=_window_open(r["last_inbound_at"]),
            suppressed=review_request_service.is_suppressed(db, org_id, r["phone"]),
        )
        for r in ordered
    ]


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


@router.post("/conversations/{phone}/reply", response_model=Message,
             status_code=status.HTTP_201_CREATED)
def reply(
    phone: str,
    payload: ReplyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Send a free-form reply, inside the 24-hour window only."""
    org_id = current_user.organization_id
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
