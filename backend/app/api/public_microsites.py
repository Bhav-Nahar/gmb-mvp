import json
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, joinedload
from app.db.session import get_db
from app.models.microsite import Microsite
from app.models.location import Location
from app.models.review import Review
from app.models.location_media import LocationMedia, LocationMediaStatus
from app.models.lead import Lead
from app.models.user import User
from app.schemas.public_microsite import PublicMicrositeSchema, PublicReviewSchema
from app.schemas.lead import LeadCreate
from app.core.redis_client import get_redis
from app.services.email_service import send_email

logger = logging.getLogger(__name__)
router = APIRouter()

# Public microsite pages are unauthenticated, SEO-crawled, and change only when a
# sync/publish runs — all of which flow through revalidation_service, which deletes
# this key. The TTL is a backstop matching the frontend's hourly ISR cycle.
_PUBLIC_MICROSITE_CACHE_TTL = 60 * 60


def public_microsite_cache_key(location_slug: str) -> str:
    return f"public_microsite:{location_slug}"


# GBP exposes social/contact links as URL attributes (attributes/url_*). Map the
# ones we want to show -> a display label. Anything not present is simply skipped.
_SOCIAL_ATTRS = {
    "url_whatsapp": "WhatsApp",
    "url_facebook": "Facebook",
    "url_instagram": "Instagram",
    "url_linkedin": "LinkedIn",
    "url_twitter": "Twitter",
    "url_youtube": "YouTube",
    "url_tiktok": "TikTok",
    "url_pinterest": "Pinterest",
    "url_appointment": "Book Appointment",
    "url_menu": "Menu",
    "url_order": "Order Online",
    "url_reservations": "Reservations",
}


def _extract_social_links(attrs) -> list:
    """Pull social/contact links from GBP URL attributes. Returns
    [{"type","label","url"}], empty if the business has none set."""
    out = []
    for a in attrs or []:
        if not isinstance(a, dict):
            continue
        key = (a.get("name") or "").split("/")[-1]
        label = _SOCIAL_ATTRS.get(key)
        if not label:
            continue
        # URL attributes use uriValues[{uri}]; fall back to plain string values.
        uris = [u.get("uri") for u in (a.get("uriValues") or []) if isinstance(u, dict) and u.get("uri")]
        if not uris:
            uris = [v for v in (a.get("values") or []) if isinstance(v, str)]
        if uris:
            out.append({"type": key.replace("url_", ""), "label": label, "url": uris[0]})
    return out


def _format_address(raw) -> Optional[str]:
    """Turn the stored GBP storefrontAddress JSON into a readable single line.
    Falls back to the raw value if it isn't the expected JSON shape."""
    if not raw:
        return None
    data = raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            return raw  # already a plain string
    if not isinstance(data, dict):
        return str(raw)
    parts = []
    parts.extend(data.get("addressLines") or [])
    for key in ("locality", "administrativeArea", "postalCode"):
        if data.get(key):
            parts.append(str(data[key]))
    return ", ".join(p.strip().rstrip(",") for p in parts if p) or None

# ponytail: Redis fixed-window limiter, 60 req/min per IP. Coarse but enough to
# stop slug enumeration/scraping of unauthenticated microsites. Swap for slowapi
# or a sliding window if abuse patterns need finer control.
def rate_limit(request: Request) -> None:
    ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
          or (request.client.host if request.client else "unknown"))
    try:
        r = get_redis()
        key = f"ratelimit:public_microsite:{ip}"
        count = r.incr(key)
        if count == 1:
            r.expire(key, 60)
        if count > 60:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                                detail="Too many requests")
    except HTTPException:
        raise
    except Exception as e:
        # Never let a Redis hiccup take down the public page — fail open.
        logger.warning(f"Rate limit check failed, allowing request: {e}")

@router.get("/{location_slug}", response_model=PublicMicrositeSchema)
def get_public_microsite(location_slug: str, request: Request, db: Session = Depends(get_db)):
    """
    Public endpoint to fetch all data necessary to render a microsite.
    Single-level URL: access control is purely via the globally-unique location_slug.
    """
    # Cache only holds published responses and is deleted on any publish/unpublish/
    # sync (revalidation_service), so a hit always means "still published". A Redis
    # miss/outage falls through to the DB.
    cache_key = public_microsite_cache_key(location_slug)
    try:
        cached = get_redis().get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass

    # Rate-limit only cache misses: slug enumeration always misses (unknown slugs),
    # so scraping protection is intact, while cached hits cost 1 Redis command
    # instead of 2-3 (Upstash bills per command).
    rate_limit(request)

    # 1. Look up Microsite (eager-load the location to avoid a second round-trip)
    microsite = db.query(Microsite).options(
        joinedload(Microsite.location)
    ).filter(
        Microsite.location_slug == location_slug
    ).first()

    if not microsite or microsite.status == "draft":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    
    if microsite.status == "unpublished":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Microsite is no longer available.")
        
    location = microsite.location
    if not location:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
        
    # 2. Fetch top 5 Reviews (rating DESC, review_created_at DESC)
    reviews = db.query(Review).filter(
        Review.location_id == location.id,
        Review.is_deleted == False
    ).order_by(
        Review.rating.desc().nullslast(),
        Review.review_created_at.desc()
    ).limit(5).all()
    
    # 3. Fetch Photos (LocationMedia published)
    media_items = db.query(LocationMedia).filter(
        LocationMedia.location_id == location.id,
        LocationMedia.publish_status == LocationMediaStatus.PUBLISHED,
        LocationMedia.is_deleted == False
    ).all()
    
    # Images only — exclude videos (mp4/mov/etc.), which break <img> tags. Filter by
    # the media_format column and, defensively, by file extension.
    _VIDEO_EXT = (".mp4", ".mov", ".webm", ".avi", ".m4v", ".mkv")

    def _is_image(m):
        if not m.source_url:
            return False
        if (m.media_format or "").upper() == "VIDEO":
            return False
        return not m.source_url.lower().split("?")[0].endswith(_VIDEO_EXT)

    image_items = [m for m in media_items if _is_image(m)]
    photos = [m.source_url for m in image_items]

    # Brand logo: prefer GBP LOGO, then PROFILE, then COVER (images only).
    by_cat = {}
    for m in image_items:
        if m.gbp_category:
            by_cat.setdefault(m.gbp_category.upper(), m.source_url)
    logo = by_cat.get("LOGO") or by_cat.get("PROFILE") or by_cat.get("COVER")

    # Hero background: a wide/scenic shot. Prefer COVER, then storefront/interior,
    # else just the first available photo.
    cover = None
    for cat in ("COVER", "EXTERIOR", "INTERIOR"):
        if cat in by_cat:
            cover = by_cat[cat]
            break
    if not cover and photos:
        cover = photos[0]

    # GBP canonical map + review links (exact business pin / write-review deep link).
    meta = (location.gbp_raw or {}).get("metadata") or {}
    maps_url = meta.get("mapsUri")
    review_url = meta.get("newReviewUri")

    # address is stored as the raw GBP storefrontAddress JSON; render a clean,
    # human-readable single line instead of dumping the JSON onto the page.
    readable_address = _format_address(location.address)

    # Handle service_items (JSON array natively returned by Postgres JSONB)
    services = location.service_items if isinstance(location.service_items, list) else []
    
    public_reviews = []
    for r in reviews:
        public_reviews.append(PublicReviewSchema(
            reviewer_name=r.reviewer_name,
            reviewer_profile_photo=r.reviewer_profile_photo,
            rating=r.rating,
            comment=r.comment,
            review_created_at=r.review_created_at,
            reply_text=r.reply_text,
            reply_created_at=r.reply_created_at
        ))
        
    result = PublicMicrositeSchema(
        location_name=location.location_name,
        primary_category=location.primary_category,
        average_rating=location.average_rating,
        total_reviews=location.total_reviews,
        description=location.description,
        logo=logo,
        cover=cover,
        address=readable_address,
        city=location.city,
        state=location.state,
        phone=location.phone,
        social_links=_extract_social_links(location.google_attributes),
        website=location.website,
        # Stored as a bare list of GBP periods; the frontend/JSON-LD expect {"periods": [...]}.
        business_hours={"periods": location.business_hours} if isinstance(location.business_hours, list) else location.business_hours,
        latlng=location.latlng,
        maps_url=maps_url,
        review_url=review_url,
        service_items=services,
        photos=photos,
        reviews=public_reviews,
        status=microsite.status
    )
    # Only published responses reach here (draft/unpublished raised above).
    if microsite.status == "published":
        try:
            get_redis().setex(cache_key, _PUBLIC_MICROSITE_CACHE_TTL, result.model_dump_json())
        except Exception:
            pass
    return result


def _notify_recipients(db: Session, location: Location) -> list:
    """Lead-email recipients (all respecting the per-user opt-out):
      • org Owners/Admins (org-wide access), plus
      • Regional/Store Managers assigned to THIS location, plus
      • the optional per-location lead_email override.
    """
    from app.models.user_location_access import UserLocationAccess

    org_wide = db.query(User).filter(
        User.organization_id == location.organization_id,
        User.role.in_(["Owner", "Admin"]),
        User.lead_email_notifications == True,  # noqa: E712 — respect per-user opt-out
    )
    # Managers (Regional/Store) only for the location the lead came in on.
    assigned = db.query(User).join(
        UserLocationAccess, UserLocationAccess.user_id == User.id
    ).filter(
        User.organization_id == location.organization_id,
        User.role.in_(["Regional Manager", "Store Manager"]),
        User.lead_email_notifications == True,  # noqa: E712
        UserLocationAccess.location_id == location.id,
    )
    emails = [u.email for u in org_wide.all() if u.email]
    emails += [u.email for u in assigned.all() if u.email]
    if location.lead_email:
        emails.append(location.lead_email)
    # de-dupe, preserve order
    seen, out = set(), []
    for e in emails:
        k = e.lower()
        if k not in seen:
            seen.add(k); out.append(e)
    return out


@router.post("/{location_slug}/leads", status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(rate_limit)])
def create_lead(location_slug: str, payload: LeadCreate, db: Session = Depends(get_db)):
    """Public lead capture from a microsite form. Always stores the lead; emails
    org admins best-effort (never blocks on email failure)."""
    microsite = db.query(Microsite).filter(Microsite.location_slug == location_slug).first()
    if not microsite or microsite.status != "published":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    location = microsite.location
    if not location:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    lead = Lead(
        organization_id=microsite.organization_id,
        location_id=location.id,
        name=payload.name,
        phone=payload.phone,
        email=payload.email,
        message=payload.message,
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)

    # Best-effort email notification — failure must not break the submission.
    try:
        recipients = _notify_recipients(db, location)
        if recipients:
            html = f"""
            <h2>New lead from your microsite</h2>
            <p><strong>Location:</strong> {location.location_name}</p>
            <p><strong>Name:</strong> {lead.name}</p>
            <p><strong>Phone:</strong> {lead.phone or '-'}</p>
            <p><strong>Email:</strong> {lead.email or '-'}</p>
            <p><strong>Message:</strong><br>{(lead.message or '-')}</p>
            """
            send_email(recipients, f"New lead — {location.location_name}", html)
    except Exception as e:
        logger.warning("Lead email failed (lead %s stored): %s", lead.id, e)

    # Best-effort web push to the org's subscribed dashboard users.
    try:
        from app.services.push_service import send_push_to_org
        # No customer PII in the notification body — details are shown only after
        # the user clicks through and is authenticated (safe on shared devices).
        send_push_to_org(
            db, microsite.organization_id,
            title=f"New enquiry — {location.location_name}",
            body="Tap to view the lead in your dashboard.",
            url=f"/dashboard/locations/{location.id}",
        )
    except Exception as e:
        logger.warning("Lead push failed (lead %s stored): %s", lead.id, e)

    return {"ok": True, "id": lead.id}
