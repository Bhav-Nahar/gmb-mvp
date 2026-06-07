from sqlalchemy import Column, String, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from app.db.session import Base

class GbpAttributeMetadata(Base):
    __tablename__ = "gbp_attribute_metadata"
    category_id = Column(String(100), primary_key=True)
    region_code = Column(String(2), primary_key=True)
    language_code = Column(String(5), primary_key=True)
    metadata_json = Column(JSONB, nullable=False)
    etag = Column(String(255), nullable=True)
    metadata_version = Column(String(50), nullable=True)
    last_fetched_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
