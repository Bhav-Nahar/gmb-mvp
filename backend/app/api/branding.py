"""Agency white-label branding settings.

GET is open to any staff member — the export header needs it on every analytics
page, whatever the reader's role. PATCH is Owner/Admin only, and 403s unless a
super-admin has marked the org as an agency.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.api.deps import admin_required, get_current_user, get_db
from app.models.audit_log import AuditLog
from app.models.organization import Organization
from app.models.user import User
from app.services.branding import report_branding

logger = logging.getLogger(__name__)
router = APIRouter()


class BrandingUpdate(BaseModel):
    """Empty string clears a field back to the Pinzo default; null leaves it alone."""
    brand_name: str | None = Field(default=None, max_length=120)
    brand_logo_url: str | None = Field(default=None, max_length=500)
    brand_website_url: str | None = Field(default=None, max_length=500)

    @field_validator("brand_logo_url", "brand_website_url")
    @classmethod
    def _https_only(cls, v):
        # These land in an <img src> and an <a href> on an exported report and in an
        # email, so anything that isn't a plain https URL (javascript:, data:) has no
        # business here. http:// is refused too: a plain-http logo is blocked as mixed
        # content by the browser printing the PDF and by most mail clients, so it would
        # silently render as a broken image on the client's report.
        if v is None or v == "":
            return v
        if not v.startswith("https://"):
            raise ValueError("must be an https:// URL")
        return v


def _org(db: Session, user: User) -> Organization:
    org = db.query(Organization).filter(Organization.id == user.organization_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    return org


@router.get("/branding")
def get_branding(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """What to stamp on this org's exports, plus whether the settings UI should show."""
    org = _org(db, user)
    return {
        "is_agency": org.is_agency,
        "branding": report_branding(org),
        # The raw stored values, so the settings form shows blanks (not the Pinzo
        # fallbacks) for fields this agency has never filled in.
        "saved": {
            "brand_name": org.brand_name,
            "brand_logo_url": org.brand_logo_url,
            "brand_website_url": org.brand_website_url,
        },
    }


@router.patch("/branding")
def update_branding(
    payload: BrandingUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(admin_required),
):
    org = _org(db, user)
    if not org.is_agency:
        raise HTTPException(
            status_code=403,
            detail="Agency branding is not enabled for this account. Contact support.",
        )
    changes = {}
    for field in ("brand_name", "brand_logo_url", "brand_website_url"):
        new = getattr(payload, field)
        if new is None:
            continue
        new = new.strip() or None
        if getattr(org, field) != new:
            changes[field] = {"old": getattr(org, field), "new": new}
            setattr(org, field, new)
    if changes:
        # Whose logo is on a client's report is a support question ("this PDF says
        # RankWise, why?"), so the change is recorded like every other override.
        db.add(AuditLog(
            organization_id=org.id, user_id=user.id, actor_user_id=user.id,
            action="branding.update",
            details=json.dumps({"changes": changes}, default=str),
        ))
    db.commit()
    logger.info("Branding updated for org %s by user %s (%s)", org.id, user.id, list(changes))
    return {"message": "Branding updated", "branding": report_branding(org)}
