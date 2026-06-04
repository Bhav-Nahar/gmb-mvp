from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db, engine
from app.core.config import settings
from app.worker import celery  # Must be initialized before routers are imported
from app.api import auth, locations, users, reviews, posts, media, listing_edits, insights
from app.api.deps import check_csrf
import os
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="Google Business Profile Sync Service",
    description="Backend service managing GMB OAuth, scheduled metadata synchronization, and team roles.",
    version="1.0.0",
    dependencies=[Depends(check_csrf)]
)

# CORS configurations to support Next.js frontend
# Include both localhost and 127.0.0.1 variants to cover all browser address bar forms
allow_origins = [
    settings.FRONTEND_URL,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount local uploads directory for static file serving in development
static_uploads_path = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
)
os.makedirs(static_uploads_path, exist_ok=True)
app.mount("/static/uploads", StaticFiles(directory=static_uploads_path), name="static_uploads")

# Register routers under api/v1 prefix
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(locations.router, prefix="/api/v1/locations", tags=["Locations"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(reviews.router, prefix="/api/v1/reviews", tags=["Reviews"])
app.include_router(posts.router, prefix="/api/v1/posts", tags=["Posts"])
app.include_router(media.router, prefix="/api/v1/media", tags=["Media"])
app.include_router(listing_edits.router, prefix="/api/v1", tags=["Listing Edits"])
app.include_router(insights.router, prefix="/api/v1/insights", tags=["Insights"])
@app.get("/")
def health_check(db: Session = Depends(get_db)):
    """Health check endpoint validating service and database status."""
    try:
        # Simple query to check DB connectivity (SQLAlchemy 2.x requires text())
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
        
    return {
        "status": "online",
        "database": db_status,
        "environment": "development"
    }
