import math
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import get_current_user, staff_required, get_user_location_ids, require_location_access
from app.core.authorization import assert_location_active
from app.core.roles import Role, ADMIN_ROLES
from app.models.user import User
from app.models.location import Location
from app.models.review import Review
from app.schemas.review import ReviewResponse, ReviewListResponse, ReviewReplyRequest, GenerateReplyResponse
from app.providers.factory import ProviderFactory
from app.worker import celery as celery_app
from app.services.ai_reply_service import generate_reply
from app.services.billing.credit_service import CreditService
from app.llm.exceptions import LLMProviderError
from app.constants.review_sentiment import ALLOWED_SENTIMENTS, ALLOWED_ISSUE_CATEGORIES
from app.constants.sla import SLA_TIER_LIST
from sqlalchemy import func, extract

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/", response_model=ReviewListResponse)
def get_reviews(
    location_id: Optional[int] = None,
    is_replied: Optional[bool] = None,
    rating: Optional[int] = None,
    sentiment: Optional[str] = None,
    issue_category: Optional[str] = None,
    sla_tier: Optional[str] = None,
    overdue_only: bool = False,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    from sqlalchemy.orm import joinedload
    from app.services.reply_template_service import ReplyTemplateService
    query = db.query(Review).options(joinedload(Review.location)).filter(
        Review.organization_id == current_user.organization_id,
        Review.is_deleted == False
    )

    allowed_location_ids = get_user_location_ids(current_user, db)
    
    if location_id:
        if allowed_location_ids is not None and location_id not in allowed_location_ids:
            raise HTTPException(status_code=403, detail="You do not have access to this location")
        query = query.filter(Review.location_id == location_id)
    elif allowed_location_ids is not None:
        query = query.filter(Review.location_id.in_(allowed_location_ids))

    if is_replied is not None:
        query = query.filter(Review.is_replied == is_replied)
    if rating:
        query = query.filter(Review.rating == rating)
    if sentiment is not None:
        if sentiment not in ALLOWED_SENTIMENTS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid sentiment value. Allowed: {sorted(ALLOWED_SENTIMENTS)}"
            )
        query = query.filter(Review.sentiment == sentiment)
    if issue_category is not None:
        if issue_category not in ALLOWED_ISSUE_CATEGORIES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid issue_category value. Allowed: {sorted(ALLOWED_ISSUE_CATEGORIES)}"
            )
        query = query.filter(Review.issue_category == issue_category)

    if sla_tier is not None or overdue_only:
        query = query.join(Location, Review.location_id == Location.id)
        query = query.filter(
            Location.sla_tracking_started_at != None,
            Review.review_created_at >= Location.sla_tracking_started_at
        )

    if sla_tier is not None:
        if sla_tier not in SLA_TIER_LIST:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid sla_tier value. Allowed: {SLA_TIER_LIST}"
            )
        response_hours = extract('epoch', Review.reply_created_at - Review.review_created_at) / 3600.0
        query = query.filter(Review.is_replied == True, Review.reply_created_at != None)
        if sla_tier == "Best":
            query = query.filter(response_hours <= 12)
        elif sla_tier == "Good":
            query = query.filter(response_hours > 12, response_hours <= 24)
        elif sla_tier == "Average":
            query = query.filter(response_hours > 24, response_hours <= 72)
        elif sla_tier == "Poor":
            query = query.filter(response_hours > 72)

    if overdue_only:
        age_hours = extract('epoch', func.now() - Review.review_created_at) / 3600.0
        query = query.filter(Review.is_replied == False, age_hours > 72)

    total = db.query(func.count()).select_from(query.subquery()).scalar()
    pages = math.ceil(total / size) if total > 0 else 1

    reviews = query.order_by(Review.review_created_at.desc()).offset((page - 1) * size).limit(size).all()

    templates_by_star = ReplyTemplateService.fetch_all_grouped(db, current_user.organization_id)
    for r in reviews:
        r.suggested_templates = templates_by_star.get(r.rating, [])

    return ReviewListResponse(
        reviews=reviews,
        total=total,
        page=page,
        pages=pages
    )

@router.post("/sync", status_code=status.HTTP_202_ACCEPTED)
def trigger_reviews_sync(
    location_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    allowed_location_ids = get_user_location_ids(current_user, db)

    if location_id:
        if allowed_location_ids is not None and location_id not in allowed_location_ids:
            raise HTTPException(status_code=403, detail="You do not have access to this location")
            
        loc = db.query(Location).filter(
            Location.id == location_id,
            Location.organization_id == current_user.organization_id
        ).first()
        if not loc:
            raise HTTPException(status_code=404, detail="Location not found")
            
        task = celery_app.send_task("app.tasks.sync_reviews_task", args=[location_id, "Manual", current_user.id])
        return {"message": "Sync task has been queued for the location.", "task_id": task.id}
    else:
        if current_user.role not in ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Only Owners and Admins can trigger organization-wide sync")
            
        from app.core.config import settings
        chunk_size = getattr(settings, "REVIEW_SYNC_CHUNK_SIZE", 20)
        
        locations = db.query(Location).filter(
            Location.organization_id == current_user.organization_id
        ).all()
        loc_ids = [loc.id for loc in locations]
        
        task_ids = []
        for i in range(0, len(loc_ids), chunk_size):
            chunk = loc_ids[i:i + chunk_size]
            task = celery_app.send_task(
                "app.tasks.sync_reviews_chunk_task", 
                args=[chunk, current_user.organization_id, "Manual", current_user.id]
            )
            task_ids.append(task.id)
            
        return {"message": f"Sync tasks have been queued for {len(locations)} locations in {len(task_ids)} batches.", "task_ids": task_ids}

@router.post("/{id}/reply", response_model=ReviewResponse)
async def reply_to_review(
    id: int,
    payload: ReviewReplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    if current_user.role == Role.VIEWER:
        raise HTTPException(status_code=403, detail="Viewers cannot reply to reviews")

    review = db.query(Review).filter(
        Review.id == id,
        Review.organization_id == current_user.organization_id,
        Review.is_deleted == False
    ).first()
    
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
        
    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None and review.location_id not in allowed_location_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this location")

    assert_location_active(db, review.location_id)

    provider = ProviderFactory.get_provider(review.provider, current_user.organization_id, db)
    
    try:
        await provider.reply_review(review.provider_review_id, payload.reply_text)
    except Exception as e:
        logger.error("Failed to post reply to provider for review %s: %s", id, e, exc_info=True)
        raise HTTPException(status_code=502, detail="Failed to post reply to the review provider. Please try again later.")
        
    if review.reply_created_at is None:
        review.reply_created_at = datetime.now(timezone.utc)
    review.is_replied = True
    review.reply_text = payload.reply_text
    review.review_updated_at = datetime.now(timezone.utc)
    
    if getattr(payload, 'template_id', None) is not None:
        from app.models.reply_template import ReplyTemplate
        db.query(ReplyTemplate).filter(
            ReplyTemplate.id == payload.template_id,
            ReplyTemplate.organization_id == current_user.organization_id
        ).update(
            {ReplyTemplate.usage_count: ReplyTemplate.usage_count + 1},
            synchronize_session=False
        )
    
    from app.services.activity_log_service import ActivityLogService
    try:
        ActivityLogService.log(
            db,
            organization_id=current_user.organization_id,
            location_id=review.location_id,
            actor_user_id=current_user.id,
            entity_type="review",
            entity_id=review.id,
            action="review_replied",
            payload={"rating": review.rating}
        )
    except Exception as log_exc:
        logger.error("ActivityLogService.log failed for review %s: %s", review.id, log_exc, exc_info=True)
    
    db.commit()
    db.refresh(review)
    
    return review

@router.post("/{review_id}/generate-reply", response_model=GenerateReplyResponse)
async def generate_review_reply(
    review_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    if current_user.role == Role.VIEWER:
        raise HTTPException(status_code=403, detail="Viewers cannot generate replies")

    review = db.query(Review).filter(
        Review.id == review_id,
        Review.is_deleted == False
    ).first()
    
    if not review or review.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Review not found")

    allowed_location_ids = get_user_location_ids(current_user, db)
    if allowed_location_ids is not None and review.location_id not in allowed_location_ids:
        raise HTTPException(status_code=403, detail="You do not have access to this location")
        
    location = db.query(Location).filter(
        Location.id == review.location_id,
        Location.organization_id == current_user.organization_id
    ).first()
    
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    assert_location_active(db, location.id)

    try:
        with CreditService.consume_ai_credit(db, current_user.organization_id, "generate_review_reply"):
            result = await generate_reply(review, location)
    except LLMProviderError as e:
        logger.error("LLM generation failed for review %s: %s", review_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service temporarily unavailable. Please write a manual reply."
        )
    except Exception as e:
        logger.error("Unexpected error during AI reply generation for review %s: %s", review_id, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI service temporarily unavailable. Please write a manual reply."
        )
        
    return GenerateReplyResponse(
        review_id=review.id,
        generated_reply=result["generated_reply"],
        tone=result["tone"]
    )


@router.post("/locations/{location_id}/retag-sentiment", status_code=status.HTTP_200_OK)
def retag_sentiment(
    location_id: int = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """
    Reset sentiment_tagged_at for all non-deleted reviews of a location to NULL,
    then enqueue the sentiment tagging task.
    """
    # Location scope is enforced by the require_location_access dependency.
    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id
    ).first()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # Reset all non-deleted reviews so they get re-tagged
    db.query(Review).filter(
        Review.location_id == location_id,
        Review.organization_id == current_user.organization_id,
        Review.is_deleted == False
    ).update({Review.sentiment_tagged_at: None}, synchronize_session=False)
    db.commit()

    celery_app.send_task(
        "app.tasks.tag_reviews_sentiment_task",
        kwargs={
            "location_id": location_id,
            "organization_id": current_user.organization_id
        }
    )

    return {"status": "queued", "message": "Sentiment retagging queued for this location"}
