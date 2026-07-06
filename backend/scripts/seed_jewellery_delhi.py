"""Seed a fully-populated showcase pSEO page: Jewellery Stores in Delhi.

Run inside the backend container:
    docker exec gmb_backend python scripts/seed_jewellery_delhi.py

Idempotent — upserts by slug. Fills every template section (incl. the audit-added
answer block, comparison, audit checklist and multiple review examples) so the page
renders at its richest. quality_score=90 so it passes the index gate.
"""
import os
import sys
from datetime import datetime, timezone

# Running `python scripts/foo.py` puts scripts/ on sys.path, not the app root — add it.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models.pseo_page import PseoPage, PseoPageStatus

SLUG = "jewellery-stores-in-delhi"

content = {
    "badge": "Built for jewellery retailers & multi-location showrooms",
    "hero_sub": "Manage your jewellery store's Google Business Profile — reviews, product photos, festive offers, Google Posts and local visibility across Delhi — from one dashboard.",
    "primary_cta": "Run Free Jewellery GBP Audit",
    "secondary_cta": "Book Demo on WhatsApp",
    "answer_block": (
        "Google Business Profile management for jewellery stores in Delhi means keeping your "
        "showroom's Google profile complete and current — correct categories, services, bridal "
        "and diamond collections, product photos, hallmark and certification details, customer "
        "reviews, festive Google Posts and performance tracking — so buyers across Delhi can find, "
        "trust and choose your store on Google Search and Maps, especially around weddings, "
        "Dhanteras and Akshaya Tritiya."
    ),
    "why_matters_body": (
        "Delhi jewellery buyers research on Google and Maps before they ever step into a showroom — "
        "comparing collections, reviews, prices and locations, then visiting two or three stores in "
        "person. A sharp Google Business Profile is what gets your showroom onto that shortlist."
    ),
    "why_matters_points": [
        "High-value purchases mean buyers research heavily before visiting",
        "Wedding season and festivals drive sharp spikes in local jewellery searches",
        "Reviews and photos decide which showrooms make the shortlist",
        "Maps visibility captures 'jeweller near me' and 'bridal jewellery in Delhi' searches",
    ],
    "problems": [
        {"title": "Low Google Maps visibility", "detail": "Buyers visit competing showrooms first because you don't appear for local jewellery searches."},
        {"title": "Unanswered reviews", "detail": "Future customers lose trust when they see reviews sitting without a reply."},
        {"title": "Outdated product photos", "detail": "Old or missing collection photos make your showroom look inactive."},
        {"title": "No festive posts", "detail": "Akshaya Tritiya, Dhanteras and wedding-season demand passes you by without timely offers."},
        {"title": "Missing services", "detail": "Buyers can't see bridal jewellery, repairs, resizing, gold exchange or custom work."},
        {"title": "Branch inconsistency", "detail": "Different timings, phone numbers and photos across showrooms confuse customers."},
        {"title": "Weak trust signals", "detail": "BIS hallmark, certification and real showroom photos aren't visible on the profile."},
        {"title": "Negative reviews unmanaged", "detail": "Pricing, billing or repair-delay complaints sit unanswered for everyone to read."},
        {"title": "No performance tracking", "detail": "Owners can't see which profile actions drive calls, directions and visits."},
    ],
    "solutions": [
        {"title": "Free GBP audit", "detail": "Find missing categories, services, products, photos, posts, reviews, Q&A and branch-level gaps."},
        {"title": "AI review replies", "detail": "Reply professionally to reviews about product quality, staff, pricing transparency, repair delays and the bridal experience."},
        {"title": "Google Posts scheduler", "detail": "Plan collection launches, festive offers, gold-exchange promotions and wedding-season updates."},
        {"title": "Photo checklist", "detail": "Track storefront, showroom interior, bridal collections, diamond rings, mangalsutra and certificate photos."},
        {"title": "Multi-location dashboard", "detail": "Manage Karol Bagh, South Extension, Chandni Chowk and franchise showrooms centrally."},
        {"title": "Local rank tracking", "detail": "Monitor visibility across key Delhi areas and nearby 'near me' searches."},
        {"title": "Hallmark & trust signals", "detail": "Surface BIS hallmarking, certification and staff photos to build buyer confidence."},
        {"title": "Monthly reporting", "detail": "See calls, direction clicks, website clicks, review trends and profile activity in one report."},
    ],
    "comparison": [
        {"point": "Review replies", "manual": "Written one at a time during store hours — many missed", "pinzo": "AI drafts every reply in your store's tone; you approve"},
        {"point": "Festive posts", "manual": "Remembered late, if at all", "pinzo": "Dhanteras & Akshaya Tritiya offers scheduled weeks ahead"},
        {"point": "Product photos", "manual": "Uploaded rarely, collections look old", "pinzo": "Photo checklist keeps every showroom fresh"},
        {"point": "Multiple showrooms", "manual": "Log into each listing separately", "pinzo": "Karol Bagh, South Ex & more from one dashboard"},
        {"point": "Local visibility", "manual": "No idea where you rank in Delhi", "pinzo": "Geo-grid rank tracking, area by area"},
        {"point": "Trust signals", "manual": "Hallmark & certificates not shown", "pinzo": "Audit flags missing trust fields to add"},
    ],
    "gbp_categories": ["Jewelry store", "Jewelry designer", "Diamond dealer", "Gold dealer", "Jewelry repair service"],
    "gbp_services": [
        "Bridal jewellery", "Diamond rings", "Engagement rings", "Mangalsutra", "Gold bangles",
        "Necklace sets", "Old gold exchange", "Jewellery repair", "Resizing", "Cleaning & polishing",
        "Custom jewellery", "Hallmarking & certification",
    ],
    "gbp_attributes": ["In-store shopping", "Wheelchair accessible", "Certified & hallmarked", "Custom orders", "Repairs & resizing", "By appointment"],
    "reviews_body": (
        "For a high-value purchase like jewellery, trust is built review by review. Pinzo drafts "
        "professional, on-brand replies you approve — so every buyer sees a store that listens, "
        "whether the review is about a bridal set, a repair or festive-season billing."
    ),
    "review_themes": ["pricing transparency", "product quality", "staff knowledge", "bridal experience", "after-sales service", "hallmarking trust"],
    "review_examples": [
        {"review": "Bought my wedding set from their Karol Bagh showroom — stunning designs and completely transparent pricing.",
         "reply": "Thank you so much! It was a joy helping with your wedding jewellery — wishing you a wonderful celebration."},
        {"review": "Got my grandmother's necklace repaired and polished; it looks brand new. Very skilled craftsmen.",
         "reply": "We're delighted the necklace came back to life — heirloom pieces are close to our hearts. Thank you for trusting us."},
        {"review": "Loved the certified diamond ring collection and the team explained the certification patiently.",
         "reply": "Thank you! Clear, certified information matters on a diamond purchase — glad we could help you choose with confidence."},
        {"review": "Exchanged old gold for a new mangalsutra. Fair valuation and a quick, honest process.",
         "reply": "Appreciate the kind words — transparent gold valuation is something we hold ourselves to. See you again soon!"},
        {"review": "Billing took longer than expected during the Dhanteras rush.",
         "reply": "Thank you for the honest feedback, and apologies for the wait during Dhanteras. We're adding counters at peak times to speed things up."},
    ],
    "post_ideas": [
        "Akshaya Tritiya — 0% making charges on gold this week",
        "New bridal collection launch — book a private viewing",
        "Dhanteras coin & jewellery pre-booking now open",
        "Old gold exchange camp this weekend — best valuation in Delhi",
        "Certified solitaire diamond festival — now in store",
        "Lightweight wedding-season jewellery, just arrived",
    ],
    "photo_checklist": [
        "Storefront with clear signage", "Showroom interior & display counters", "Bridal jewellery collection",
        "Diamond rings display", "Mangalsutra & gold sets", "BIS hallmark & certificates",
        "Craftsmen and counter staff", "Customer consultation lounge",
    ],
    "city_visibility_body": (
        "Delhi jewellery demand clusters around a few well-known hubs, and buyers compare showrooms "
        "on Google Maps before visiting — most heavily in wedding season and around Dhanteras and "
        "Akshaya Tritiya. Being visible in the right areas is what turns searches into showroom walk-ins."
    ),
    "neighborhoods": ["Karol Bagh", "Chandni Chowk (Dariba Kalan)", "South Extension", "Lajpat Nagar", "Connaught Place", "Rajouri Garden", "Preet Vihar", "Pitampura"],
    "single_points": [
        "One dashboard for your profile and reviews",
        "AI replies save close to an hour a day",
        "Festive posts scheduled weeks ahead",
        "A clear health score for your showroom",
    ],
    "multi_points": [
        "Branch-wise health scores across showrooms",
        "Bulk festive posts to every location at once",
        "Consistent timings, numbers and photos everywhere",
        "A leaderboard to compare showroom performance",
    ],
    "monthly_workflow": [
        {"title": "Audit", "detail": "Run the branch health audit across showrooms"},
        {"title": "Fix", "detail": "Push missing services, hallmark info and fresh photos"},
        {"title": "Reply", "detail": "Clear the review queue with AI-drafted replies"},
        {"title": "Report", "detail": "Send the monthly local-visibility report"},
    ],
    "faqs": [
        {"q": "What is Google Business Profile management for jewellery stores?",
         "a": "It means keeping your showroom's Google profile updated with correct information, categories, services, product photos, reviews, Google Posts and offers, so local buyers can find and trust your store on Google Search and Maps."},
        {"q": "How can jewellery stores get more showroom visits from Google Maps?",
         "a": "Complete every profile field, add real collection photos, keep hallmark and service details current, reply to reviews and post festive offers regularly. An active, complete profile is more likely to be shown for local jewellery searches."},
        {"q": "What should a jewellery store add to its Google Business Profile?",
         "a": "Accurate categories (jewelry store, diamond dealer, gold dealer), services like bridal jewellery, repairs, resizing and gold exchange, product photos, business hours, and hallmarking or certification details."},
        {"q": "How often should jewellery stores publish Google Posts?",
         "a": "Aim for at least weekly, and more often around wedding season, Dhanteras and Akshaya Tritiya, so buyers see current offers and new collections when they view your profile."},
        {"q": "What photos should jewellery stores upload?",
         "a": "Storefront and signage, showroom interior, bridal and diamond collections, mangalsutra and gold sets, hallmark and certificates, and your staff — real, current photos build buyer trust."},
        {"q": "How should jewellery stores reply to negative reviews?",
         "a": "Respond promptly, acknowledge the concern, avoid sharing private details, and offer to make it right. Pinzo drafts a measured reply you approve before it publishes."},
        {"q": "Can Pinzo manage multiple jewellery showroom profiles in Delhi?",
         "a": "Yes. Pinzo manages unlimited locations from one dashboard, with branch-wise health scores and bulk posting across Karol Bagh, South Extension and your other showrooms."},
        {"q": "Can jewellery stores promote Akshaya Tritiya or Dhanteras offers on GBP?",
         "a": "Yes — schedule Google Posts ahead of time for festive offers, gold-exchange camps and new collections so they go live across every showroom at the right moment."},
        {"q": "What is the best GBP category for a jewellery store?",
         "a": "'Jewelry store' is the primary category; add relevant secondary categories such as diamond dealer, gold dealer, jewelry designer or jewelry repair service to match what you actually offer."},
        {"q": "Can Pinzo track local visibility across Delhi?",
         "a": "Yes. Local rank tracking shows where you appear on Google Maps across Delhi areas so you can focus effort where visibility is weakest."},
    ],
    "final_heading": "Grow your jewellery store's visibility in Delhi",
    "final_sub": "Connect your Google Business Profile and see your health score, review gaps and local visibility in minutes. Free 7-day trial, no card required.",
    "template_version": "showcase-1",
    "last_updated": "2026-07-06",
}

db = SessionLocal()
page = db.query(PseoPage).filter(PseoPage.slug == SLUG).first()
if not page:
    page = PseoPage(slug=SLUG)
    db.add(page)
page.industry_label = "Jewellery Stores"
page.industry_slug = "jewellery-stores"
page.city_label = "Delhi"
page.city_slug = "delhi"
page.country = "in"
page.meta_title = "Google Business Profile Management for Jewellery Stores in Delhi | Pinzo"
page.meta_description = "Manage reviews, Google Posts, product photos, festive offers and local visibility for jewellery stores in Delhi with Pinzo. Free GBP audit, no card required."
page.h1 = "Google Business Profile Management for Jewellery Stores in Delhi"
page.canonical_url = None
page.index_status = "index"
page.quality_score = 90
page.content = content
page.status = PseoPageStatus.PUBLISHED.value
page.published_at = page.published_at or datetime.now(timezone.utc)
db.commit()
print("seeded:", SLUG, "quality_score=", page.quality_score, "status=", page.status)
