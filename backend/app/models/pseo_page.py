import enum
from sqlalchemy import Column, String, Integer, DateTime, JSON, func, Index
from app.db.session import Base


class PseoPageStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class PseoPage(Base):
    """Programmatic SEO landing page (industry x city). All section copy lives in
    `content` (JSON) so new sections never need a migration; identity + meta are
    real columns for querying and uniqueness."""

    __tablename__ = "pseo_pages"

    id = Column(Integer, primary_key=True, index=True)
    # Single-level public URL: pinzo.io/{slug} (same namespace as microsites,
    # resolved after microsites in the frontend [slug] route).
    slug = Column(String, nullable=False, unique=True)
    industry_label = Column(String, nullable=False)
    industry_slug = Column(String, nullable=False)
    city_label = Column(String, nullable=False)
    city_slug = Column(String, nullable=False)

    # Market. ISO-3166 alpha-2, lowercase (in, us, gb...). Drives the locale
    # ("en-{country}"), the URL prefix (/en-us/gbp-management/...), hreflang and
    # geotargeting. English-only content for now; add a language column if that changes.
    country = Column(String, nullable=False, default="in")

    meta_title = Column(String, nullable=False)
    meta_description = Column(String, nullable=False)
    h1 = Column(String, nullable=False)
    # Blank -> self-canonical to the page's own locale URL. Set to point a thin/variant
    # page at its canonical target.
    canonical_url = Column(String, nullable=True)
    # "index" | "noindex" — lets low-quality pages publish without being indexed.
    index_status = Column(String, nullable=False, default="index")
    # Optional QA gate score (0-100) from the content brief; can drive auto-noindex.
    quality_score = Column(Integer, nullable=True)

    # All template sections + softer SEO fields (keywords, related_pages,
    # internal_links, page_type, template_version, region, last_updated).
    content = Column(JSON, nullable=False, default=dict)

    status = Column(String, nullable=False, default=PseoPageStatus.DRAFT.value)
    published_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_pseo_pages_status", "status"),
        Index("ix_pseo_pages_industry_city", "industry_slug", "city_slug"),
        Index("ix_pseo_pages_country_status", "country", "status"),
    )
