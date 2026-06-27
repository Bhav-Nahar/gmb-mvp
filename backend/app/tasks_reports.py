"""Weekly performance report emails.

One beat task fans out a per-recipient email. Scope is automatic: Owners/Admins
get the whole org (get_user_location_ids returns None → no location filter),
Regional/Store Managers get only their assigned locations. Reuses the existing
Resend send_email service and the same LocationDailyInsight metrics the dashboard
already shows — no new infra, no PDF.
"""
import datetime
import logging

from celery import shared_task
from sqlalchemy import func, case

from app.db.session import SessionLocal
from app.core.config import settings
from app.core.roles import STAFF_ROLES
from app.api.deps import get_user_location_ids
from app.models.user import User
from app.models.organization import Organization
from app.models.location import Location
from app.models.location_daily_insights import LocationDailyInsight
from app.models.review import Review
from app.services.email_service import send_email

logger = logging.getLogger(__name__)

_KPI_COLS = [
    ("profile_views", "Profile views"),
    ("search_impressions", "Search impressions"),
    ("maps_views", "Maps views"),
    ("phone_calls", "Phone calls"),
    ("website_clicks", "Website clicks"),
    ("direction_requests", "Directions"),
]


def _scoped(q, location_ids):
    """Apply the per-user location scope. None = whole org (org-wide roles)."""
    if location_ids is not None:
        q = q.filter(LocationDailyInsight.location_id.in_(location_ids))
    return q


def _kpi_sums(db, org_id, location_ids, start, end):
    """Sum the 6 headline metrics over [start, end] for the given scope."""
    cols = [func.coalesce(func.sum(getattr(LocationDailyInsight, k)), 0).label(k) for k, _ in _KPI_COLS]
    q = db.query(*cols).filter(
        LocationDailyInsight.organization_id == org_id,
        LocationDailyInsight.date >= start,
        LocationDailyInsight.date <= end,
    )
    return _scoped(q, location_ids).one()


def _reputation(db, org_id, location_ids, start, end):
    """avg rating (simple mean of standing ratings), new reviews this week, awaiting reply."""
    rq = db.query(Location.average_rating).filter(
        Location.organization_id == org_id, Location.average_rating.isnot(None)
    )
    if location_ids is not None:
        rq = rq.filter(Location.id.in_(location_ids))
    ratings = [float(r[0]) for r in rq.all()]
    avg_rating = round(sum(ratings) / len(ratings), 1) if ratings else None

    nq = db.query(func.coalesce(func.sum(LocationDailyInsight.reviews_received), 0)).filter(
        LocationDailyInsight.organization_id == org_id,
        LocationDailyInsight.date >= start,
        LocationDailyInsight.date <= end,
    )
    new_reviews = int(_scoped(nq, location_ids).scalar() or 0)

    uq = db.query(func.count(Review.id)).filter(
        Review.organization_id == org_id,
        Review.is_deleted == False,  # noqa: E712
        Review.is_replied == False,  # noqa: E712
    )
    if location_ids is not None:
        uq = uq.filter(Review.location_id.in_(location_ids))
    unanswered = int(uq.scalar() or 0)
    return avg_rating, new_reviews, unanswered


def _render_html(org_name, period, cur, prior, avg_rating, new_reviews, unanswered, dash_url):
    def tile(key, label):
        c, p = int(getattr(cur, key)), int(getattr(prior, key))
        if p:
            pct = round((c - p) / p * 100)
            color = "#16a34a" if pct >= 0 else "#dc2626"
            delta = f'<span style="color:{color};font-size:12px"> {"▲" if pct >= 0 else "▼"} {abs(pct)}%</span>'
        else:
            delta = ""
        return (
            '<td style="padding:12px;border:1px solid #eee;border-radius:8px;width:33%">'
            f'<div style="font-size:11px;color:#888;text-transform:uppercase">{label}</div>'
            f'<div style="font-size:22px;font-weight:800;color:#111">{c:,}{delta}</div></td>'
        )

    t = [tile(k, lbl) for k, lbl in _KPI_COLS]
    grid = f"<tr>{t[0]}{t[1]}{t[2]}</tr><tr>{t[3]}{t[4]}{t[5]}</tr>"
    rating_txt = f"★ <b>{avg_rating:.1f}</b> avg rating · " if avg_rating is not None else ""
    return f'''<div style="font-family:system-ui,Arial,sans-serif;max-width:560px;margin:auto;color:#111">
  <h2 style="margin:0 0 4px">Your week on Google</h2>
  <p style="color:#888;margin:0 0 20px">{org_name} · {period}</p>
  <table style="width:100%;border-collapse:separate;border-spacing:8px">{grid}</table>
  <div style="background:#f6f6f6;border-radius:8px;padding:16px;margin:20px 0">
    {rating_txt}<b>{new_reviews}</b> new reviews · <b style="color:#dc2626">{unanswered}</b> awaiting reply
  </div>
  <a href="{dash_url}" style="display:inline-block;background:#111;color:#fff;text-decoration:none;padding:12px 24px;border-radius:8px;font-weight:700">View full report →</a>
  <p style="color:#aaa;font-size:11px;margin-top:24px"><a href="{dash_url}/settings" style="color:#aaa">Notification settings</a></p>
</div>'''


@shared_task(name="app.tasks_reports.send_weekly_reports_task")
def send_weekly_reports_task() -> str:
    """Email every Owner/Admin/Regional Manager/Store Manager their weekly summary.

    Owners/Admins see the whole org; managers see only their assigned locations —
    driven entirely by get_user_location_ids. Skips recipients whose scope had no
    activity this week so we never send an all-zero email.
    """
    end = datetime.date.today() - datetime.timedelta(days=1)      # yesterday
    start = end - datetime.timedelta(days=6)                       # last 7 days
    prior_end = start - datetime.timedelta(days=1)
    prior_start = prior_end - datetime.timedelta(days=6)
    period = f"{start.strftime('%b %d')} – {end.strftime('%b %d')}"
    dash_url = f"{settings.FRONTEND_URL.rstrip('/')}/dashboard"

    db = SessionLocal()
    sent = 0
    try:
        users = db.query(User).filter(
            User.is_active == True,  # noqa: E712
            User.weekly_report_email == True,  # noqa: E712
            User.role.in_(list(STAFF_ROLES)),
        ).all()
        org_names = dict(db.query(Organization.id, Organization.name).all())

        for user in users:
            try:
                location_ids = get_user_location_ids(user, db)
                if location_ids is not None and not location_ids:
                    continue  # manager with no assigned locations
                cur = _kpi_sums(db, user.organization_id, location_ids, start, end)
                prior = _kpi_sums(db, user.organization_id, location_ids, prior_start, prior_end)
                avg_rating, new_reviews, unanswered = _reputation(
                    db, user.organization_id, location_ids, start, end
                )
                # Nothing happened in this scope this week — don't send a dead email.
                if not any(int(getattr(cur, k)) for k, _ in _KPI_COLS) and not new_reviews and not unanswered:
                    continue
                html = _render_html(
                    org_names.get(user.organization_id, "Your business"), period,
                    cur, prior, avg_rating, new_reviews, unanswered, dash_url,
                )
                if send_email([user.email], f"Your week on Google · {period}", html):
                    sent += 1
            except Exception as e:
                db.rollback()
                logger.error("Weekly report failed for user %s: %s", user.id, e)
        return f"Weekly reports sent: {sent}/{len(users)}"
    finally:
        db.close()
