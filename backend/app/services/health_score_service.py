from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone
import json

from datetime import timedelta

from app.models.location import Location
from app.models.review import Review
from app.models.location_health_score import LocationHealthScore
from app.models.location_media import LocationMedia, LocationMediaStatus
from app.models.local_rank_scan import LocalRankScan
from app.models.location_daily_insights import LocationDailyInsight
from app.services import description_validation

class HealthScoreService:
    SCORE_VERSION = "HEALTH_V2.1"

    @classmethod
    def recalculate_health_score(cls, db: Session, location_id: int, reason: str = "manual") -> LocationHealthScore:
        location = db.query(Location).filter(Location.id == location_id).first()
        if not location:
            return None

        # 1. Profile Completeness (30 Max)
        prof_score = 0
        has_name = bool(location.location_name and location.location_name.strip())
        if isinstance(location.address, dict):
            has_address = len(location.address) > 0
        elif isinstance(location.address, str):
            has_address = bool(location.address.strip())
        else:
            has_address = bool(location.address)
        has_phone = bool(location.phone and str(location.phone).strip())
        has_website = bool(location.website and location.website.strip())
        has_hours = bool(location.business_hours and len(location.business_hours) > 0)
        has_desc = bool(location.description and location.description.strip())
        # Graduated 0-5 quality (length band + category mention + policy-clean),
        # so improving a weak description actually moves the score — not just
        # presence. Same analysis powers the "is it already good?" gate. No LLM.
        desc_analysis = description_validation.analyze(location.description, location.primary_category)
        desc_quality = desc_analysis["quality_score"]

        if has_name: prof_score += 5
        if has_address: prof_score += 5
        if has_phone: prof_score += 5
        if has_website: prof_score += 5
        if has_hours: prof_score += 5
        prof_score += desc_quality

        # 2. Reviews & Rating (25 Max)
        rating_score = 0
        avg_rating = location.average_rating or 0.0
        if avg_rating >= 4.5: rating_score = 20
        elif avg_rating >= 4.0: rating_score = 15
        elif avg_rating >= 3.5: rating_score = 10
        elif avg_rating > 0: rating_score = 5

        vol_score = 0
        total_revs = location.total_reviews or 0
        if total_revs >= 100: vol_score = 5
        elif total_revs >= 50: vol_score = 4
        elif total_revs >= 20: vol_score = 3
        elif total_revs >= 1: vol_score = 2

        reviews_score = rating_score + vol_score

        # 3. Review Response Rate (10 Max)
        # Reply data lives only on the Review table (not cached on Location), so we
        # read it live. A single aggregate query returns both totals to avoid two
        # round-trips.
        resp_score = 10
        db_total_revs, replied_revs = (
            db.query(
                func.count(Review.id),
                func.count(func.nullif(Review.is_replied, False)),
            )
            .filter(Review.location_id == location_id, Review.is_deleted == False)
            .one()
        )
        db_total_revs = db_total_revs or 0
        replied_revs = replied_revs or 0
        if db_total_revs > 0:
            rate = replied_revs / db_total_revs
            if rate >= 0.9: resp_score = 10
            elif rate >= 0.7: resp_score = 8
            elif rate >= 0.5: resp_score = 5
            else: resp_score = 2

        # 4. Post Activity (20 Max)
        post_score = 0
        if location.last_published_at:
            # Ensure timezone-aware subtraction
            now_dt = datetime.now(timezone.utc)
            pub_dt = location.last_published_at
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
                
            days_ago = (now_dt - pub_dt).days
            if days_ago <= 7: post_score = 20
            elif days_ago <= 30: post_score = 15
            else: post_score = 5

        # 5. Photos & Media (15 Max)
        # Reward the photos that matter, not a raw count: a Logo (4), a Cover (4),
        # and content/additional photos (up to 7). Counts only photos actually
        # live on the Google profile gallery (synced or published via the app).
        cat_rows = (
            db.query(LocationMedia.gbp_category, func.count(LocationMedia.id))
            .filter(
                LocationMedia.location_id == location_id,
                LocationMedia.is_deleted == False,
                LocationMedia.publish_status == LocationMediaStatus.PUBLISHED,
            )
            .group_by(LocationMedia.gbp_category)
            .all()
        )
        cat_counts = {c: n for c, n in cat_rows}
        # Google's profile photo serves as the logo/avatar, so PROFILE counts too.
        has_logo = (cat_counts.get("LOGO", 0) + cat_counts.get("PROFILE", 0)) > 0
        has_cover = cat_counts.get("COVER", 0) > 0
        additional_count = sum(
            n for c, n in cat_counts.items() if c not in ("LOGO", "PROFILE", "COVER")
        )
        photos_count = sum(cat_counts.values())

        logo_score = 4 if has_logo else 0
        cover_score = 4 if has_cover else 0
        if additional_count >= 5: additional_score = 7
        elif additional_count >= 1: additional_score = 3
        else: additional_score = 0
        photo_score = logo_score + cover_score + additional_score

        # --- Radar-only dimensions (0-10 each, NOT counted in the 100-pt total;
        # an axis is omitted when the location has no data for it) ---
        now_utc = datetime.now(timezone.utc)

        # Ranking: latest completed local rank scan's share-of-local-voice (0-100%).
        ranking_score = None
        latest_scan = (
            db.query(LocalRankScan.solv)
            .filter(LocalRankScan.location_id == location_id,
                    LocalRankScan.status == "Completed",
                    LocalRankScan.solv.isnot(None))
            .order_by(LocalRankScan.created_at.desc())
            .first()
        )
        if latest_scan:
            ranking_score = round(latest_scan.solv / 10, 1)

        # Traffic + Sentiment + website clicks: last 30 days of daily insights.
        views_30d, clicks_30d, sentiment_avg = (
            db.query(
                func.coalesce(func.sum(LocationDailyInsight.profile_views), 0),
                func.coalesce(func.sum(LocationDailyInsight.website_clicks), 0),
                func.avg(LocationDailyInsight.avg_sentiment_score),
            )
            .filter(LocationDailyInsight.location_id == location_id,
                    LocationDailyInsight.date >= (now_utc - timedelta(days=30)).date())
            .one()
        )

        # Traffic: tiered on monthly profile views.
        # ponytail: absolute tiers, switch to category/cohort benchmarks if needed.
        traffic_score = None
        if views_30d > 0:
            if views_30d >= 3000: traffic_score = 10.0
            elif views_30d >= 1500: traffic_score = 8.0
            elif views_30d >= 600: traffic_score = 6.0
            elif views_30d >= 200: traffic_score = 4.0
            elif views_30d >= 50: traffic_score = 2.5
            else: traffic_score = 1.0

        # Sentiment: -1..1 mapped onto 0-10.
        sentiment_score = round((sentiment_avg + 1) * 5, 1) if sentiment_avg is not None else None

        # Website: URL on the profile (up to 6) + clicks actually happening (up to 4).
        website_score = None
        if has_website or clicks_30d > 0:
            website_score = 6.0 if has_website else 0.0
            if clicks_30d >= 100: website_score += 4.0
            elif clicks_30d >= 25: website_score += 3.0
            elif clicks_30d >= 5: website_score += 2.0
            elif clicks_30d >= 1: website_score += 1.0

        # --- Totals ---
        total_score = prof_score + reviews_score + resp_score + post_score + photo_score
        potential_score = 100  # Max is 100

        # Label
        if total_score >= 90: label = "Excellent"
        elif total_score >= 75: label = "Good"
        elif total_score >= 60: label = "Average"
        elif total_score >= 40: label = "Poor"
        else: label = "Critical"

        # One-line "why this score" per dimension, shown next to the radar.
        missing_fields = [name for ok, name in [
            (has_name, "name"), (has_address, "address"), (has_phone, "phone"),
            (has_website, "website"), (has_hours, "hours"), (has_desc, "description"),
        ] if not ok]
        prof_detail = ("All core profile fields are filled." if not missing_fields
                       else f"Missing: {', '.join(missing_fields)}.")
        reviews_detail = (f"{avg_rating:.1f}★ average across {total_revs} reviews."
                          if total_revs else "No reviews yet.")
        resp_detail = (f"{replied_revs} of {db_total_revs} reviews replied to."
                       if db_total_revs else "No reviews to reply to yet.")
        if location.last_published_at:
            post_detail = f"Last post published {days_ago} day{'s' if days_ago != 1 else ''} ago."
        else:
            post_detail = "No posts published yet — regular posts improve local SEO."
        photo_bits = []
        if not has_logo: photo_bits.append("no logo")
        if not has_cover: photo_bits.append("no cover photo")
        if additional_count < 5: photo_bits.append(f"only {additional_count} gallery photos (5+ recommended)")
        photo_detail = (f"{photos_count} photos live on your profile."
                        if not photo_bits else f"{photos_count} photos live, but {', '.join(photo_bits)}.")

        breakdown = {
            "profile_completeness": {"score": prof_score, "max_score": 30, "detail": prof_detail},
            "reviews_rating": {"score": reviews_score, "max_score": 25, "detail": reviews_detail},
            "response_rate": {"score": resp_score, "max_score": 10, "detail": resp_detail},
            "post_activity": {"score": post_score, "max_score": 20, "detail": post_detail},
            "photos_media": {"score": photo_score, "max_score": 15, "detail": photo_detail},
            # Surfaced so the UI shows the description's "before" status/flags
            # straight from the cached score — no recompute, no extra table.
            "description": {
                "score": desc_quality, "max_score": 5,
                "status": desc_analysis["status"],
                "char_count": desc_analysis["char_count"],
                "hard_flags": desc_analysis["hard_flags"],
                "soft_flags": desc_analysis["soft_flags"],
            },
        }
        ranking_detail = (f"You appear in {latest_scan.solv:.0f}% of local search grid points in your latest rank scan."
                          if latest_scan else None)
        traffic_detail = f"{views_30d} profile views in the last 30 days." if views_30d > 0 else None
        if sentiment_avg is not None:
            mood = "positive" if sentiment_avg > 0.3 else ("negative" if sentiment_avg < -0.3 else "mixed")
            sentiment_detail = f"Review sentiment over the last 30 days is {mood}."
        else:
            sentiment_detail = None
        website_detail = None
        if website_score is not None:
            website_detail = ((f"Website on profile; {clicks_30d} clicks in the last 30 days."
                               if has_website else f"{clicks_30d} website clicks, but no website URL on your profile.")
                              if clicks_30d else "Website on profile, but no clicks in the last 30 days.")

        for key, val, detail in (("ranking", ranking_score, ranking_detail),
                                 ("traffic", traffic_score, traffic_detail),
                                 ("sentiment", sentiment_score, sentiment_detail),
                                 ("website", website_score, website_detail)):
            if val is not None:
                breakdown[key] = {"score": min(round(val), 10), "max_score": 10, "detail": detail}

        # Recommendations
        recs = []

        # Priority 1
        if not has_website:
            recs.append({"priority": 1, "title": "Add Website", "description": "Website URL is missing.", "potential_gain": 5, "target_tab": "profile"})
        if not has_address:
            recs.append({"priority": 1, "title": "Add Address", "description": "Business address is missing.", "potential_gain": 5, "target_tab": "profile"})

        # Priority 2
        if post_score < 15:
            recs.append({"priority": 2, "title": "Publish a GBP Post", "description": "You haven't posted recently. Regular posts improve local SEO.", "potential_gain": 20 - post_score, "target_tab": "posts"})
        if resp_score < 8:
            recs.append({"priority": 2, "title": "Reply to Reviews", "description": "Your review response rate is low. Reply to pending reviews.", "potential_gain": 10 - resp_score, "target_tab": "reviews"})

        # Priority 3
        if not has_hours:
            recs.append({"priority": 3, "title": "Add Business Hours", "description": "Business hours are missing.", "potential_gain": 5, "target_tab": "profile"})
        if not has_desc:
            recs.append({"priority": 3, "title": "Add Description", "description": "Business description is missing.", "potential_gain": 5, "target_tab": "profile"})
        elif desc_quality < 5:
            if desc_analysis["hard_flags"]:
                why = "Your description contains content Google may reject."
            elif desc_analysis["char_count"] < 350:
                why = "Your description is short — aim for 550-700 characters."
            elif not desc_analysis["has_category"]:
                why = "Mention your business category naturally in the description."
            else:
                why = "Polish your description for stronger local relevance."
            recs.append({"priority": 3, "title": "Improve Description", "description": why, "potential_gain": 5 - desc_quality, "target_tab": "profile"})
        if rating_score < 15 and avg_rating > 0:
            recs.append({"priority": 3, "title": "Improve Rating", "description": "Your average rating is below 4.0. Focus on customer experience.", "potential_gain": 20 - rating_score, "target_tab": "reviews"})

        # Priority 4
        if not has_logo:
            recs.append({"priority": 4, "title": "Add a Logo", "description": "Add a logo/profile photo so customers recognise your brand.", "potential_gain": 4, "target_tab": "photos"})
        if not has_cover:
            recs.append({"priority": 4, "title": "Add a Cover Photo", "description": "A cover photo makes your profile stand out in search and maps.", "potential_gain": 4, "target_tab": "photos"})
        if additional_score < 7:
            recs.append({"priority": 4, "title": "Add More Photos", "description": "Add photos of your products, interior, and team (5+ recommended).", "potential_gain": 7 - additional_score, "target_tab": "photos"})

        # Sort recommendations by priority asc, then potential_gain desc
        recs.sort(key=lambda r: (r["priority"], -r["potential_gain"]))

        # Remove priority key for output
        for r in recs:
            del r["priority"]

        # Update or create health score
        hs = db.query(LocationHealthScore).filter(LocationHealthScore.location_id == location_id).first()
        if not hs:
            hs = LocationHealthScore(location_id=location_id)
            db.add(hs)
        
        hs.score = total_score
        hs.potential_score = potential_score
        hs.label = label
        hs.breakdown = breakdown
        hs.recommendations = recs
        hs.last_recalculated_reason = reason
        hs.score_version = cls.SCORE_VERSION

        # Flush (do not commit) so the caller controls the transaction boundary.
        # Committing here would prematurely flush unrelated pending work in the
        # shared session (e.g. mid-task sync state).
        db.flush()
        return hs
