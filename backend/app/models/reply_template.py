from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, Index, func, text
from sqlalchemy.orm import relationship
from app.db.session import Base

class ReplyTemplate(Base):
    __tablename__ = "reply_templates"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    star_rating = Column(Integer, nullable=False)
    title = Column(String(100), nullable=False)
    body = Column(Text, nullable=False)
    display_order = Column(Integer, nullable=False, default=0, server_default=text("0"))
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    usage_count = Column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    organization = relationship("Organization", lazy="select")
    created_by = relationship("User", lazy="select")

    __table_args__ = (
        CheckConstraint("star_rating >= 1 AND star_rating <= 5", name="ck_reply_templates_star_rating"),
        UniqueConstraint("organization_id", "star_rating", "title", name="uq_reply_templates_org_star_title"),
        Index("idx_reply_templates_org_star", "organization_id", "star_rating"),
    )
