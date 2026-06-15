import re
from typing import List, Dict
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.reply_template import ReplyTemplate
from app.schemas.reply_template import ReplyTemplateCreate, ReplyTemplateUpdate

# Max templates allowed per star rating
STAR_RATING_LIMITS: Dict[int, int] = {
    1: 5,
    2: 3,
    3: 3,
    4: 3,
    5: 5,
}

class ReplyTemplateService:
    @staticmethod
    def validate_template_variables(body: str) -> None:
        """
        Validates that the only double-curly brace variables used are
        {{reviewer_name}} and {{location_name}}.
        """
        vars_found = re.findall(r"\{\{\s*(\w+)\s*\}\}", body)
        allowed = {"reviewer_name", "location_name"}
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
    def delete_template(db: Session, organization_id: int, template_id: int) -> None:
        template = db.query(ReplyTemplate).filter(
            ReplyTemplate.id == template_id,
            ReplyTemplate.organization_id == organization_id
        ).first()
        
        if not template:
            raise HTTPException(status_code=404, detail="Template not found")
            
        db.delete(template)
        db.commit()

    @staticmethod
    def resolve_variables(body: str, reviewer_name: str, location_name: str) -> str:
        replacements = {"reviewer_name": reviewer_name, "location_name": location_name}
        return re.sub(
            r"\{\{\s*(\w+)\s*\}\}",
            lambda m: replacements.get(m.group(1), m.group(0)),
            body,
        )
