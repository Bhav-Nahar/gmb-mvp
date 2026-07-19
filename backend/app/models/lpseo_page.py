import enum
from sqlalchemy import Column, String, Integer, DateTime, JSON, func, Index
from app.db.session import Base


class LpseoPageStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class LpseoPage(Base):
    """Local-SEO programmatic landing page (industry x city), sibling of PseoPage.

    Same shape as pseo_pages on purpose (identity + meta columns, all section copy
    in `content` JSON), but a SEPARATE table so the two page types never collide on
    slug: `dentists-in-mumbai` is a valid slug for both the GBP page (/gbp-management)
    and this managed-local-SEO page (/local-seo-services). The URL segment differs;
    the slug string is identical. Keeping them apart means editing one never touches
    the live behaviour of the other."""

    __tablename__ = "lpseo_pages"

    id = Column(Integer, primary_key=True, index=True)
    # Public URL: /{locale}/local-seo-services/{slug}. Unique within this table only.
    slug = Column(String, nullable=False, unique=True)
    industry_label = Column(String, nullable=False)
    industry_slug = Column(String, nullable=False)
    city_label = Column(String, nullable=False)
    city_slug = Column(String, nullable=False)

    # ISO-3166 alpha-2, lowercase — drives locale ("en-{country}"), URL prefix,
    # hreflang. English-only content for now.
    country = Column(String, nullable=False, default="in")

    meta_title = Column(String, nullable=False)
    meta_description = Column(String, nullable=False)
    h1 = Column(String, nullable=False)
    # Blank -> self-canonical to the page's own locale URL.
    canonical_url = Column(String, nullable=True)
    # "index" | "noindex".
    index_status = Column(String, nullable=False, default="index")
    # Optional QA gate score (0-100); < gate auto-noindexes.
    quality_score = Column(Integer, nullable=True)

    content = Column(JSON, nullable=False, default=dict)

    status = Column(String, nullable=False, default=LpseoPageStatus.DRAFT.value)
    published_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_lpseo_pages_status", "status"),
        Index("ix_lpseo_pages_industry_city", "industry_slug", "city_slug"),
        Index("ix_lpseo_pages_country_status", "country", "status"),
    )
