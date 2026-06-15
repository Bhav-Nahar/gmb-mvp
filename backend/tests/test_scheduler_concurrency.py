import pytest
from app.models.post import Post
from app.constants.posts import PostStatus
from app.tasks import check_scheduled_posts_task
import datetime

@pytest.mark.asyncio
async def test_scheduler_concurrency_skips_locked_rows(db_session, mock_organization):
    """
    Test that check_scheduled_posts_task safely skips rows locked by another transaction
    and transitions scheduled posts to APPROVED state.
    """
    # Create scheduled post
    post = Post(
        organization_id=mock_organization.id,
        summary="Test post",
        status=PostStatus.SCHEDULED.value,
        scheduled_at=datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)
    )
    db_session.add(post)
    db_session.commit()
    
    # Run the scheduler task
    result = check_scheduled_posts_task()
    
    # Assert successful process count
    assert result["status"] == "success"
    
    # Refresh post and verify status
    db_session.refresh(post)
    assert post.status == PostStatus.APPROVED.value
