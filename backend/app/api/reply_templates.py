from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import get_current_user, admin_required
from app.models.user import User
from app.schemas.reply_template import ReplyTemplateCreate, ReplyTemplateUpdate, ReplyTemplateResponse
from app.services.reply_template_service import ReplyTemplateService
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", response_model=List[ReplyTemplateResponse])
def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """List all reply templates for the current organization."""
    try:
        return ReplyTemplateService.list_templates(db, current_user.organization_id)
    except Exception as e:
        logger.error(f"Failed to list templates: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.post("/", response_model=ReplyTemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(
    data: ReplyTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Create a new reply template."""
    try:
        return ReplyTemplateService.create_template(
            db, 
            organization_id=current_user.organization_id, 
            user_id=current_user.id, 
            data=data
        )
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to create template: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.put("/{template_id}", response_model=ReplyTemplateResponse)
def update_template(
    template_id: int,
    data: ReplyTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Update an existing reply template."""
    try:
        return ReplyTemplateService.update_template(
            db, 
            organization_id=current_user.organization_id, 
            template_id=template_id, 
            data=data
        )
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Failed to update template: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Delete a reply template."""
    try:
        ReplyTemplateService.delete_template(db, current_user.organization_id, template_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete template: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")
