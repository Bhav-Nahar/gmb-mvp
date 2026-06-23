from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, func, Index, and_
from sqlalchemy.orm import relationship
from app.db.session import Base

class CustomGroup(Base):
    __tablename__ = "custom_groups"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    organization = relationship("Organization")
    locations = relationship("CustomGroupLocation", back_populates="custom_group", cascade="all, delete-orphan")
    daily_insights = relationship(
        "GroupDailyInsight",
        primaryjoin="and_(GroupDailyInsight.group_id == CustomGroup.id, GroupDailyInsight.group_type == 'CUSTOM_GROUP')",
        foreign_keys="[GroupDailyInsight.group_id]",
        cascade="all, delete-orphan",
        overlaps="daily_insights"
    )


    __table_args__ = (
        Index("ix_custom_groups_org_name", "organization_id", "name", unique=True),
    )
