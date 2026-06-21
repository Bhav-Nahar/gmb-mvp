from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.db.session import Base


class DescriptionGeneration(Base):
    """One AI description generation for a location.

    Persisted only when the output passes the hard-policy validator (a blocked
    generation is never charged and never stored). Doubles as the regen history
    AND the first-vs-regenerate pricing signal: a location with no prior row is
    charged the first-generation price, otherwise the cheaper regen price.
    """
    __tablename__ = "description_generations"

    id = Column(Integer, primary_key=True, index=True)

    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    action = Column(String, nullable=False)  # generate_business_description | regenerate_business_description
    payload = Column(JSONB, nullable=False)  # the input: mode, tone, language, usp, services, audience, nudge

    generated_text = Column(Text, nullable=False)
    char_count = Column(Integer, nullable=False)
    # The model's own claim of what it referenced — fuzzy-matched against GBP data
    # by the gate, so we never need a second LLM call to score a generated description.
    category_mentioned = Column(String, nullable=True)
    locality_used = Column(String, nullable=True)
    improvement_notes = Column(JSONB, nullable=True)
    policy_flags = Column(JSONB, nullable=True)  # {"hard": [...], "soft": [...]} at generation time

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_description_generations_location_created", "location_id", "created_at"),
    )
