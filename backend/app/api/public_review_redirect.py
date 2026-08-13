"""Public review-link redirect: /r/{token} -> that location's Google review page.

Unauthenticated by design — this is opened from a WhatsApp message by a customer
who has no Pinzo account. The token is the only credential, which is why it is
16 random bytes rather than anything derivable from the request id.

Why the hop exists at all, rather than linking straight to Google from the
WhatsApp button: Meta fixes a template's button URL at approval time and only
lets the SUFFIX vary. A Google review URL is per-location, so a direct link
would need one approved template per location. Redirecting also gives us the
click — the only per-recipient signal available, since Google never tells
anyone who left a review.
"""
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.location import Location
from app.models.review_request import ReviewRequest

logger = logging.getLogger(__name__)
router = APIRouter()


def google_review_url(location: Location) -> str | None:
    """The location's own "write a review" URL.

    Google returns this on the Business Information API as
    metadata.newReviewUri, and the existing location sync already asks for
    `metadata` in its readMask and stores the whole payload verbatim in
    gbp_raw — so this needs no extra API call and no new column.

    Falls back to building the URL from placeId, which is the same destination
    by a different route, for any location synced before newReviewUri appeared.
    """
    raw = location.gbp_raw or {}
    meta = raw.get("metadata") or {}

    uri = meta.get("newReviewUri")
    if uri:
        return uri

    place_id = meta.get("placeId")
    if place_id:
        return f"https://search.google.com/local/writereview?placeid={place_id}"

    return None


@router.get("/{token}")
def resolve_review_link(token: str, db: Session = Depends(get_db)):
    """Resolve a review token to its destination and record the click.

    Returns the URL rather than issuing the 302 itself: the caller is the
    Next.js route handler on pinzo.io, which owns the customer-facing response
    and can show a friendly page when something is wrong. A dead link should
    never be a raw JSON error in a customer's browser.
    """
    request = db.query(ReviewRequest).filter(ReviewRequest.token == token).first()
    if not request:
        # Deliberately identical to the "no review URL" case below — an
        # attacker probing tokens learns nothing about which ones exist.
        raise HTTPException(status_code=404, detail="link_not_found")

    location = db.query(Location).filter(Location.id == request.location_id).first()
    url = google_review_url(location) if location else None
    if not url:
        logger.warning(
            "[review-redirect] token %s resolved to location %s with no review URL",
            token, request.location_id,
        )
        raise HTTPException(status_code=404, detail="link_not_found")

    # First click only. A second tap is the same person changing their mind
    # about the tab they closed, not a new signal — and overwriting would lose
    # the time-to-click, which is the interesting part.
    if not request.clicked_at:
        request.clicked_at = datetime.now(timezone.utc)
        # Never downgrade a later state: delivered/read are facts from Meta,
        # and a click proves delivery anyway.
        if request.status in (ReviewRequest.STATUS_SENT, ReviewRequest.STATUS_DELIVERED,
                              ReviewRequest.STATUS_READ):
            request.status = ReviewRequest.STATUS_CLICKED
        db.commit()

    return {"url": url}
