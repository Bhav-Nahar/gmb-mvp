import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user, staff_required, require_location_access
from app.core.authorization import assert_location_access, assert_location_active
from app.models.user import User
from app.models.location import Location
from app.models.location_media import LocationMedia, LocationMediaStatus
from app.models.post_media import PostMedia
from app.schemas.location_media import LocationMediaCreate, LocationMediaResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["location-media"])

# Google Business Profile photo requirements (stricter than our generic upload
# validation, which allows 250px / 10MB for post media). Validated here so users
# get a clear up-front error instead of a silent Google-side rejection.
GBP_PHOTO_MIN_EDGE_PX = 720
GBP_PHOTO_MAX_BYTES = 5 * 1024 * 1024  # 5 MB

# A publish that's been in PUBLISHING longer than this is considered stuck
# (worker crashed / never ran) and is recovered to Failed on next list.
PUBLISH_STALE_MINUTES = 10


@router.post(
    "/locations/{location_id}/media",
    response_model=LocationMediaResponse,
    status_code=status.HTTP_201_CREATED,
)
def publish_location_media(
    payload: LocationMediaCreate,
    location_id: int = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    """Publish an already-uploaded asset to a location's Google profile gallery.

    The file must first be uploaded via POST /media/upload (which stores it and
    returns a PostMedia id + cdn_url); we reference that asset here and send its
    public URL to Google as the photo `sourceUrl`.
    """
    assert_location_active(db, location_id)

    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id,
    ).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found.")

    # Google only accepts media for verified locations.
    if location.is_verified is False:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This location is not verified on Google, so photos cannot be published yet.",
        )

    source = db.query(PostMedia).filter(
        PostMedia.id == payload.source_media_id,
        PostMedia.organization_id == current_user.organization_id,
        PostMedia.is_deleted == False,
    ).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source media not found or access denied.")
    if not source.cdn_url:
        raise HTTPException(status_code=400, detail="Source media has no public URL to publish.")

    # GBP photo spec validation (clear error now vs. silent Google rejection later).
    if source.file_size and source.file_size > GBP_PHOTO_MAX_BYTES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Image is too large for Google ({source.file_size // (1024*1024)}MB). Max is 5MB.",
        )
    short_edge = min(source.width or 0, source.height or 0)
    if short_edge and short_edge < GBP_PHOTO_MIN_EDGE_PX:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Image is too small for Google ({source.width}×{source.height}). Minimum is {GBP_PHOTO_MIN_EDGE_PX}px on the shortest side.",
        )

    media = LocationMedia(
        organization_id=current_user.organization_id,
        location_id=location_id,
        source_media_id=source.id,
        gbp_category=payload.category,
        source_url=source.cdn_url,
        publish_status=LocationMediaStatus.PUBLISHING,
    )
    db.add(media)
    db.commit()
    db.refresh(media)

    from app.worker import celery as celery_app
    try:
        celery_app.send_task(
            "app.tasks.publish_location_media_task",
            args=[media.id, current_user.organization_id],
        )
    except Exception as dispatch_err:
        media.publish_status = LocationMediaStatus.PENDING
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Task dispatch failed: {str(dispatch_err)}",
        )

    return media


@router.get(
    "/locations/{location_id}/media",
    response_model=list[LocationMediaResponse],
)
def list_location_media(
    location_id: int = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the gallery photos tracked for a location (newest first).

    Opportunistically kicks off a reconcile with Google's real gallery
    (debounced to once/60s per location) so photos uploaded outside our app
    appear shortly after opening the tab.
    """
    # Stuck-Publishing recovery: a row left in PUBLISHING past the threshold means
    # the worker crashed or never ran — surface it as Failed instead of forever-spinning.
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=PUBLISH_STALE_MINUTES)
    stale = db.query(LocationMedia).filter(
        LocationMedia.location_id == location_id,
        LocationMedia.organization_id == current_user.organization_id,
        LocationMedia.publish_status == LocationMediaStatus.PUBLISHING,
        LocationMedia.updated_at < stale_cutoff,
    ).all()
    if stale:
        for m in stale:
            m.publish_status = LocationMediaStatus.FAILED
            m.failure_reason = "Publishing timed out — the worker may have crashed. Please try again."
            m.google_error_code = "STALE_RECOVERY"
        db.commit()

    try:
        from app.api.posts import get_redis
        r = get_redis()
        debounce_key = f"media_sync_debounce:{location_id}"
        if r.set(debounce_key, "1", nx=True, ex=60):
            from app.worker import celery as celery_app
            celery_app.send_task("app.tasks.sync_location_media_task", args=[location_id])
    except Exception as e:
        logger.warning(f"Lazy media sync dispatch failed for {location_id}: {e}")

    return (
        db.query(LocationMedia)
        .filter(
            LocationMedia.location_id == location_id,
            LocationMedia.organization_id == current_user.organization_id,
            LocationMedia.is_deleted == False,
        )
        .order_by(LocationMedia.created_at.desc())
        .all()
    )


@router.delete(
    "/locations/media/{media_id}",
    status_code=status.HTTP_202_ACCEPTED,
)
def delete_location_media(
    media_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    """Remove a gallery photo from Google and soft-delete the local record."""
    media = db.query(LocationMedia).filter(
        LocationMedia.id == media_id,
        LocationMedia.organization_id == current_user.organization_id,
        LocationMedia.is_deleted == False,
    ).first()
    if not media:
        raise HTTPException(status_code=404, detail="Media not found or access denied.")

    # Resource-indirect path (no location_id in URL) — enforce scope explicitly.
    assert_location_access(db, current_user, media.location_id)

    # If it was never published to Google, just soft-delete locally.
    if not media.media_key and not media.gbp_resource_name:
        media.is_deleted = True
        media.deleted_at = datetime.now(timezone.utc)
        db.commit()
        return {"status": "deleted"}

    from app.worker import celery as celery_app
    try:
        celery_app.send_task(
            "app.tasks.delete_location_media_task",
            args=[media.id, current_user.organization_id],
        )
    except Exception as dispatch_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Task dispatch failed: {str(dispatch_err)}",
        )
    return {"status": "deleting"}
