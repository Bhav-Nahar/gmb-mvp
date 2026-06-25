import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sqlalchemy.orm import Session
from app.models.organization import Organization
from app.models.location import Location
from app.models.microsite import Microsite
from app.services.revalidation_service import trigger_bulk_microsite_revalidation

@pytest.fixture
def mock_redis():
    mock_r = MagicMock()
    mock_lock = MagicMock()
    # By default, lock acquire succeeds
    mock_lock.acquire.return_value = True
    mock_r.lock.return_value = mock_lock
    return mock_r, mock_lock

@pytest.mark.asyncio
@patch("app.services.revalidation_service.SessionLocal")
@patch("app.services.revalidation_service._get_redis")
@patch("app.services.revalidation_service.trigger_microsite_revalidation", new_callable=AsyncMock)
def test_trigger_bulk_revalidation_published_only(
    mock_trigger, mock_get_redis, mock_session_local, db, mock_redis
):
    # Setup mock redis and database session
    redis_instance, lock_instance = mock_redis
    mock_get_redis.return_value = redis_instance
    mock_session_local.return_value = db

    # Create dummy organization
    org = Organization(name="Audit Org")
    db.add(org)
    db.commit()

    # Create dummy locations
    loc1 = Location(organization_id=org.id, google_location_id="audit-1", location_name="Audit Loc 1")
    loc2 = Location(organization_id=org.id, google_location_id="audit-2", location_name="Audit Loc 2")
    db.add(loc1)
    db.add(loc2)
    db.commit()

    # Create one published microsite and one draft microsite
    ms1 = Microsite(
        organization_id=org.id,
        location_id=loc1.id,
        org_slug="audit-org",
        location_slug="audit-loc-1",
        status="published"
    )
    ms2 = Microsite(
        organization_id=org.id,
        location_id=loc2.id,
        org_slug="audit-org",
        location_slug="audit-loc-2",
        status="draft"
    )
    db.add(ms1)
    db.add(ms2)
    db.commit()

    # Trigger bulk revalidation for both locations
    trigger_bulk_microsite_revalidation([loc1.id, loc2.id])

    # Should only call trigger_microsite_revalidation for the published one (ms1)
    mock_trigger.assert_called_once_with("audit-loc-1")
    redis_instance.lock.assert_called_once_with(f"lock:revalidate_microsite:{loc1.id}", timeout=60)
    lock_instance.acquire.assert_called_once()


@pytest.mark.asyncio
@patch("app.services.revalidation_service.SessionLocal")
@patch("app.services.revalidation_service._get_redis")
@patch("app.services.revalidation_service.trigger_microsite_revalidation", new_callable=AsyncMock)
def test_trigger_bulk_revalidation_debounce(
    mock_trigger, mock_get_redis, mock_session_local, db, mock_redis
):
    # Setup mock redis: lock acquire returns False (already locked)
    redis_instance, lock_instance = mock_redis
    lock_instance.acquire.return_value = False
    mock_get_redis.return_value = redis_instance
    mock_session_local.return_value = db

    org = Organization(name="Audit Org 2")
    db.add(org)
    db.commit()

    loc = Location(organization_id=org.id, google_location_id="audit-3", location_name="Audit Loc 3")
    db.add(loc)
    db.commit()

    ms = Microsite(
        organization_id=org.id,
        location_id=loc.id,
        org_slug="audit-org-2",
        location_slug="audit-loc-3",
        status="published"
    )
    db.add(ms)
    db.commit()

    trigger_bulk_microsite_revalidation([loc.id])

    # Should NOT call trigger_microsite_revalidation since it's debounced (lock acquire fails)
    mock_trigger.assert_not_called()
