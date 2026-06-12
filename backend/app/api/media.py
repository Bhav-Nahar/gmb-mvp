import hashlib
import uuid
import logging
from fastapi import APIRouter, Depends, status, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.session import get_db
from app.api.deps import staff_required
from app.models.user import User
from app.models.post_media import PostMedia
from app.schemas.posts import PostMediaResponse
from app.services.media_validation_service import media_validation_service
from app.storage.factory import StorageProviderFactory

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/upload", response_model=PostMediaResponse, status_code=status.HTTP_201_CREATED)
async def upload_media(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """
    Uploads a new media asset for the organization.
    Validates GBP image requirements, checks for duplicate uploads in the same tenant,
    stores the file in the configured storage provider, and dispatches Celery optimization tasks.
    """
    # 0. Size Limit: Read only up to 10MB + 1 byte to detect overflow
    # This prevents OOM (Out of Memory) attacks from multi-GB uploads.
    MAX_SIZE = 10 * 1024 * 1024  # 10MB
    file_bytes = await file.read(MAX_SIZE + 1)
    if len(file_bytes) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum size is {MAX_SIZE // (1024 * 1024)}MB"
        )
    
    # 1. Deduplication: Compute SHA256 checksum
    sha256_hash = hashlib.sha256(file_bytes).hexdigest()
    
    # Strict tenant-boundary deduplication search
    existing_media = db.query(PostMedia).filter(
        PostMedia.organization_id == current_user.organization_id,
        PostMedia.sha256_hash == sha256_hash,
        PostMedia.is_deleted == False,
        PostMedia.upload_status == "Uploaded"
    ).first()
    
    if existing_media:
        logger.info(
            "Media upload deduplicated successfully",
            extra={
                "organization_id": current_user.organization_id,
                "media_id": existing_media.id,
                "storage_provider": existing_media.storage_provider,
                "upload_status": "Deduplicated"
            }
        )
        # Ensure optimization is triggered if missing (Bug Fix)
        if not existing_media.optimized_url:
            from app.worker import celery as celery_app
            try:
                celery_app.send_task("app.tasks.optimize_media_task", args=(existing_media.id, current_user.organization_id))
                celery_app.send_task("app.tasks.generate_thumbnail_task", args=(existing_media.id, current_user.organization_id))
            except Exception as e:
                logger.error(f"Failed to dispatch media tasks for deduplicated media: {str(e)}")
        
        return existing_media

    # 2. Validation Checks (filetype + Pillow)
    validation_res = media_validation_service.validate_image(file_bytes, file.filename)
    
    # 3. Storage Provider & Dynamic Key Resolution
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "jpg"
    if ext not in ["jpg", "jpeg", "png", "webp"]:
        ext = "jpg"
        
    storage_key = f"uploads/org_{current_user.organization_id}/media/{sha256_hash}.{ext}"
    storage_provider = StorageProviderFactory.get_provider()
    
    try:
        cdn_url = await storage_provider.upload_file(
            file_data=file_bytes,
            key=storage_key,
            mime_type=validation_res["mime_type"]
        )
    except Exception as e:
        logger.error(
            f"Failed to upload media to storage: {str(e)}",
            extra={
                "organization_id": current_user.organization_id,
                "storage_provider": storage_provider.provider_name
            }
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {str(e)}"
        )

    # 4. Save Database Record
    media = PostMedia(
        organization_id=current_user.organization_id,
        post_id=None,
        storage_provider=storage_provider.provider_name,
        storage_key=storage_key,
        media_type="PHOTO",
        original_filename=file.filename,
        mime_type=validation_res["mime_type"],
        file_size=validation_res["file_size"],
        width=validation_res["width"],
        height=validation_res["height"],
        sha256_hash=sha256_hash,
        cdn_url=cdn_url,
        upload_status="Uploaded",
        validation_status="Valid",
        is_deleted=False
    )
    db.add(media)
    db.commit()
    db.refresh(media)

    # Recalculate health score for affected locations if this media is linked to a post.
    if media.post_id:
        from app.models.post_variant import PostVariant
        from app.services.health_score_service import HealthScoreService
        variants = db.query(PostVariant).filter(PostVariant.post_id == media.post_id).all()
        for variant in variants:
            HealthScoreService.recalculate_health_score(db, variant.location_id, reason="media_upload")
        if variants:
            db.commit()


    # Structured Logging (No print statement!)
    logger.info(
        "Media uploaded and registered successfully",
        extra={
            "organization_id": current_user.organization_id,
            "media_id": media.id,
            "storage_provider": media.storage_provider,
            "upload_status": media.upload_status,
            "validation_status": media.validation_status
        }
    )

    # 5. Dispatch Celery Background Optimization Tasks
    from app.worker import celery as celery_app
    try:
        celery_app.send_task("app.tasks.optimize_media_task", args=(media.id, current_user.organization_id))
        celery_app.send_task("app.tasks.generate_thumbnail_task", args=(media.id, current_user.organization_id))
    except Exception as e:
        logger.error(f"Failed to dispatch media tasks: {str(e)}")
        # We don't raise here to avoid failing the upload, but optimization will be missing.
        # In a real app, we might want to retry or mark for later.
    
    return media

@router.get("/{id}", response_model=PostMediaResponse)
def get_media_details(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """
    Fetches the metadata details of a specific media asset, enforcing tenant isolation.
    """
    media = db.query(PostMedia).filter(
        PostMedia.id == id,
        PostMedia.organization_id == current_user.organization_id,
        PostMedia.is_deleted == False
    ).first()
    
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found or access denied."
        )
        
    return media

@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    """
    Soft-deletes a specific media asset. Permanently purges physical storage assets asynchronously.
    """
    media = db.query(PostMedia).filter(
        PostMedia.id == id,
        PostMedia.organization_id == current_user.organization_id,
        PostMedia.is_deleted == False
    ).first()
    
    if not media:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media not found or access denied."
        )
        
    # Soft deletion transition
    media.is_deleted = True
    media.deleted_at = datetime.utcnow()
    media.upload_status = "Deleted"
    db.commit()
    
    # Recalculate health score for affected locations
    if media.post_id:
        from app.models.post_variant import PostVariant
        from app.services.health_score_service import HealthScoreService
        variants = db.query(PostVariant).filter(PostVariant.post_id == media.post_id).all()
        for variant in variants:
            HealthScoreService.recalculate_health_score(db, variant.location_id, reason="media_delete")
        db.commit()


    logger.info(
        "Media soft-deleted successfully",
        extra={
            "organization_id": current_user.organization_id,
            "media_id": media.id,
            "storage_provider": media.storage_provider,
            "upload_status": media.upload_status
        }
    )
    
    # Permanent cleanup is delegated to background/periodic task.
    # We can trigger it instantly for self-cleaning:
    from app.worker import celery as celery_app
    celery_app.send_task("app.tasks.cleanup_deleted_media_task")
