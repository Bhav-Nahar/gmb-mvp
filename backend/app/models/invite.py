from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, func, text
from sqlalchemy.orm import relationship
from app.db.session import Base

class Invite(Base):
    __tablename__ = "invites"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, index=True, nullable=False)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String, default="Staff", nullable=False)  # Admin or Staff
    token = Column(String, unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    invited_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String, default="pending", nullable=False)  # pending, accepted, expired

    organization = relationship("Organization", back_populates="invites")
    invited_by = relationship("User", foreign_keys=[invited_by_user_id])

    __table_args__ = (
        Index(
            "uq_active_invite_email_org",
            "email",
            "organization_id",
            unique=True,
            postgresql_where=text("status = 'pending'")
        ),
    )
