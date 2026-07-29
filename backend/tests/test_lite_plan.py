"""Lite plan gating: feature gate, 1-location cap, scheduler block, insights window,
search-query cap, and team/seat cap. Unit-level so they run on in-memory SQLite."""
import datetime
import sys
import types
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base
from app.core import plan_config
from app.models.organization import Organization
from app.models.user import User



@compiles(JSONB, "sqlite")
def _jsonb(el, comp, **kw):
    return "TEXT"


_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(name="db")
def fixture_db():
    Base.metadata.create_all(bind=_engine)
    db = _Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=_engine)


def _org_user(db, tier):
    o = Organization(name=tier, plan_tier=tier, subscription_status="active", location_quota=1)
    db.add(o)
    db.commit()
    db.refresh(o)
    u = User(email=f"{tier}@t.com", name=tier, google_id=f"g_{tier}", role="Owner",
             is_active=True, organization_id=o.id)
    db.add(u)
    db.commit()
    db.refresh(u)
    return o, u


# --- tier config -------------------------------------------------------------

def test_lite_has_no_premium_features_and_tight_limits():
    for f in (plan_config.FEATURE_SCHEDULER, plan_config.FEATURE_TEAM, plan_config.FEATURE_TEMPLATES,
              plan_config.FEATURE_AUTO_REPLY, plan_config.FEATURE_LEADERBOARD, plan_config.FEATURE_COMPARISON,
              plan_config.FEATURE_LOCAL_RANK, plan_config.FEATURE_MICROSITE):
        assert not plan_config.plan_has_feature("lite", f)
        assert plan_config.plan_has_feature("pro", f)
    # Lite went unlimited-locations with the July 2026 flat pricing — the upsell to
    # Basic rests on the feature gap above, not on a location cap.
    assert plan_config.plan_limit("lite", plan_config.LIMIT_MAX_LOCATIONS) is None
    assert plan_config.plan_limit("lite", plan_config.LIMIT_INSIGHTS_DAYS) == 7
    assert plan_config.plan_limit("lite", plan_config.LIMIT_SEARCH_QUERIES) == 10
    assert plan_config.plan_limit("basic", plan_config.LIMIT_MAX_LOCATIONS) is None


# --- central feature gate ----------------------------------------------------

def test_require_feature_blocks_lite_allows_basic(db):
    import types
    from app.api.deps import require_feature
    gate = require_feature(plan_config.FEATURE_LEADERBOARD)
    # Minimal stand-in for the Request the dep now uses for per-request org caching.
    _req = lambda: types.SimpleNamespace(state=types.SimpleNamespace())

    _, lite_user = _org_user(db, "lite")
    with pytest.raises(HTTPException) as exc:
        gate(request=_req(), db=db, current_user=lite_user)
    assert exc.value.status_code == 403

    _, basic_user = _org_user(db, "basic")
    assert gate(request=_req(), db=db, current_user=basic_user) is None   # allowed


# --- scheduler gate ----------------------------------------------------------

def test_scheduler_blocks_future_post_on_lite_allows_now(db):
    from app.api.posts import _assert_can_schedule
    _, lite_user = _org_user(db, "lite")
    future = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)

    with pytest.raises(HTTPException) as exc:
        _assert_can_schedule(db, lite_user, future)
    assert exc.value.status_code == 403
    # Posting now (no timestamp) is always fine, even on Lite.
    assert _assert_can_schedule(db, lite_user, None) is None

    _, basic_user = _org_user(db, "basic")
    assert _assert_can_schedule(db, basic_user, future) is None   # scheduling allowed


# --- insights window ---------------------------------------------------------

def test_insights_floor_caps_lite_to_seven_days(db):
    from app.api.insights import _insights_start_floor
    end = datetime.date(2026, 7, 1)
    _, lite_user = _org_user(db, "lite")
    _, basic_user = _org_user(db, "basic")
    assert _insights_start_floor(db, lite_user, end) == end - datetime.timedelta(days=6)  # 7-day window
    assert _insights_start_floor(db, basic_user, end) is None                             # unlimited
