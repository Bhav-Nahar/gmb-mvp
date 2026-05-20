from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.db.session import get_db, engine
from app.core.config import settings
from app.worker import celery  # Must be initialized before routers are imported
from app.api import auth, locations, users

app = FastAPI(
    title="Google Business Profile Sync Service",
    description="Backend service managing GMB OAuth, scheduled metadata synchronization, and team roles.",
    version="1.0.0"
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

# Register routers under api/v1 prefix
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(locations.router, prefix="/api/v1/locations", tags=["Locations"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])

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
