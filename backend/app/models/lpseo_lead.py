from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text, func, Index
from app.db.session import Base


class LpseoLead(Base):
    """An enquiry from a public Local-SEO landing-page audit form.

    Deliberately NOT the `leads` table: that one is tenant data (organization_id and
    location_id are both required) captured from a customer's own microsite, and it
    surfaces in that customer's dashboard. These are Pinzo's own marketing leads with
    no org behind them, read only by super-admins.

    Not a CRM. No owner, no pipeline, no notes: just the submitted fields, where it
    came from and whether the notification email got out."""

    __tablename__ = "lpseo_leads"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String, nullable=False)
    clinic = Column(String, nullable=True)  # business or group name
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    website = Column(String, nullable=True)
    locations = Column(String, nullable=True)
    goal = Column(String, nullable=True)
    message = Column(Text, nullable=True)

    # Route the form was submitted from, e.g. /en-in/local-seo-services/dentists-in-mumbai.
    page = Column(String, nullable=True, index=True)

    utm_source = Column(String, nullable=True)
    utm_medium = Column(String, nullable=True)
    utm_campaign = Column(String, nullable=True)
    gclid = Column(String, nullable=True)
    landing_page = Column(String, nullable=True)

    # False means the super-admin notification never went out (missing Resend key,
    # rejected sender, timeout). The row is still the lead; this flags the ones
    # nobody was told about.
    emailed = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_lpseo_leads_created_at", "created_at"),
    )
