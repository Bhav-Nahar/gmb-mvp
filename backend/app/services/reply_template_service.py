import re
import random
from typing import List, Dict, Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.reply_template import ReplyTemplate
from app.models.organization import Organization
from app.schemas.reply_template import ReplyTemplateCreate, ReplyTemplateUpdate

# Max templates allowed per star rating
STAR_RATING_LIMITS: Dict[int, int] = {
    1: 5,
    2: 3,
    3: 3,
    4: 3,
    5: 5,
}

# Auto-reply picks at random among the N least-used templates for a rating, to
# spread usage and avoid posting the same reply over and over (looks spammy to
# Google). N == the largest per-rating cap above, so today this means "all of
# them, weighted toward least-used".
# ponytail: pool == per-rating template cap; promote to a setting only if
# STAR_RATING_LIMITS ever grows past this — one-line change.
TEMPLATE_SELECTION_POOL = 5

# Auto-reply only fires on positive reviews, and needs at least this many templates
# across those ratings before it can be turned on — 1 template means the same reply
# every time, which reads as spam.
AUTO_REPLY_RATINGS = (4, 5)
MIN_TEMPLATES_FOR_AUTO_REPLY = 2

# Template variable name -> which underlying value it renders to. Aliases
# (customer/business/location) point at data we already hold, so they cost nothing.
# {{date}} is deliberately omitted — a date in a public reply reads oddly (YAGNI).
_VARIABLE_ALIASES: Dict[str, str] = {
    "reviewer_name": "reviewer_name",
    "customer": "reviewer_name",
    "first_name": "first_name",
    "location_name": "location_name",
    "location": "location_name",
    "business": "location_name",
    "city": "city",
    "phone": "phone",
    "website": "website",
    "rating": "rating",
}

class ReplyTemplateService:
    @staticmethod
    def validate_template_variables(body: str) -> None:
        """
        Validates that the only double-curly brace variables used are
        {{reviewer_name}} and {{location_name}}.
        """
        vars_found = re.findall(r"\{\{\s*(\w+)\s*\}\}", body)
        allowed = set(_VARIABLE_ALIASES)
        for v in vars_found:
            if v not in allowed:
                raise ValueError(f"Invalid template variable: {{{{{v}}}}}")

    @staticmethod
    def list_templates(db: Session, organization_id: int) -> List[ReplyTemplate]:
        return db.query(ReplyTemplate).filter(
            ReplyTemplate.organization_id == organization_id
        ).order_by(
            ReplyTemplate.star_rating.asc(),
            ReplyTemplate.display_order.asc(),
            ReplyTemplate.id.asc()
        ).all()

    @staticmethod
    def fetch_all_grouped(db: Session, organization_id: int) -> Dict[int, List[ReplyTemplate]]:
        templates = db.query(ReplyTemplate).filter(
            ReplyTemplate.organization_id == organization_id
        ).order_by(
            ReplyTemplate.star_rating.asc(),
            ReplyTemplate.display_order.asc(),
            ReplyTemplate.id.asc()
        ).all()

        grouped: Dict[int, List[ReplyTemplate]] = {i: [] for i in range(1, 6)}
        for t in templates:
            grouped[t.star_rating].append(t)
        return grouped

    @staticmethod
    def create_template(db: Session, organization_id: int, user_id: int, data: ReplyTemplateCreate) -> ReplyTemplate:
        ReplyTemplateService.validate_template_variables(data.body)
        
        limit = STAR_RATING_LIMITS.get(data.star_rating, 0)

        # Lock existing rows for this (org, star) so two concurrent creates can't
        # both pass the limit check and exceed the cap. We fetch-and-count in
        # Python because Postgres rejects FOR UPDATE inside an aggregate subquery
        # (which is what .count() would generate).
        locked_rows = db.query(ReplyTemplate.id).filter(
            ReplyTemplate.organization_id == organization_id,
            ReplyTemplate.star_rating == data.star_rating
        ).with_for_update().all()
        count = len(locked_rows)

        if count >= limit:
            raise ValueError(f"Maximum {limit} templates allowed for {data.star_rating}-star rating")
            
        # Check for duplicate title
        existing = db.query(ReplyTemplate).filter(
            ReplyTemplate.organization_id == organization_id,
            ReplyTemplate.star_rating == data.star_rating,
            ReplyTemplate.title == data.title
        ).first()
        if existing:
            raise ValueError(f"A template with the title '{data.title}' already exists for this rating")
            
        template = ReplyTemplate(
            organization_id=organization_id,
            star_rating=data.star_rating,
            title=data.title,
            body=data.body,
            display_order=data.display_order,
            created_by_user_id=user_id
        )
        db.add(template)
        db.commit()
        db.refresh(template)
        return template

    @staticmethod
    def update_template(db: Session, organization_id: int, template_id: int, data: ReplyTemplateUpdate) -> ReplyTemplate:
        template = db.query(ReplyTemplate).filter(
            ReplyTemplate.id == template_id,
            ReplyTemplate.organization_id == organization_id
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
            
        if data.body is not None:
            ReplyTemplateService.validate_template_variables(data.body)
            template.body = data.body
            
        if data.title is not None:
            # Check for duplicate title
            existing = db.query(ReplyTemplate).filter(
                ReplyTemplate.organization_id == organization_id,
                ReplyTemplate.star_rating == template.star_rating,
                ReplyTemplate.title == data.title,
                ReplyTemplate.id != template_id
            ).first()
            if existing:
                raise ValueError(f"A template with the title '{data.title}' already exists for this rating")
            template.title = data.title
            
        if data.display_order is not None:
            template.display_order = data.display_order
            
        db.commit()
        db.refresh(template)
        return template

    @staticmethod
    def delete_template(db: Session, organization_id: int, template_id: int) -> bool:
        """Delete a template. Returns True if this forced org-wide auto-reply OFF
        because it dropped 4-5★ coverage below the minimum (keeps the invariant
        'auto-reply on => at least MIN_TEMPLATES_FOR_AUTO_REPLY positive templates')."""
        template = db.query(ReplyTemplate).filter(
            ReplyTemplate.id == template_id,
            ReplyTemplate.organization_id == organization_id
        ).first()

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        star = template.star_rating
        db.delete(template)
        db.flush()  # so the count below sees the deletion within this transaction

        auto_reply_disabled = False
        if star in AUTO_REPLY_RATINGS:
            org = db.query(Organization).filter(Organization.id == organization_id).first()
            # AI mode does not use templates, so losing one must not switch it off.
            if org and org.auto_reply_enabled_at is not None and org.auto_reply_mode != "ai" and \
                    ReplyTemplateService.count_positive_templates(db, organization_id) < MIN_TEMPLATES_FOR_AUTO_REPLY:
                org.auto_reply_enabled_at = None
                auto_reply_disabled = True

        db.commit()
        return auto_reply_disabled

    @staticmethod
    def resolve_variables(body: str, reviewer_name: str, location_name: str, rating: Optional[int] = None,
                          city: Optional[str] = None, phone: Optional[str] = None,
                          website: Optional[str] = None) -> str:
        first_name = (reviewer_name or "").strip().split(" ")[0] if reviewer_name else ""
        values = {
            "reviewer_name": reviewer_name or "",
            "first_name": first_name,
            "location_name": location_name or "",
            "city": city or "",
            "phone": phone or "",
            "website": website or "",
            "rating": str(rating) if rating is not None else "",
        }

        def _repl(m):
            target = _VARIABLE_ALIASES.get(m.group(1))
            return values.get(target, m.group(0)) if target else m.group(0)

        return re.sub(r"\{\{\s*(\w+)\s*\}\}", _repl, body)

    @staticmethod
    def count_positive_templates(db: Session, organization_id: int) -> int:
        """Number of templates across the auto-reply ratings (4-5★)."""
        return db.query(ReplyTemplate).filter(
            ReplyTemplate.organization_id == organization_id,
            ReplyTemplate.star_rating.in_(AUTO_REPLY_RATINGS),
        ).count()

    @staticmethod
    def pick_least_used(db: Session, organization_id: int, star_rating: int) -> Optional[ReplyTemplate]:
        """Random choice among the least-used templates for a rating (spreads usage,
        avoids repeating the same reply). Returns None if no template exists."""
        rows = db.query(ReplyTemplate).filter(
            ReplyTemplate.organization_id == organization_id,
            ReplyTemplate.star_rating == star_rating,
        ).order_by(
            ReplyTemplate.usage_count.asc(),
            ReplyTemplate.id.asc(),
        ).limit(TEMPLATE_SELECTION_POOL).all()
        return random.choice(rows) if rows else None
