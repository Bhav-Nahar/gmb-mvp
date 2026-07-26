import enum
from sqlalchemy import Column, String, Integer, DateTime, JSON, func, Index
from app.db.session import Base


class CseoPageStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class CseoPage(Base):
    """Country pillar for the Local SEO universe: one row per market, served at
    /{locale}/local-seo-services/.

    Third sibling of pseo_pages and lpseo_pages, and a separate table for the same
    reason they are separate: it owns a different URL shape (a bare country hub, not
    an {industry}-in-{city} leaf) and its own content schema. It is also the parent
    those leaves link back up to, so it must be editable without touching them.

    There is at most one row per country. `country` carries the unique constraint
    rather than a slug, because the slug segment is the constant
    "local-seo-services" in every market."""

    __tablename__ = "cseo_pages"

    id = Column(Integer, primary_key=True, index=True)
    # ISO-3166 alpha-2, lowercase. Drives locale ("en-{country}") and the URL prefix.
    country = Column(String, nullable=False, unique=True)
    country_label = Column(String, nullable=False)

    meta_title = Column(String, nullable=False)
    meta_description = Column(String, nullable=False)
    h1 = Column(String, nullable=False)
    canonical_url = Column(String, nullable=True)
    # "index" | "noindex". The package ships "noindex,nofollow" during staging.
    index_status = Column(String, nullable=False, default="noindex")
    # QA gate (0-100); below the gate the page is served noindex regardless.
    quality_score = Column(Integer, nullable=True)

    content = Column(JSON, nullable=False, default=dict)

    status = Column(String, nullable=False, default=CseoPageStatus.DRAFT.value)
    published_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_cseo_pages_status", "status"),
    )
