from typing import List, Dict, Any, TypeVar, Type, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from fastapi import HTTPException, status
from app.models.campaign import Campaign
from app.models.post import Post
from app.models.post_variant import PostVariant
from app.models.post_media import PostMedia
from app.models.publish_job import PublishJob
from app.models.post_audit_log import PostAuditLog
from app.models.location import Location
from app.schemas.posts import (
    PostCreateRequest,
    PostUpdateRequest,
    CampaignCreateRequest,
    PostMediaCreateRequest
)
from app.constants.posts import PostStatus, PublishJobStatus, CampaignStatus
import datetime

T = TypeVar("T")

class PostService:
    @staticmethod
    def _verify_ownership(db: Session, model: Type[T], resource_id: int, organization_id: int) -> T:
        """Helper to ensure a resource exists and belongs to the given organization."""
        resource = db.query(model).filter(
            model.id == resource_id,
            model.organization_id == organization_id
        ).first()
        if not resource:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{model.__name__} not found or access denied."
            )
        return resource

    @staticmethod
    def create_draft_post(db: Session, post_data: PostCreateRequest, organization_id: int, user_id: int) -> Post:
        campaign = None
        if post_data.campaign_id:
            campaign = PostService._verify_ownership(db, Campaign, post_data.campaign_id, organization_id)
            
        post = Post(
            organization_id=organization_id,
            campaign_id=post_data.campaign_id,
            created_by_user_id=user_id,
            title=post_data.title,
            summary=post_data.summary,
            language_code=post_data.language_code,
            post_type=post_data.post_type.value,
            status=PostStatus.DRAFT.value,
            cta_type=post_data.cta_type.value if post_data.cta_type else None,
            cta_url=str(post_data.cta_url) if post_data.cta_url else None,
            is_bulk_post=post_data.is_bulk_post,
            scheduled_at=post_data.scheduled_at
        )
        db.add(post)
        db.flush()
        
        # Link explicit primary_post_id on campaign
        if campaign and not campaign.primary_post_id:
            campaign.primary_post_id = post.id
            db.add(campaign)
        
        audit_log = PostAuditLog(
            organization_id=organization_id,
            post_id=post.id,
            actor_user_id=user_id,
            action="CREATED",
            new_status=PostStatus.DRAFT.value,
            log_metadata={"action": "draft_created"}
        )
        db.add(audit_log)
        db.commit()
        db.refresh(post)
        return post

    _ALLOWED_PATCH_TRANSITIONS: Dict[str, List[str]] = {
        "Draft":           ["PendingApproval", "Scheduled", "Draft"],
        "PendingApproval": ["Approved", "Scheduled", "Draft"],
        "Approved":        ["Scheduled", "Draft"],  # allow revert only; Publishing is set by publish endpoint
        "Scheduled":       ["Approved", "Draft"],
    }

    @staticmethod
    def update_post(db: Session, post_id: int, update_data: PostUpdateRequest, organization_id: int, user_id: int) -> Post:
        post = PostService._verify_ownership(db, Post, post_id, organization_id)

        # DB stores raw strings; normalize to str so enum objects and plain
        # strings compare identically regardless of Pydantic serialization mode.
        old_status: str = post.status if isinstance(post.status, str) else str(post.status)
        update_dict = update_data.model_dump(exclude_unset=True)

        # Normalize the incoming status to its string value before any comparison.
        if "status" in update_dict:
            raw = update_dict["status"]
            new_status: str = raw.value if hasattr(raw, "value") else str(raw)
            update_dict["status"] = new_status  # ensure we always write a plain string

            allowed = PostService._ALLOWED_PATCH_TRANSITIONS.get(old_status, [])
            if new_status not in allowed:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Invalid status transition '{old_status}' \u2192 '{new_status}' via PATCH. "
                        f"Allowed: {allowed or 'none (terminal state)'}."
                    )
                )

        for key, value in update_dict.items():
            setattr(post, key, value)

        if "status" in update_dict and old_status != update_dict["status"]:
            audit_log = PostAuditLog(
                organization_id=organization_id,
                post_id=post.id,
                actor_user_id=user_id,
                action="STATUS_CHANGED",
                previous_status=old_status,
                new_status=update_dict["status"],
                log_metadata={"action": "status_update"}
            )
            db.add(audit_log)

        db.commit()
        db.refresh(post)
        return post

    @staticmethod
    def create_campaign(db: Session, campaign_data: CampaignCreateRequest, organization_id: int, user_id: int) -> Campaign:
        campaign = Campaign(
            organization_id=organization_id,
            created_by_user_id=user_id,
            name=campaign_data.name,
            description=campaign_data.description,
            total_locations=campaign_data.total_locations,
            status=CampaignStatus.DRAFT.value
        )
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        return campaign

    @staticmethod
    def attach_media(db: Session, post_id: int, media_data: PostMediaCreateRequest, organization_id: int) -> PostMedia:
        post = PostService._verify_ownership(db, Post, post_id, organization_id)
        
        # Safe storage key resolution (Bug 1 Fix)
        storage_key = media_data.storage_key
        if not storage_key:
            ext = "jpg"
            if media_data.mime_type:
                parts = media_data.mime_type.split("/")
                if len(parts) > 1:
                    ext = parts[1]
                    if ext == "jpeg":
                        ext = "jpg"
            storage_key = f"uploads/org_{organization_id}/media/{media_data.sha256_hash}.{ext}"

        media = PostMedia(
            organization_id=organization_id,
            post_id=post.id,
            storage_provider=media_data.storage_provider,
            storage_key=storage_key,
            media_type=media_data.media_type.value,
            original_filename=media_data.original_filename,
            mime_type=media_data.mime_type,
            file_size=media_data.file_size,
            width=media_data.width,
            height=media_data.height,
            sha256_hash=media_data.sha256_hash,
            cdn_url=str(media_data.cdn_url),
            upload_status="Uploaded",
            validation_status="Valid",
            is_deleted=False
        )
        db.add(media)
        db.commit()
        db.refresh(media)
        return media

    @staticmethod
    def create_post_variant(db: Session, post_id: int, location_id: int, variables: dict, organization_id: int) -> PostVariant:
        PostService._verify_ownership(db, Post, post_id, organization_id)
        PostService._verify_ownership(db, Location, location_id, organization_id)
        
        # Rendering logic would ideally happen here using variables
        # For Phase 1, we just store the variant record
        variant = PostVariant(
            organization_id=organization_id,
            post_id=post_id,
            location_id=location_id,
            rendered_summary="[Placeholder Rendered Summary]", 
            rendered_cta_url=None,
            rendering_variables=variables
        )
        db.add(variant)
        db.commit()
        db.refresh(variant)
        return variant

    @staticmethod
    def _validate_publish_eligibility(
        db: Session,
        post: Post,
        location_id: int,
        organization_id: int,
    ) -> None:
        """
        Pure-read pre-flight check for a single location.
        Raises HTTPException if the location is invalid, access is denied,
        or a blocking publish job already exists.
        This must be called BEFORE any DB writes so the caller can do an
        all-or-nothing pre-flight pass across all locations.
        """
        # Location ownership
        location = db.query(Location).filter(
            Location.id == location_id,
            Location.organization_id == organization_id
        ).first()
        if not location:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Location {location_id} not found or access denied."
            )

        # Idempotency: detect blocking existing jobs
        existing_job = db.query(PublishJob).filter(
            PublishJob.post_id == post.id,
            PublishJob.location_id == location_id
        ).first()

        if existing_job:
            job_status_upper = existing_job.status.upper()
            if job_status_upper in ["PENDING", "RUNNING", "RETRYING"]:
                # Non-blocking: an in-flight job means we'll skip this location
                # (handled by the write phase). Mark as sentinel so caller can skip.
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Location {location_id} already has an in-flight publish job (status={existing_job.status})."
                )
            elif job_status_upper == "SUCCESS":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Location {location_id} was already published successfully."
                )
            elif job_status_upper == "FAILED":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Location {location_id} has a failed publish job. Manual retry required."
                )

    @staticmethod
    def _stage_publish_job(
        db: Session,
        post: "Post",
        location_id: int,
        organization_id: int,
        user_id: int,
    ) -> PublishJob:
        """
        Flush-only: stages one PublishJob + audit log into the current transaction
        WITHOUT committing. The caller is responsible for the single final commit
        that covers all locations atomically.
        """
        post.status = "PUBLISHING"

        idempotency_key = f"post_{post.id}_loc_{location_id}_rev_1"
        job = PublishJob(
            organization_id=organization_id,
            campaign_id=post.campaign_id,
            post_id=post.id,
            location_id=location_id,
            status="PENDING",
            idempotency_key=idempotency_key,
        )
        db.add(job)
        db.flush()  # populate job.id without committing

        audit_log = PostAuditLog(
            organization_id=organization_id,
            post_id=post.id,
            actor_user_id=user_id,
            action="PUBLISHING",
            previous_status="APPROVED",
            new_status="PUBLISHING",
            log_metadata={"action": "published_to_location", "location_id": location_id},
        )
        db.add(audit_log)
        return job


post_service = PostService()
