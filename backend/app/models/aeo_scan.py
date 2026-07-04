from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.db.session import Base


class AEOScan(Base):
    """One AI-search-visibility (AEO) scan for a location.

    A scan asks a set of local queries against AI answer surfaces (Google AI
    Overview / AI Mode, and — on Pro — ChatGPT/Gemini/Perplexity + brand
    share-of-voice) and records where this business shows up. The whole result
    is stored as a single JSONB blob (`result`) because it's read/written as a
    unit, never per-row — same reasoning as LocalRankScan.cells.

    Status: Pending (queued) -> Completed | Failed. The provider fills results.
    Quota: one manual scan per location per calendar month (both plans) — see
    aeo_service.used_this_month.
    """
    __tablename__ = "aeo_scans"

    id = Column(Integer, primary_key=True, index=True)

    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    tier = Column(String, nullable=False)  # "google" (Basic) | "full" (Pro)
    status = Column(String, nullable=False, server_default="Pending")  # Pending | Completed | Failed

    ai_visibility_score = Column(Integer, nullable=True)  # 0-100 headline
    score_delta = Column(Integer, nullable=True)          # vs previous scan
    queries_tracked = Column(Integer, nullable=False, server_default="0")

    # Full contract: {surfaces:[...], queries:[...], share_of_voice:[...], recommendations:[...]}
    result = Column(JSONB, nullable=False, server_default="{}")
    error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_aeo_scans_location_created", "location_id", "created_at"),
    )
