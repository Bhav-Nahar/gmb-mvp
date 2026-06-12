"""One-off backfill: lock surplus active locations down to the paid quota.

The trial→paid quota enforcement (apply_subscription_charged) only fixes orgs going
FORWARD. Orgs that converted BEFORE that fix may have more 'active' locations than
their paid location_quota (the trial admitted every location for free, and the
grandfathering rule never reclaimed the surplus). This script reconciles them:
keep the oldest `location_quota` active locations, flip the rest to 'pending_payment'.

Only touches orgs on a paid subscription (razorpay_subscription_id set) — trial orgs
are intentionally allowed full access until they convert.

Run:  docker exec gmb_backend python -m scripts.backfill_locked_over_quota_locations [--dry-run]
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.organization import Organization
from app.models.location import Location


def main(dry_run: bool = False) -> None:
    db = SessionLocal()
    try:
        orgs = db.query(Organization).filter(
            Organization.razorpay_subscription_id.isnot(None),
            Organization.location_quota.isnot(None),
        ).all()

        total_locked = 0
        for org in orgs:
            quota = org.location_quota or 0
            active = db.query(Location).filter(
                Location.organization_id == org.id,
                Location.billing_status == "active",
            ).order_by(Location.id.asc()).all()

            surplus = active[quota:]
            if not surplus:
                continue

            print(f"Org {org.id} ({org.name}): quota={quota}, active={len(active)} "
                  f"-> locking {len(surplus)} location(s): {[l.id for l in surplus]}")
            for loc in surplus:
                loc.billing_status = "pending_payment"
            total_locked += len(surplus)

        if dry_run:
            db.rollback()
            print(f"[DRY RUN] Would lock {total_locked} location(s). No changes committed.")
        else:
            db.commit()
            print(f"Locked {total_locked} surplus location(s) across {len(orgs)} paid org(s).")
    finally:
        db.close()


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
