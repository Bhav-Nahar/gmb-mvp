from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, Text
from sqlalchemy.dialects.postgresql import JSONB
from app.db.session import Base

class GbpAttributeDefinition(Base):
    __tablename__ = "gbp_attribute_definitions"
    id = Column(Integer, primary_key=True, index=True)
    attribute_id = Column(String(255), nullable=False)
    category_id = Column(String(100), nullable=False)
    region_code = Column(String(2), nullable=False)
    language_code = Column(String(5), nullable=False)
    display_name = Column(Text, nullable=True)
    group_display_name = Column(Text, nullable=True)
    value_type = Column(String(50), nullable=False) # BOOL, ENUM, REPEATED_ENUM, URL, etc.
    is_repeatable = Column(Boolean, default=False)
    is_required = Column(Boolean, default=False)
    options_json = Column(JSONB, nullable=True) # Allowed options for ENUM types
    raw_schema = Column(JSONB, nullable=True)
    is_active = Column(Boolean, default=True)
    deprecated_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
