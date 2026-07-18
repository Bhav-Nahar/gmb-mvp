import logging
import os
import stat
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db, engine
from app.core.config import settings
from app.worker import celery  # Must be initialized before routers are imported
from app.api import auth, locations, users, reviews, posts, media, listing_edits, insights, dynamic_attributes, billing, location_media, reply_templates, descriptions, local_rank, admin, leaderboard, microsites, public_microsites, leads, push, holidays, aeo, pseo
from app.api.endpoints import comparison
from app.api.deps import check_csrf, check_billing_lock, require_feature, require_premium
from app.core import plan_config
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Google Business Profile Sync Service",
    description="Backend service managing GMB OAuth, scheduled metadata synchronization, and team roles.",
    version="1.0.0",
    dependencies=[Depends(check_csrf), Depends(check_billing_lock)]
)

# CORS configurations to support Next.js frontend
frontend_url = settings.FRONTEND_URL.rstrip("/")
allow_origins = [frontend_url]

# Support both www and non-www in production if a custom domain is used
if "localhost" not in frontend_url and "127.0.0.1" not in frontend_url:
    if "://www." in frontend_url:
        allow_origins.append(frontend_url.replace("://www.", "://"))
    else:
        allow_origins.append(frontend_url.replace("://", "://www."))

# Allow additional domains (e.g. a custom domain alongside the Vercel URL) via env.
# Each entry is also expanded to its www/non-www twin so callers don't have to list both.
for extra in (settings.ADDITIONAL_CORS_ORIGINS or "").split(","):
    origin = extra.strip().rstrip("/")
    if not origin:
        continue
    allow_origins.append(origin)
    if "://www." in origin:
        allow_origins.append(origin.replace("://www.", "://"))
    else:
        allow_origins.append(origin.replace("://", "://www."))

if getattr(settings, "APP_ENV", "production") == "development":
    allow_origins += [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

# De-duplicate while preserving order.
allow_origins = list(dict.fromkeys(allow_origins))
logger.info(f"CORS origins configured as: {allow_origins}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "X-Requested-With", "Accept", "X-Acting-Org"],
    expose_headers=["X-CSRF-Token"],
)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Ensure CORS headers are present on 500 errors so the browser sees the real error."""
    origin = request.headers.get("origin", "")
    headers = {}
    if origin in allow_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
        headers=headers,
    )


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Attach baseline security headers to every response.

    This is a JSON API consumed by a separate SPA, so the CSP is intentionally
    restrictive (no scripts/embedding from this origin). HSTS is only emitted in
    non-development environments to avoid pinning localhost to HTTPS.
    """
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'none'; frame-ancestors 'none'",
    )
    if getattr(settings, "APP_ENV", "production") != "development":
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return response

# Mount local uploads directory for static file serving in development
static_uploads_path = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
)
os.makedirs(static_uploads_path, exist_ok=True)
os.chmod(static_uploads_path, stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP)
app.mount("/static/uploads", StaticFiles(directory=static_uploads_path), name="static_uploads")

# Register routers under api/v1 prefix
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(locations.router, prefix="/api/v1/locations", tags=["Locations"])
app.include_router(microsites.router, prefix="/api/v1/locations", tags=["Microsites"],
                   dependencies=[Depends(require_premium)])
app.include_router(public_microsites.router, prefix="/api/v1/public/microsites", tags=["Public Microsites"])
app.include_router(leads.router, prefix="/api/v1/locations", tags=["Leads"])
app.include_router(push.router, prefix="/api/v1/push", tags=["Push"])
app.include_router(dynamic_attributes.router, prefix="/api/v1/locations", tags=["Dynamic Attributes"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(reviews.router, prefix="/api/v1/reviews", tags=["Reviews"])
app.include_router(posts.router, prefix="/api/v1/posts", tags=["Posts"],
                   dependencies=[Depends(require_premium)])
app.include_router(holidays.router, prefix="/api/v1/holidays", tags=["Holidays"])
app.include_router(media.router, prefix="/api/v1/media", tags=["Media"])
app.include_router(listing_edits.router, prefix="/api/v1", tags=["Listing Edits"])
app.include_router(descriptions.router, prefix="/api/v1", tags=["Descriptions"])
app.include_router(local_rank.router, prefix="/api/v1", tags=["Local Rank"],
                   dependencies=[Depends(require_premium)])
app.include_router(aeo.router, prefix="/api/v1", tags=["AI Visibility"],
                   dependencies=[Depends(require_premium)])
app.include_router(location_media.router, prefix="/api/v1", tags=["Location Media"])
app.include_router(insights.router, prefix="/api/v1/insights", tags=["Insights"],
                   dependencies=[Depends(require_premium)])
app.include_router(billing.router, prefix="/api/v1/billing", tags=["Billing"])
app.include_router(billing.webhook_router, prefix="/api/v1/webhooks", tags=["Webhooks"])
app.include_router(reply_templates.router, prefix="/api/v1/reply-templates", tags=["Reply Templates"],
                   dependencies=[Depends(require_feature(plan_config.FEATURE_TEMPLATES))])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["Admin"])
app.include_router(pseo.public_router, prefix="/api/v1/public/pseo", tags=["Public pSEO"])
app.include_router(pseo.admin_router, prefix="/api/v1/admin/pseo", tags=["Admin pSEO"])
app.include_router(leaderboard.router, prefix="/api/v1/leaderboard", tags=["Leaderboard"],
                   dependencies=[Depends(require_feature(plan_config.FEATURE_LEADERBOARD))])
app.include_router(comparison.router, prefix="/api/v1/comparison", tags=["Comparison"],
                   dependencies=[Depends(require_feature(plan_config.FEATURE_COMPARISON))])

@app.on_event("startup")
async def on_startup():
    app_env = getattr(settings, "APP_ENV", "production")
    jwt_set = bool(getattr(settings, "JWT_SECRET", None))
    enc_set = bool(getattr(settings, "ENCRYPTION_KEY", None))
    logger.info(
        "App starting — APP_ENV=%s JWT_SECRET=%s ENCRYPTION_KEY=%s",
        app_env,
        "set" if jwt_set else "NOT SET",
        "set" if enc_set else "NOT SET",
    )


@app.get("/")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint validating service and database status."""
    try:
        # Simple query to check DB connectivity (SQLAlchemy 2.x requires text())
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        logger.error("Database health check failed: %s", str(e))
        db_status = "unhealthy"

    return {
        "status": "online",
        "database": db_status
    }
