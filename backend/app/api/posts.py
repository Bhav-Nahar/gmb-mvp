import logging
import math
from typing import Optional
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.db.session import get_db
from app.api.deps import staff_required
from app.models.user import User
from app.models.post import Post
from app.models.campaign import Campaign
from app.models.publish_job import PublishJob
from app.constants.posts import PostStatus, CampaignStatus

from app.schemas.posts import (
    PostCreateRequest,
    PostResponse,
    CampaignCreateRequest,
    CampaignResponse,
    PostListResponse,
    PostUpdateRequest,
    PostMediaCreateRequest,
    PostMediaResponse,
    CampaignLaunchRequest,
    BatchPublishJobCreateResponse,
    CampaignListResponse,
    CampaignProgressResponse,
    CampaignDetailResponse
)
from app.services.post_service import post_service
from app.core.config import settings
import redis as _redis_lib

_redis_pool = None

def get_redis() -> _redis_lib.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = _redis_lib.ConnectionPool.from_url(
            settings.REDIS_URL, 
            max_connections=20,
            socket_timeout=5,
            socket_connect_timeout=5
        )
    return _redis_lib.Redis(connection_pool=_redis_pool)

router = APIRouter()

@router.post("/draft", response_model=PostResponse, status_code=status.HTTP_201_CREATED)
def create_draft_post(
    payload: PostCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Creates a new draft post."""
    post = post_service.create_draft_post(
        db=db,
        post_data=payload,
        organization_id=current_user.organization_id,
        user_id=current_user.id
    )
    return post

@router.get("", response_model=PostListResponse)
def list_posts(
    post_status: Optional[PostStatus] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch paginated list of posts for the organization."""
    query = db.query(Post).filter(Post.organization_id == current_user.organization_id)
    
    if post_status:
        query = query.filter(Post.status == post_status.value)
        
    total = query.count()
    pages = math.ceil(total / size) if total > 0 else 1
    posts = query.order_by(Post.created_at.desc()).offset((page - 1) * size).limit(size).all()
    
    return PostListResponse(
        posts=posts,
        total=total,
        page=page,
        pages=pages
    )

@router.get("/campaigns", response_model=CampaignListResponse)
def list_campaigns(
    location_id: Optional[int] = None,
    campaign_status: Optional[CampaignStatus] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch paginated list of campaigns for the organization."""
    query = db.query(Campaign).filter(Campaign.organization_id == current_user.organization_id)
    
    if location_id:
        from app.models.publish_job import PublishJob
        query = query.join(PublishJob).filter(PublishJob.location_id == location_id)
        query = query.distinct()
        
    if campaign_status:
        query = query.filter(Campaign.status == campaign_status.value)
        
    total = query.count()
    pages = math.ceil(total / size) if total > 0 else 1
    campaigns = query.order_by(Campaign.created_at.desc()).offset((page - 1) * size).limit(size).all()
    
    return CampaignListResponse(
        campaigns=campaigns,
        total=total,
        page=page,
        pages=pages
    )

@router.post("/campaigns", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
def create_campaign(
    payload: CampaignCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Creates a new campaign for bulk posting."""
    return post_service.create_campaign(
        db=db,
        campaign_data=payload,
        organization_id=current_user.organization_id,
        user_id=current_user.id
    )

@router.get("/campaigns/{id}", response_model=CampaignResponse)
def get_campaign(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch a single campaign belonging to the organization."""
    return post_service._verify_ownership(db, Campaign, id, current_user.organization_id)

@router.post("/campaigns/{id}/launch", status_code=status.HTTP_202_ACCEPTED)
def launch_campaign(
    id: int,
    payload: CampaignLaunchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Launches a campaign by enqueuing the orchestrator task."""
    from app.core.authorization import validate_location_access
    validate_location_access(db, current_user, payload.location_ids)
    
    campaign = post_service._verify_ownership(db, Campaign, id, current_user.organization_id)
    
    if campaign.status.upper() not in ["DRAFT", "FAILED", "PAUSED", "COMPLETED"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Campaign is in {campaign.status} state and cannot be launched."
        )

    # Transition campaign to QUEUED
    from app.constants.posts import CampaignStatus
    old_status = campaign.status
    campaign.status = CampaignStatus.QUEUED.value
    campaign.total_locations = len(payload.location_ids)
    campaign.total_pending = len(payload.location_ids)
    # Reset counters on launch
    campaign.total_published = 0
    campaign.total_failed = 0
    campaign.total_rejected = 0
    campaign.total_shadow_banned = 0
    
    # Audit log
    from app.models.campaign_audit_log import CampaignAuditLog
    audit = CampaignAuditLog(
        organization_id=current_user.organization_id,
        campaign_id=campaign.id,
        actor_user_id=current_user.id,
        action="launch",
        previous_status=old_status,
        new_status=CampaignStatus.QUEUED.value,
        log_metadata={"location_count": len(payload.location_ids)}
    )
    db.add(audit)

    # Dispatch orchestrator task BEFORE committing so we can roll back if dispatch fails
    from app.worker import celery as celery_app
    try:
        celery_app.send_task(
            "app.tasks.orchestrate_campaign_task",
            args=(campaign.id, current_user.organization_id, payload.location_ids, current_user.id)
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to dispatch orchestrate_campaign_task: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Task dispatch failed: {str(e)}")

    db.commit()
    db.refresh(campaign)

    return {"message": "Campaign launch queued successfully."}
@router.get("/campaigns/{id}/progress", response_model=CampaignDetailResponse)
def get_campaign_progress(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch aggregate progress for a campaign including jobs and audit logs."""
    campaign = post_service._verify_ownership(db, Campaign, id, current_user.organization_id)
    
    from app.models.publish_job import PublishJob
    from app.models.campaign_audit_log import CampaignAuditLog
    
    from app.api.deps import get_user_location_ids
    allowed_locs = get_user_location_ids(current_user, db)
    
    query = db.query(PublishJob).filter(PublishJob.campaign_id == campaign.id)
    if allowed_locs is not None:
        query = query.filter(PublishJob.location_id.in_(allowed_locs))
        
    jobs = query.order_by(PublishJob.created_at.desc()).all()
    audit_logs = db.query(CampaignAuditLog).filter(CampaignAuditLog.campaign_id == campaign.id).order_by(CampaignAuditLog.created_at.desc()).all()
    
    # Safe response mapping (Finding 2 Fix)
    return CampaignDetailResponse(
        id=campaign.id,
        status=campaign.status,
        total_locations=campaign.total_locations,
        total_pending=campaign.total_pending,
        total_published=campaign.total_published,
        total_failed=campaign.total_failed,
        total_rejected=campaign.total_rejected,
        total_shadow_banned=campaign.total_shadow_banned,
        jobs=jobs,
        audit_logs=audit_logs
    )

@router.get("/{id}", response_model=PostResponse)
def get_post(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch a single post belonging to the organization."""
    return post_service._verify_ownership(db, Post, id, current_user.organization_id)

@router.patch("/{id}", response_model=PostResponse)
def update_post(
    id: int,
    payload: PostUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Updates a draft post or transitions its state."""
    return post_service.update_post(
        db=db,
        post_id=id,
        update_data=payload,
        organization_id=current_user.organization_id,
        user_id=current_user.id
    )

@router.post("/{id}/media", response_model=PostMediaResponse, status_code=status.HTTP_201_CREATED)
def attach_media_to_post(
    id: int,
    payload: PostMediaCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Registers media metadata for a specific post."""
    return post_service.attach_media(
        db=db,
        post_id=id,
        media_data=payload,
        organization_id=current_user.organization_id
    )

@router.post("/{id}/publish", response_model=BatchPublishJobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def launch_publish_jobs(
    id: int,
    payload: CampaignLaunchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """
    Launch a post across multiple locations asynchronously.
    Uses a two-phase approach:
      Phase 1 (pre-flight, read-only): validate every location before writing anything.
      Phase 2 (write): create jobs atomically, one per location.
    If any pre-flight check fails the entire request is rejected with no DB side-effects.
    """
    # Verify post ownership
    post = post_service._verify_ownership(db, Post, id, current_user.organization_id)

    from app.core.authorization import validate_location_access
    validate_location_access(db, current_user, payload.location_ids)

    # Post MUST be APPROVED
    if post.status.upper() != "APPROVED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Only APPROVED posts can be published. Current status: {post.status}"
        )

    # Note: Media is optional for GMB posts according to project standards and GMB API.
    # The mapper in gbp/post_mapper.py handles the conditional inclusion of media.

    # ── Phase 1: pre-flight (pure reads, zero DB writes) ──────────────────────
    # Fail fast with a clear error if ANY location is invalid or already
    # has a blocking job. This prevents partial commits.
    for loc_id in payload.location_ids:
        post_service._validate_publish_eligibility(
            db=db,
            post=post,
            location_id=loc_id,
            organization_id=current_user.organization_id
        )

    # ── Phase 2: write — single atomic transaction for all locations ──────────
    # _stage_publish_job flushes (populates job.id) but does NOT commit.
    # All locations land in the same transaction; one failure rolls back everything.
    staged_jobs: list[PublishJob] = []
    try:
        for loc_id in payload.location_ids:
            job = post_service._stage_publish_job(
                db=db,
                post=post,
                location_id=loc_id,
                organization_id=current_user.organization_id,
                user_id=current_user.id,
            )
            staged_jobs.append(job)

        # Single commit — all-or-nothing for every location in this batch.
        db.commit()
    except Exception:
        db.rollback()
        raise

    # Refresh ORM objects and dispatch Celery tasks AFTER the transaction is closed
    # so workers can read committed rows immediately.
    from app.worker import celery as celery_app
    successful_jobs: list[PublishJob] = []
    for job in staged_jobs:
        db.refresh(job)
        celery_app.send_task(
            "app.tasks.process_publish_job_task",
            args=(job.id, current_user.organization_id)
        )
        successful_jobs.append(job)

    return BatchPublishJobCreateResponse(
        successful_jobs=successful_jobs
    )

@router.get("/{id}/jobs")
def get_post_publish_jobs(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Fetch all publish jobs and audit logs associated with a post."""
    post = post_service._verify_ownership(db, Post, id, current_user.organization_id)

    from app.models.publish_job import PublishJob
    from app.models.post_audit_log import PostAuditLog
    from app.models.location import Location

    from app.api.deps import get_user_location_ids
    allowed_locs = get_user_location_ids(current_user, db)
    
    from sqlalchemy.orm import joinedload as _joinedload
    query = db.query(PublishJob).options(_joinedload(PublishJob.location)).filter(PublishJob.post_id == post.id)
    if allowed_locs is not None:
        query = query.filter(PublishJob.location_id.in_(allowed_locs))
    jobs = query.all()
    audits = (
        db.query(PostAuditLog)
        .filter(PostAuditLog.post_id == post.id)
        .order_by(PostAuditLog.created_at.desc())
        .all()
    )

    # Batch-load all locations in a single query (eliminates N+1)
    location_ids = {job.location_id for job in jobs}
    location_map: dict[int, Location] = {}
    if location_ids:
        rows = db.query(Location).filter(Location.id.in_(location_ids)).all()
        location_map = {loc.id: loc for loc in rows}

    mapped_jobs = [
        {
            "id": job.id,
            "organization_id": job.organization_id,
            "campaign_id": job.campaign_id,
            "post_id": job.post_id,
            "location_id": job.location_id,
            "location_name": (
                location_map[job.location_id].location_name
                if job.location_id in location_map
                else f"Location #{job.location_id}"
            ),
            "provider": job.provider,
            "status": job.status,
            "retry_count": job.retry_count,
            "last_error": job.last_error,
            "google_post_id": job.google_post_id,
            "provider_response": job.provider_response,
            "idempotency_key": job.idempotency_key,
            "published_at": job.published_at.isoformat() if job.published_at else None,
            "created_at": job.created_at.isoformat(),
            "updated_at": job.updated_at.isoformat(),
        }
        for job in jobs
    ]

    return {
        "jobs": mapped_jobs,
        "audit_logs": [
            {
                "id": log.id,
                "action": log.action,
                "previous_status": log.previous_status,
                "new_status": log.new_status,
                "log_metadata": log.log_metadata,
                "created_at": log.created_at.isoformat(),
            }
            for log in audits
        ],
    }


@router.post("/campaigns/{id}/pause", response_model=CampaignResponse)
def pause_campaign(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Pauses a running or queued campaign."""
    campaign = post_service._verify_ownership(db, Campaign, id, current_user.organization_id)
    
    if campaign.status.upper() not in ["QUEUED", "PROCESSING"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Campaign is in {campaign.status} state and cannot be paused."
        )
        
    from app.constants.posts import CampaignStatus
    from app.models.campaign_audit_log import CampaignAuditLog

    old_status = campaign.status
    campaign.status = CampaignStatus.PAUSED.value

    # Update Redis flag instantly so active worker loops check and abort/drain gracefully
    r = get_redis()
    r.set(f"campaign:{campaign.id}:status", "Paused")
    
    audit = CampaignAuditLog(
        organization_id=current_user.organization_id,
        campaign_id=campaign.id,
        actor_user_id=current_user.id,
        action="pause",
        previous_status=old_status,
        new_status=CampaignStatus.PAUSED.value,
        log_metadata={}
    )
    db.add(audit)
    db.commit()
    db.refresh(campaign)
    
    return campaign


@router.post("/campaigns/{id}/resume", response_model=CampaignResponse)
def resume_campaign(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Resumes a paused campaign by re-sharding and re-enqueueing the paused publish jobs."""
    campaign = post_service._verify_ownership(db, Campaign, id, current_user.organization_id)
    
    if campaign.status.upper() != "PAUSED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Campaign is in {campaign.status} state and cannot be resumed."
        )
        
    from app.constants.posts import CampaignStatus, PublishJobStatus
    from app.models.campaign_audit_log import CampaignAuditLog
    from app.models.publish_job import PublishJob

    old_status = campaign.status
    campaign.status = CampaignStatus.PROCESSING.value

    # Set Redis flag instantly
    r = get_redis()
    r.set(f"campaign:{campaign.id}:status", "Processing")

    # Fetch paused/pending jobs for the campaign
    paused_jobs = db.query(PublishJob).filter(
        PublishJob.campaign_id == campaign.id,
        PublishJob.status.in_([PublishJobStatus.PAUSED.value, PublishJobStatus.PENDING.value])
    ).all()
    
    # Update all to PENDING in the DB
    for job in paused_jobs:
        job.status = PublishJobStatus.PENDING.value
    
    # Log Audit
    audit = CampaignAuditLog(
        organization_id=current_user.organization_id,
        campaign_id=campaign.id,
        actor_user_id=current_user.id,
        action="resume",
        previous_status=old_status,
        new_status=CampaignStatus.PROCESSING.value,
        log_metadata={"job_count": len(paused_jobs)}
    )
    db.add(audit)
    db.commit()
    db.refresh(campaign)
    
    # Re-shard the paused jobs in chunks of 50
    if paused_jobs:
        job_ids = [j.id for j in paused_jobs]
        chunk_size = 50
        shards = [job_ids[i:i + chunk_size] for i in range(0, len(job_ids), chunk_size)]
        
        # Initialize campaign Redis keys
        r.set(f"campaign:{campaign.id}:pending_shards", len(shards))
        
        # Dispatch Celery tasks
        from app.worker import celery as celery_app
        for shard in shards:
            celery_app.send_task(
                "app.tasks.process_campaign_shard_task",
                args=(shard, current_user.organization_id, campaign.id)
            )
            
    return campaign


@router.post("/campaigns/{id}/cancel", response_model=CampaignResponse)
def cancel_campaign(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """Cancels a running, queued, or paused campaign."""
    campaign = post_service._verify_ownership(db, Campaign, id, current_user.organization_id)
    
    if campaign.status.upper() not in ["QUEUED", "PROCESSING", "PAUSED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Campaign is in {campaign.status} state and cannot be cancelled."
        )
        
    from app.constants.posts import CampaignStatus, PublishJobStatus
    from app.models.campaign_audit_log import CampaignAuditLog
    from app.models.publish_job import PublishJob

    old_status = campaign.status
    campaign.status = CampaignStatus.CANCELLED.value

    # Set Redis flag instantly
    r = get_redis()
    r.set(f"campaign:{campaign.id}:status", "Cancelled")
    
    # Fetch pending/paused/running jobs for the campaign
    pending_jobs = db.query(PublishJob).filter(
        PublishJob.campaign_id == campaign.id,
        PublishJob.status.in_([
            PublishJobStatus.PENDING.value,
            PublishJobStatus.PAUSED.value,
            PublishJobStatus.RUNNING.value
        ])
    ).all()
    
    # Transition them to CANCELLED in DB
    for job in pending_jobs:
        job.status = PublishJobStatus.CANCELLED.value
        
    audit = CampaignAuditLog(
        organization_id=current_user.organization_id,
        campaign_id=campaign.id,
        actor_user_id=current_user.id,
        action="cancel",
        previous_status=old_status,
        new_status=CampaignStatus.CANCELLED.value,
        log_metadata={"cancelled_jobs_count": len(pending_jobs)}
    )
    db.add(audit)
    db.commit()
    db.refresh(campaign)
    
    return campaign


@router.post("/campaigns/{id}/retry-failed", response_model=CampaignResponse)
def retry_failed_campaign_jobs(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """
    Retries all failed publish jobs in a campaign with full RBAC, duplicate retry prevention, 
    and campaign status checks.
    """
    from app.core.authorization import validate_location_access
    from app.constants.posts import CampaignStatus, PublishJobStatus
    from app.models.campaign_audit_log import CampaignAuditLog
    from sqlalchemy import func

    campaign = post_service._verify_ownership(db, Campaign, id, current_user.organization_id)

    # 1. Campaign state check: campaign not PAUSED or CANCELLED
    if campaign.status.upper() in ["PAUSED", "CANCELLED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Campaign is in {campaign.status} state and cannot be retried. Resume or launch a new campaign instead."
        )

    # Fetch failed jobs
    failed_jobs = db.query(PublishJob).filter(
        PublishJob.campaign_id == campaign.id,
        PublishJob.status == PublishJobStatus.FAILED.value
    ).all()

    if not failed_jobs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No failed jobs found to retry"
        )

    # 2. RBAC Location Access check for all failed jobs
    location_ids = [job.location_id for job in failed_jobs]
    validate_location_access(db, current_user, location_ids)

    # 3. Prevent duplicate active retries: ensure no job in this campaign is actively enqueued or running
    active_jobs = db.query(PublishJob).filter(
        PublishJob.campaign_id == campaign.id,
        PublishJob.status.in_([PublishJobStatus.PENDING.value, PublishJobStatus.RUNNING.value, PublishJobStatus.RETRYING.value])
    ).count()
    if active_jobs > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot retry failed jobs while there are active jobs running in the campaign."
        )

    # Transition campaign and failed jobs
    old_status = campaign.status
    campaign.status = CampaignStatus.PROCESSING.value
    
    # Recalculate Postgres counters
    jobs_count = len(failed_jobs)
    campaign.total_failed = func.greatest(0, campaign.total_failed - jobs_count)
    campaign.total_pending = campaign.total_pending + jobs_count

    # Audit log
    audit = CampaignAuditLog(
        organization_id=current_user.organization_id,
        campaign_id=campaign.id,
        actor_user_id=current_user.id,
        action="retry_failed",
        previous_status=old_status,
        new_status=CampaignStatus.PROCESSING.value,
        log_metadata={"retrying_jobs_count": jobs_count}
    )
    db.add(audit)

    # Reset all failed jobs to PENDING
    job_ids = []
    for job in failed_jobs:
        job.status = PublishJobStatus.PENDING.value
        job.retry_count = 0
        job.last_error = None
        job.provider_response = None
        job_ids.append(job.id)

    db.commit()
    db.refresh(campaign)

    # 4. Enqueue to Celery in shards of 50
    if job_ids:
        chunk_size = 50
        shards = [job_ids[i:i + chunk_size] for i in range(0, len(job_ids), chunk_size)]
        
        r = get_redis()
        r.set(f"campaign:{campaign.id}:pending_shards", len(shards))
        r.set(f"campaign:{campaign.id}:success", campaign.total_published)
        r.set(f"campaign:{campaign.id}:failed", campaign.total_failed)
        r.set(f"campaign:{campaign.id}:total_locations", campaign.total_locations)
        r.set(f"campaign:{campaign.id}:status", "Processing")

        from app.worker import celery as celery_app
        for shard in shards:
            celery_app.send_task(
                "app.tasks.process_campaign_shard_task",
                args=(shard, current_user.organization_id, campaign.id)
            )

    return campaign


@router.post("/jobs/{job_id}/retry", response_model=CampaignResponse)
def retry_single_publish_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """
    Retries an individual failed publish job with full RBAC, duplicate retry prevention, 
    and campaign status checks.
    """
    from app.core.authorization import validate_location_access
    from app.constants.posts import CampaignStatus, PublishJobStatus
    from app.models.campaign_audit_log import CampaignAuditLog
    from sqlalchemy import func

    job = db.query(PublishJob).filter(
        PublishJob.id == job_id,
        PublishJob.organization_id == current_user.organization_id
    ).first()

    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Publish job not found or access denied."
        )

    # 1. Validate location access for the target location ID
    validate_location_access(db, current_user, [job.location_id])

    # Get campaign
    campaign = db.query(Campaign).filter(Campaign.id == job.campaign_id).first()
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign linked to job not found."
        )

    # 2. Campaign state check: campaign not PAUSED or CANCELLED
    if campaign.status.upper() in ["PAUSED", "CANCELLED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Campaign is in {campaign.status} state and cannot be retried. Resume the campaign first."
        )

    # 3. Reject if job.status is currently active
    if job.status.upper() in ["PENDING", "RUNNING", "RETRYING"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Job is already active in status: {job.status}."
        )

    old_job_status = job.status

    # Reset job
    job.status = PublishJobStatus.PENDING.value
    job.retry_count = 0
    job.last_error = None
    job.provider_response = None

    # Recalculate Postgres counters
    old_campaign_status = campaign.status
    campaign.status = CampaignStatus.PROCESSING.value
    
    if old_job_status.upper() == "FAILED":
        campaign.total_failed = func.greatest(0, campaign.total_failed - 1)
    campaign.total_pending = campaign.total_pending + 1

    audit = CampaignAuditLog(
        organization_id=current_user.organization_id,
        campaign_id=campaign.id,
        actor_user_id=current_user.id,
        action="retry_job",
        previous_status=old_campaign_status,
        new_status=CampaignStatus.PROCESSING.value,
        log_metadata={"retrying_job_id": job.id}
    )
    db.add(audit)
    db.commit()
    db.refresh(campaign)

    # 4. Enqueue to Celery as a single-element shard
    r = get_redis()
    r.incr(f"campaign:{campaign.id}:pending_shards")
    r.set(f"campaign:{campaign.id}:status", "Processing")

    from app.worker import celery as celery_app
    celery_app.send_task(
        "app.tasks.process_campaign_shard_task",
        args=([job.id], current_user.organization_id, campaign.id)
    )

    return campaign

