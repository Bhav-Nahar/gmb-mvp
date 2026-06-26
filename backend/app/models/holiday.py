from sqlalchemy import Column, Integer, String, Date, DateTime, ForeignKey, func, UniqueConstraint, Index
from app.db.session import Base


class Holiday(Base):
    """Platform-wide holidays/festivals shown as overlays on the post calendar.

    Global, not org-scoped: holidays are the same for everyone, so a super-admin
    curates one shared table (seeded from the open-source `holidays` package and
    topped up via CSV). `region` tags state-specific festivals (e.g. "TN" for
    Pongal) so the UI can filter; null/"IN" means pan-India.
    """
    __tablename__ = "holidays"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)
    name = Column(String, nullable=False)
    category = Column(String, default="festival", nullable=False)  # festival | holiday | observance
    region = Column(String, nullable=True)   # e.g. "IN" national, "TN"/"KL" state; null = national
    country = Column(String, default="IN", nullable=False)
    source = Column(String, default="library", nullable=False)  # library | csv | manual
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        # Same name on the same day in the same region is a duplicate — lets re-seed
        # and re-upload be idempotent. region coalesced to '' for the constraint.
        UniqueConstraint("date", "name", "region", name="uq_holiday_date_name_region"),
        Index("idx_holidays_date_range", "date"),
    )
