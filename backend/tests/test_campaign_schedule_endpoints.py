import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.organization import Organization
from app.models.campaign import Campaign
from app.models.post import Post
from app.constants.posts import PostStatus, CampaignStatus
from app.api.posts import update_campaign_schedule, cancel_campaign_schedule
from app.schemas.posts import CampaignScheduleUpdateRequest


def _future(hours=24):
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=hours)


def _setup_scheduled_campaign(db):
    org = Organization(name="Acme", subscription_status="active")
    db.add(org)
    db.flush()
    post = Post(
        organization_id=org.id,
        summary="Old body",
        title="Old title",
        status=PostStatus.SCHEDULED.value,
        scheduled_at=_future(),
        target_location_ids=[1],
    )
    db.add(post)
    db.flush()
    campaign = Campaign(
        organization_id=org.id,
        name="Spring",
        status=CampaignStatus.SCHEDULED.value,
        primary_post_id=post.id,
    )
    db.add(campaign)
    post.campaign_id = campaign.id
    db.commit()
    user = SimpleNamespace(id=1, organization_id=org.id)
    return org, campaign, post, user


def test_edit_scheduled_campaign_updates_content_and_time(db):
    _, campaign, post, user = _setup_scheduled_campaign(db)
    new_time = _future(48)
    payload = CampaignScheduleUpdateRequest(
        title="New title", summary="New body", scheduled_at=new_time
    )

    update_campaign_schedule(campaign.id, payload, db=db, current_user=user)

    db.refresh(post)
    assert post.title == "New title"
    assert post.summary == "New body"
    assert post.scheduled_at.replace(microsecond=0) == new_time.replace(microsecond=0)
    # Still scheduled — editing must not change lifecycle state.
    assert post.status == PostStatus.SCHEDULED.value
    assert campaign.status == CampaignStatus.SCHEDULED.value


def test_reschedule_only_changes_time(db):
    _, campaign, post, user = _setup_scheduled_campaign(db)
    new_time = _future(72)
    payload = CampaignScheduleUpdateRequest(scheduled_at=new_time)

    update_campaign_schedule(campaign.id, payload, db=db, current_user=user)

    db.refresh(post)
    assert post.title == "Old title"          # untouched
    assert post.summary == "Old body"         # untouched
    assert post.scheduled_at.replace(microsecond=0) == new_time.replace(microsecond=0)


def test_cancel_schedule_reverts_to_draft(db):
    _, campaign, post, user = _setup_scheduled_campaign(db)

    cancel_campaign_schedule(campaign.id, db=db, current_user=user)

    db.refresh(post)
    db.refresh(campaign)
    assert post.status == PostStatus.DRAFT.value
    assert campaign.status == CampaignStatus.DRAFT.value


def test_edit_rejected_when_not_scheduled(db):
    _, campaign, post, user = _setup_scheduled_campaign(db)
    campaign.status = CampaignStatus.PROCESSING.value
    db.commit()

    payload = CampaignScheduleUpdateRequest(summary="x")
    with pytest.raises(HTTPException) as exc:
        update_campaign_schedule(campaign.id, payload, db=db, current_user=user)
    assert exc.value.status_code == 409


def test_past_scheduled_at_is_rejected_by_schema():
    with pytest.raises(ValueError):
        CampaignScheduleUpdateRequest(
            scheduled_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
        )


def test_empty_update_is_rejected_by_schema():
    with pytest.raises(ValueError):
        CampaignScheduleUpdateRequest()
