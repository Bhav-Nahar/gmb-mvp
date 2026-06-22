"""One-time backfill: force-regenerate every existing leaderboard period under the
current scoring version (v4 adds response_rate + engagement_growth to the composite).

The monthly beat task runs with force=False and never overwrites existing snapshots,
so periods generated under v3 keep stale weights until re-run. This regenerates each
distinct (org, period) pair already in the DB with force=True.

Run from the backend dir:  python -m scripts.regenerate_leaderboard_v4 [--dry-run]
"""
import sys
import os
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from app.db.session import SessionLocal
from app.models.leaderboard_snapshot import LeaderboardSnapshot
from app.services.leaderboard_service import LeaderboardService
from app.core import leaderboard_config


def regenerate(dry_run: bool = False):
    db = SessionLocal()
    try:
        pairs = db.query(
            LeaderboardSnapshot.organization_id,
            LeaderboardSnapshot.period_label
        ).distinct().order_by(
            LeaderboardSnapshot.period_label.asc()  # oldest first so prior-period lookups exist
        ).all()

        print(f"Target version: {leaderboard_config.LEADERBOARD_SCORING_VERSION}")
        print(f"Found {len(pairs)} (org, period) pairs to regenerate.")

        done = 0
        for org_id, period in pairs:
            try:
                start, end = LeaderboardService.period_to_range(period)
            except ValueError:
                print(f"  SKIP org={org_id} period={period}: unparseable label")
                continue

            if dry_run:
                print(f"  [dry-run] would regenerate org={org_id} period={period}")
                continue

            snaps = LeaderboardService.generate_snapshots_for_period(
                db, organization_id=org_id, period_label=period,
                period_start=start, period_end=end, force=True
            )
            done += 1
            print(f"  org={org_id} period={period}: {len(snaps)} snapshots")

        print(f"Done. Regenerated {done} period(s)." if not dry_run else "Dry run complete.")
    except Exception as e:
        db.rollback()
        print(f"Error during regeneration: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    regenerate(dry_run="--dry-run" in sys.argv)
