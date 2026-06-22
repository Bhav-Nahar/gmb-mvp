from app.db.session import SessionLocal
from app.models.location import Location
from app.models.review import Review
from app.models.location_health_score import LocationHealthScore
from app.models.location_daily_insights import LocationDailyInsight
from app.services.leaderboard_service import LeaderboardService
import datetime
import random

db = SessionLocal()
locations = db.query(Location).all()
now = datetime.datetime.now(datetime.timezone.utc)
past = now - datetime.timedelta(days=60)

# 1. Add a second location to Org 28 if it only has 1
org28_locs = [l for l in locations if l.organization_id == 28]
if len(org28_locs) == 1:
    new_loc = Location(
        organization_id=28,
        google_location_id="dummy_loc_" + str(random.randint(1000, 9999)),
        location_name="Storefront Seattle",
        billing_status="active",
        created_at=past,
        total_reviews=15,
        average_rating=4.2
    )
    db.add(new_loc)
    db.commit()
    db.refresh(new_loc)
    locations.append(new_loc)

for loc in locations:
    if loc.billing_status != "active":
        loc.billing_status = "active"
        
    loc.created_at = past
    loc.total_reviews = random.randint(10, 50)
    loc.average_rating = random.uniform(3.5, 5.0)
    
    # ensure it has a health score
    hs = db.query(LocationHealthScore).filter_by(location_id=loc.id).first()
    if not hs:
        hs = LocationHealthScore(location_id=loc.id, score=random.uniform(60, 95), potential_score=100, label="Excellent", breakdown={}, recommendations=[], last_recalculated_reason="mock_data")
        db.add(hs)
    else:
        hs.score = random.uniform(60, 95)
        
    # ensure reviews exist to calculate response rate
    rev_count = db.query(Review).filter_by(location_id=loc.id).count()
    if rev_count == 0:
        for i in range(loc.total_reviews):
            r = Review(
                organization_id=loc.organization_id,
                location_id=loc.id,
                provider="google",
                provider_review_id=f"rev_{loc.id}_{i}_{random.randint(1,10000)}",
                reviewer_name=f"Tester {i}",
                rating=random.randint(3, 5),
                comment="Great place!",
                review_created_at=past + datetime.timedelta(days=i) if i < loc.total_reviews - 5 else now - datetime.timedelta(days=random.randint(0, 10)),
                is_replied=(random.random() > 0.5)
            )
            db.add(r)
            
    # ensure insights exist
    ins_count = db.query(LocationDailyInsight).filter_by(location_id=loc.id).count()
    if ins_count == 0:
        for i in range(60):
            d = past + datetime.timedelta(days=i)
            ind = LocationDailyInsight(
                organization_id=loc.organization_id,
                location_id=loc.id,
                date=d.date(),
                search_impressions=random.randint(50, 150),
                maps_views=random.randint(20, 80)
            )
            db.add(ind)

db.commit()

# 2. Regenerate snapshots
for org_id in [28, 29]:
    period = f"{now.year}-{now.month:02d}"
    year_int, month_int = now.year, now.month
    period_start = datetime.date(year_int, month_int, 1)
    if month_int == 12:
        next_month_start = datetime.date(year_int + 1, 1, 1)
    else:
        next_month_start = datetime.date(year_int, month_int + 1, 1)
    period_end = next_month_start - datetime.timedelta(days=1)

    print(f"Generating for org {org_id}...")
    snapshots = LeaderboardService.generate_snapshots_for_period(
        db, 
        organization_id=org_id,
        period_label=period,
        period_start=period_start,
        period_end=period_end,
        force=True
    )
    print(f"Generated {len(snapshots)} snapshots for org {org_id}")
    for s in snapshots:
        print(f"  Loc: {s.location_id}, Eligible: {s.is_eligible}, Score: {s.composite_score}")
