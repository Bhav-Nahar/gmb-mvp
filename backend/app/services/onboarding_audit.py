"""Onboarding audit teaser.

Turns the already-synced data into a short list of REAL problems, used to create urgency
on the pre-payment gate ("we found N issues costing you customers"). Teaser only — counts
and one-line findings, never the underlying premium insight — so it's safe to expose to a
pre-payment onboarding org. Cheap COUNT queries; no AI, no external calls.
"""
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.location import Location
from app.models.review import Review

# Below this, the average rating is a conversion problem worth flagging.
_RATING_FLOOR = 4.2


def compute_audit_summary(db: Session, org_id: int) -> dict:
    loc_q = db.query(Location).filter(
        Location.organization_id == org_id,
        Location.billing_status == "active",
    )
    locations = loc_q.count()

    avg_rating = db.query(func.avg(Location.average_rating)).filter(
        Location.organization_id == org_id,
        Location.billing_status == "active",
        Location.average_rating.isnot(None),
    ).scalar()
    avg_rating = round(float(avg_rating), 1) if avg_rating is not None else None

    total_reviews = int(db.query(func.coalesce(func.sum(Location.total_reviews), 0)).filter(
        Location.organization_id == org_id,
        Location.billing_status == "active",
    ).scalar() or 0)

    rev = db.query(Review).filter(Review.organization_id == org_id, Review.is_deleted.is_(False))
    unanswered = rev.filter(Review.is_replied.is_(False)).count()
    negative_unanswered = rev.filter(Review.rating <= 2, Review.is_replied.is_(False)).count()

    profile_gaps = loc_q.filter(or_(
        Location.website.is_(None),
        Location.description.is_(None),
        Location.business_hours.is_(None),
    )).count()

    # Real findings, most-urgent first. Each is only a teaser (a number + why it hurts).
    issues: list[dict] = []
    if negative_unanswered:
        issues.append({
            "label": f"{negative_unanswered} negative review{'s' if negative_unanswered != 1 else ''} with no reply",
            "detail": "Unanswered low-star reviews are actively driving prospects to competitors.",
        })
    if unanswered:
        issues.append({
            "label": f"{unanswered} review{'s' if unanswered != 1 else ''} left unanswered",
            "detail": "Most customers read owner replies before choosing, so silence costs bookings.",
        })
    if profile_gaps:
        issues.append({
            "label": f"{profile_gaps} location{'s' if profile_gaps != 1 else ''} with missing profile info",
            "detail": "Missing website, hours or description drags down your Google ranking.",
        })
    if avg_rating is not None and avg_rating < _RATING_FLOOR:
        issues.append({
            "label": f"{avg_rating}★ average rating",
            "detail": f"Below the {_RATING_FLOOR}★ bar most customers set before they'll call.",
        })

    return {
        "locations": locations,
        "total_reviews": total_reviews,
        "avg_rating": avg_rating,
        "unanswered_reviews": unanswered,
        "negative_unanswered": negative_unanswered,
        "profile_gaps": profile_gaps,
        "critical_issues": len(issues),
        "issues": issues,
    }
