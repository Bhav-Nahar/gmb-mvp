import math
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.api.deps import get_current_user, staff_required
from app.models.user import User
from app.models.location import Location
from app.models.review import Review
from app.schemas.review import ReviewResponse, ReviewListResponse, ReviewReplyRequest
from app.providers.factory import ProviderFactory
from app.worker import celery

router = APIRouter()

@router.get("/", response_model=ReviewListResponse)
def get_reviews(
    location_id: Optional[int] = None,
    is_replied: Optional[bool] = None,
    rating: Optional[int] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    query = db.query(Review).filter(
        Review.organization_id == current_user.organization_id,
        Review.is_deleted == False
    )

    if location_id:
        query = query.filter(Review.location_id == location_id)
    if is_replied is not None:
        query = query.filter(Review.is_replied == is_replied)
    if rating:
        query = query.filter(Review.rating == rating)

    total = query.count()
    pages = math.ceil(total / size) if total > 0 else 1

    reviews = query.order_by(Review.review_created_at.desc()).offset((page - 1) * size).limit(size).all()

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
    if location_id:
        loc = db.query(Location).filter(
            Location.id == location_id,
            Location.organization_id == current_user.organization_id
        ).first()
        if not loc:
            raise HTTPException(status_code=404, detail="Location not found")
            
        task = celery.send_task("app.tasks.sync_reviews_task", args=[location_id, "Manual"])
        return {"message": "Sync task has been queued for the location.", "task_id": task.id}
    else:
        locations = db.query(Location).filter(
            Location.organization_id == current_user.organization_id
        ).all()
        task_ids = []
        for loc in locations:
            task = celery.send_task("app.tasks.sync_reviews_task", args=[loc.id, "Manual"])
            task_ids.append(task.id)
        return {"message": f"Sync tasks have been queued for {len(locations)} locations.", "task_ids": task_ids}

@router.post("/{id}/reply", response_model=ReviewResponse)
async def reply_to_review(
    id: int,
    payload: ReviewReplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    review = db.query(Review).filter(
        Review.id == id,
        Review.organization_id == current_user.organization_id,
        Review.is_deleted == False
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
        
    provider = ProviderFactory.get_provider(review.provider, current_user.organization_id, db)
    
    try:
        await provider.reply_review(review.provider_review_id, payload.reply_text)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to post reply to provider: {str(e)}")
        
    review.is_replied = True
    review.reply_text = payload.reply_text
    review.review_updated_at = datetime.utcnow()
    db.commit()
    db.refresh(review)
    
    return review
