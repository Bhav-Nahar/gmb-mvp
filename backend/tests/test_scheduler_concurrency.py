import datetime
import types

import pytest

from app.models.organization import Organization
from app.models.location import Location
from app.models.post import Post
from app.models.post_media import PostMedia
from app.models.campaign import Campaign
from app.models.publish_job import PublishJob
from app.constants.posts import PostStatus, CampaignStatus, PublishJobStatus


# ---------------------------------------------------------------------------
# Test doubles for the external systems the beat task touches (Redis + Celery).
# ---------------------------------------------------------------------------
class _FakeLock:
    def acquire(self, blocking=False):
        return True

    def release(self):
        return True


class _FakeRedis:
    """Minimal Redis stand-in: locks always acquire, get/set are no-ops."""
    def lock(self, *a, **k):
        return _FakeLock()

    def get(self, *a, **k):
        return None

    def set(self, *a, **k):
        return True

    def incr(self, *a, **k):
        return 1

    def decr(self, *a, **k):
        return 0


@pytest.fixture
def patched_externals(monkeypatch, db):
    """Patch Redis, Celery dispatch, ActivityLog and the session factory so the
    beat task runs entirely in-process against the test SQLite session."""
    import app.tasks as tasks
    import app.db.session as db_session

    dispatched = []
    monkeypatch.setattr(tasks, "_get_redis", lambda: _FakeRedis())

    fake_celery = types.SimpleNamespace(
        send_task=lambda name, args=None, **k: dispatched.append((name, args))
    )
    # check_scheduled_posts_task imports `from app.worker import celery as celery_app`
    import app.worker
    monkeypatch.setattr(app.worker, "celery", fake_celery)

    from app.services.activity_log_service import ActivityLogService
    monkeypatch.setattr(ActivityLogService, "log", staticmethod(lambda *a, **k: None))

    # The task does `from app.db.session import SessionLocal` at call time, so
    # patch it on the source module. Hand back the shared test session and stop
    # the task from closing it out from under the assertions.
    monkeypatch.setattr(db_session, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None, raising=False)

    return dispatched


def _make_org(db, **overrides):
    org = Organization(name="Acme", subscription_status="active", **overrides)
    db.add(org)
    db.flush()
    return org


def _make_location(db, org, billing_status="active"):
    loc = Location(
        organization_id=org.id,
        google_location_id="locations/123",
        location_name="Downtown",
        billing_status=billing_status,
    )
    db.add(loc)
    db.flush()
    return loc


def _make_scheduled_post(db, org, loc, campaign=None):
    post = Post(
        organization_id=org.id,
        campaign_id=campaign.id if campaign else None,
        summary="Hello {{location}}",
        status=PostStatus.SCHEDULED.value,
        scheduled_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1),
        target_location_ids=[loc.id],
    )
    db.add(post)
    db.flush()
    return post


def test_due_scheduled_post_is_staged_and_dispatched(db, patched_externals):
    """A due scheduled post with an active location transitions to PUBLISHING,
    stages a PENDING PublishJob, and dispatches a publish task."""
    from app.tasks import check_scheduled_posts_task

    org = _make_org(db)
    loc = _make_location(db, org)
    post = _make_scheduled_post(db, org, loc)
    db.commit()

    result = check_scheduled_posts_task()
    assert result["status"] == "success"
    assert result["processed_count"] == 1

    db.refresh(post)
    assert post.status == "PUBLISHING"

    jobs = db.query(PublishJob).filter(PublishJob.post_id == post.id).all()
    assert len(jobs) == 1
    assert jobs[0].status == PublishJobStatus.PENDING.value
    assert patched_externals  # at least one task dispatched


def test_locked_org_leaves_post_scheduled(db, patched_externals):
    """A due post for a locked org must NOT publish; it stays SCHEDULED so it
    fires automatically once the org reactivates."""
    from app.tasks import check_scheduled_posts_task

    org = _make_org(db, subscription_status="locked")
    loc = _make_location(db, org)
    post = _make_scheduled_post(db, org, loc)
    db.commit()

    check_scheduled_posts_task()

    db.refresh(post)
    assert post.status == PostStatus.SCHEDULED.value
    assert db.query(PublishJob).filter(PublishJob.post_id == post.id).count() == 0


def test_invalid_media_fails_post_and_campaign(db, patched_externals):
    """Invalid media fails the scheduled post AND keeps its campaign in lock-step
    (campaign flips to FAILED rather than being stuck displaying Scheduled)."""
    from app.tasks import check_scheduled_posts_task

    org = _make_org(db)
    loc = _make_location(db, org)
    campaign = Campaign(
        organization_id=org.id,
        name="Spring",
        status=CampaignStatus.SCHEDULED.value,
    )
    db.add(campaign)
    db.flush()
    post = _make_scheduled_post(db, org, loc, campaign=campaign)
    campaign.primary_post_id = post.id

    db.add(PostMedia(
        organization_id=org.id,
        post_id=post.id,
        storage_provider="local",
        storage_key="k.jpg",
        sha256_hash="x" * 64,
        cdn_url="https://cdn/x.jpg",
        upload_status="Failed",
        validation_status="Invalid",
        is_deleted=False,
    ))
    db.commit()

    check_scheduled_posts_task()

    db.refresh(post)
    db.refresh(campaign)
    assert post.status == PostStatus.FAILED.value
    assert campaign.status == CampaignStatus.FAILED.value
    assert db.query(PublishJob).filter(PublishJob.post_id == post.id).count() == 0
