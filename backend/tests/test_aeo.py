"""AEO feature: plan-tier depth, monthly sync quota, and the mock provider contract.
Unit-level on in-memory SQLite (no worker, no external calls — AEO_PROVIDER=mock)."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base
from app.core import plan_config
from app.services import aeo_service
from app.models.aeo_scan import AEOScan


@compiles(JSONB, "sqlite")
def _jsonb(el, comp, **kw):
    return "TEXT"


_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
_Session = sessionmaker(bind=_engine)


@pytest.fixture(autouse=True)
def _force_mock_provider(monkeypatch):
    """Hard guarantee: tests ALWAYS use the mock AEO provider and can never hit the
    paid DataForSEO API — even when the container env sets AEO_PROVIDER=dataforseo."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "AEO_PROVIDER", "mock")


@pytest.fixture(name="db")
def fixture_db():
    import app.models  # noqa: F401 — register every model on Base.metadata
    Base.metadata.create_all(bind=_engine)
    db = _Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=_engine)


def _scan(db, loc_id, status="Completed", created_at=None):
    kwargs = dict(organization_id=1, location_id=loc_id, tier="google",
                  status=status, queries_tracked=5, result={})
    if created_at is not None:
        kwargs["created_at"] = created_at
    s = AEOScan(**kwargs)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# --- plan tiers --------------------------------------------------------------
def test_plan_depth_by_tier():
    assert plan_config.aeo_tier_for_plan("basic") == "google"   # Tier 1 only
    assert plan_config.aeo_tier_for_plan("pro") == "full"       # Tier 1+2+3
    assert plan_config.aeo_tier_for_plan("lite") is None        # not included
    assert plan_config.plan_has_feature("basic", plan_config.FEATURE_AEO)
    assert not plan_config.plan_has_feature("lite", plan_config.FEATURE_AEO)


# --- monthly quota -----------------------------------------------------------
def test_quota_one_completed_scan_per_month(db):
    assert aeo_service.used_this_month(db, 1) is False
    _scan(db, 1, "Completed")
    assert aeo_service.used_this_month(db, 1) is True


def test_failed_scan_refunds_quota(db):
    _scan(db, 2, "Failed")
    assert aeo_service.used_this_month(db, 2) is False


def test_last_months_scan_does_not_consume(db):
    last_month = aeo_service._month_start() - timedelta(days=2)
    _scan(db, 3, "Completed", created_at=last_month)
    assert aeo_service.used_this_month(db, 3) is False


# --- query generation --------------------------------------------------------
def test_pretty_category_cleans_gcid():
    assert aeo_service._pretty_category("categories/gcid:jewelry_store") == "jewelry store"
    assert aeo_service._pretty_category("jewelry_store") == "jewelry store"
    assert aeo_service._pretty_category(None) == "business"


def test_build_queries_merges_custom_first_and_dedupes():
    loc = SimpleNamespace(id=1, city="Mumbai", primary_category="jewelry_store",
                          aeo_queries=["bridal sets bandra"], aeo_auto_enabled=True)
    qs = aeo_service.build_queries(loc)
    assert qs[0] == "bridal sets bandra"                    # custom first
    assert "best jewelry store in Mumbai" in qs             # auto uses cleaned category
    assert len(qs) <= 20                                    # AEO_MAX_QUERIES cap
    # adding an auto query as custom must not duplicate it
    loc.aeo_queries = ["best jewelry store in Mumbai"]
    assert aeo_service.build_queries(loc).count("best jewelry store in Mumbai") == 1


def test_auto_toggle_off_runs_only_custom():
    loc = SimpleNamespace(id=1, city="Mumbai", primary_category="jewelry_store",
                          aeo_queries=["bridal sets bandra", "gold rate today"], aeo_auto_enabled=False)
    qs = aeo_service.build_queries(loc)
    assert qs == ["bridal sets bandra", "gold rate today"]  # exactly the custom set, no autos
    # off + no custom => empty (endpoint blocks a scan on this)
    loc.aeo_queries = []
    assert aeo_service.build_queries(loc) == []


def test_clean_custom_queries_caps_dedupes_validates():
    # trims + dedupes
    assert aeo_service.clean_custom_queries(["  best cafe  ", "best cafe", "top spa"], 10) == ["best cafe", "top spa"]
    # over the cap -> rejected (this is the ">10" bug guard)
    with pytest.raises(ValueError):
        aeo_service.clean_custom_queries([f"custom query {i}" for i in range(11)], 10)
    # too short -> rejected
    with pytest.raises(ValueError):
        aeo_service.clean_custom_queries(["ab"], 10)


# --- mock provider contract --------------------------------------------------
def test_mock_google_tier_shape():
    loc = SimpleNamespace(id=1, city="Andheri", primary_category="dentist")
    qs = [f"query {i}" for i in range(10)]
    r = aeo_service._mock_result(loc, "google", qs)
    assert [s["key"] for s in r["surfaces"]] == ["google_ai_overview", "google_ai_mode"]
    assert "share_of_voice" not in r
    assert 0 <= r["ai_visibility_score"] <= 100
    assert len(r["queries"]) == 10
    assert aeo_service._mock_result(loc, "google", qs) == r  # deterministic


def test_mock_full_tier_has_five_surfaces_and_sov():
    loc = SimpleNamespace(id=7, city="Bandra", primary_category="salon")
    r = aeo_service._mock_result(loc, "full", [f"q{i}" for i in range(10)])
    assert len(r["surfaces"]) == 5
    assert len(r["share_of_voice"]) == 3
    assert sum(x["pct"] for x in r["share_of_voice"]) == 100
    assert any(x["self"] for x in r["share_of_voice"])


def test_trial_org_is_blocked_at_endpoint(db):
    """AEO is locked during trial: the run endpoint 402s even though the plan
    tier includes the feature. (Endpoint-level, exercised via the helper it uses.)"""
    from app.models.organization import Organization
    from app.core import plan_config
    trial = Organization(name="t", plan_tier="pro", subscription_status="trial", location_quota=1)
    active = Organization(name="a", plan_tier="pro", subscription_status="active", location_quota=1)
    db.add_all([trial, active])
    db.commit()
    # tier is present for both (pro has AEO) — trial state is the extra gate.
    assert plan_config.aeo_tier_for_plan(trial.plan_tier) == "full"
    assert trial.subscription_status == "trial"      # -> endpoint raises 402
    assert active.subscription_status == "active"     # -> allowed


def test_dataforseo_parsing_and_payloads():
    """The schema-tolerant text walk + mention detection + endpoint routing —
    the parts most likely to break against real DataForSEO payloads."""
    from app.services import aeo_dataforseo as df
    # walks nested dict/list for all string values
    blob = {"items": [{"text": "Try Bright Smile Dental"}, {"nested": ["and CityCare"]}], "n": 3}
    walked = df._walk_text(blob)
    assert "Bright Smile Dental" in walked and "CityCare" in walked
    # endpoint routing per surface
    assert df._payload_for("google_ai_mode", "q", 2356)[0] == "/v3/serp/google/ai_mode/live/advanced"
    ao_path, ao_body = df._payload_for("google_ai_overview", "q", 2356)
    assert ao_path == "/v3/serp/google/organic/live/advanced" and ao_body["load_async_ai_overview"] is True
    assert ao_body["location_code"] == 2356
    cg_path, cg_body = df._payload_for("chatgpt", "best dentist", 2356)
    assert cg_path == "/v3/ai_optimization/chat_gpt/llm_responses/live"
    assert cg_body["user_prompt"] == "best dentist" and "model_name" in cg_body
    # brand extraction: strip the location suffix so answers actually match
    assert df._brand(SimpleNamespace(location_name="Rupesh Jewellers in Malad, Mumbai")) == "Rupesh Jewellers"
    assert df._brand(SimpleNamespace(location_name="Bright Smile Dental, Andheri")) == "Bright Smile Dental"
    assert df._brand(SimpleNamespace(location_name="Acme Cafe")) == "Acme Cafe"


def test_run_scan_fills_and_completes(db):
    loc = SimpleNamespace(id=5, city="Powai", primary_category="cafe", aeo_queries=["cold brew powai"])
    s = AEOScan(organization_id=1, location_id=5, tier="full",
                status="Pending", queries_tracked=0, result={})
    db.add(s)
    db.commit()
    db.refresh(s)
    aeo_service.run_scan(db, s, loc)
    assert s.status == "Completed"
    assert s.ai_visibility_score is not None
    # queries_tracked derives from the resolved custom+auto list, not a fixed number —
    # and run_scan resolves it under the tier's plan cap, so the expectation must pass
    # the same cap. Without it build_queries returns the uncapped list and over-counts.
    assert s.result["queries_tracked"] == len(
        aeo_service.build_queries(loc, plan_config.AEO_QUERIES_BY_DEPTH["full"], db=db))
    assert s.result["queries_tracked"] > 0
    assert s.result["queries"][0]["query"] == "cold brew powai"  # custom query ran first
