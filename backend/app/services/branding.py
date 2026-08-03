"""Which logo and website go on an org's exported reports.

One resolver, used by both the PDF/print export and the weekly report email, so
the two can never disagree about whose brand a client is looking at. An org only
gets its own branding when a super-admin has flipped is_agency — an ordinary org
uploading a logo must not silently start shipping unbranded-by-us reports.
"""
from app.core.config import settings

PINZO = {
    "name": "Pinzo",
    "logo_url": f"{settings.FRONTEND_URL.rstrip('/')}/logo-horizontal-3.png",
    "website_url": settings.FRONTEND_URL.rstrip("/"),
}


def report_branding(org) -> dict:
    """Return {name, logo_url, website_url} for this org's exports.

    Falls back per-field, not all-or-nothing: an agency that set a logo but no
    website still gets its logo, with Pinzo's URL underneath rather than a blank.
    """
    if not org or not org.is_agency:
        return dict(PINZO)
    return {
        "name": org.brand_name or org.name or PINZO["name"],
        "logo_url": org.brand_logo_url or PINZO["logo_url"],
        "website_url": org.brand_website_url or PINZO["website_url"],
    }
