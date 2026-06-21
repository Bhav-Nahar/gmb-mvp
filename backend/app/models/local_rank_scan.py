from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.db.session import Base


class LocalRankScan(Base):
    """One geo-grid local-rank scan for a location.

    A scan runs the same keyword search from N×N GPS points around the location
    and records the business's Maps rank at each point (the "heatmap"). Cells are
    stored as a JSONB list rather than a child table — a scan is read/written as a
    whole, never per-cell, so a separate table would only add joins.

    Status: Pending (queued) -> Completed | Failed. The Celery task fills results.
    """
    __tablename__ = "local_rank_scans"

    id = Column(Integer, primary_key=True, index=True)

    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    keyword = Column(String, nullable=False)
    grid_size = Column(Integer, nullable=False)      # 3, 5, 7 or 9 -> grid_size**2 points
    radius_miles = Column(Float, nullable=False)     # centre -> outermost ring

    status = Column(String, nullable=False, server_default="Pending")  # Pending | Completed | Failed
    # Summary metrics (Local-Falcon style): average rank over found cells, and
    # Share of Local Voice = % of cells where the business is in the top 3.
    avg_rank = Column(Float, nullable=True)
    solv = Column(Float, nullable=True)
    found_count = Column(Integer, nullable=False, server_default="0")
    total_cells = Column(Integer, nullable=False, server_default="0")
    # list of {row, col, lat, lng, rank|null, top_competitor|null}
    cells = Column(JSONB, nullable=False, server_default="[]")
    credits_charged = Column(Integer, nullable=False, server_default="0")
    error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_local_rank_scans_location_created", "location_id", "created_at"),
    )
