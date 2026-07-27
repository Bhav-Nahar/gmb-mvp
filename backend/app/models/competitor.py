from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
from app.db.session import Base


class TrackedCompetitor(Base):
    """A competitor a user chose to track for one location.

    Identified by Google place_id (exact match against rank-scan results). Snapshots
    are harvested for free from completed local-rank scans; a paid Business Data
    refresh can later write the same snapshot rows without schema changes.
    """
    __tablename__ = "tracked_competitors"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True)

    place_id = Column(String, nullable=False)
    name = Column(String, nullable=False)
    category = Column(String, nullable=True)
    address = Column(String, nullable=True)
    lat = Column(Float, nullable=True)
    lng = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("location_id", "place_id", name="uq_tracked_competitor_location_place"),
    )


class CompetitorSnapshot(Base):
    """Point-in-time public metrics for a tracked competitor, harvested from a scan."""
    __tablename__ = "competitor_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    competitor_id = Column(Integer, ForeignKey("tracked_competitors.id", ondelete="CASCADE"), nullable=False, index=True)
    scan_id = Column(Integer, ForeignKey("local_rank_scans.id", ondelete="SET NULL"), nullable=True)

    rating = Column(Float, nullable=True)
    review_count = Column(Integer, nullable=True)
    photo_count = Column(Integer, nullable=True)
    # Visibility in the scan this snapshot came from
    best_rank = Column(Integer, nullable=True)
    avg_rank = Column(Float, nullable=True)
    appearances = Column(Integer, nullable=True)   # cells the competitor appeared in
    total_cells = Column(Integer, nullable=True)
    keyword = Column(String, nullable=True)

    captured_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_competitor_snapshots_comp_captured", "competitor_id", "captured_at"),
    )
