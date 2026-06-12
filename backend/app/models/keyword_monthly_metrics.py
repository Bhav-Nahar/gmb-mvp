from sqlalchemy import Column, Integer, String, Date, ForeignKey, Index, text
from sqlalchemy.orm import relationship
from app.db.session import Base

class KeywordMonthlyMetric(Base):
    __tablename__ = "keyword_monthly_metrics"

    id = Column(Integer, primary_key=True, index=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True)
    google_location_id = Column(String, nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    keyword = Column(String, nullable=False)
    impressions = Column(Integer, nullable=False, default=0, server_default=text("0"))

    __table_args__ = (
        Index("idx_keyword_monthly_location_period_kw", "location_id", "period_start", "keyword", unique=True),
        Index("idx_keyword_monthly_google_location_id", "google_location_id"),
    )

    location = relationship("Location", back_populates="keyword_metrics")
