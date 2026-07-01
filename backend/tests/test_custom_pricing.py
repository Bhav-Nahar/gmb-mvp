"""Enterprise custom pricing (Flavor B: per-location rate + per-location credits).

Covers the price/credit math (custom rate overrides tiers; no annual discount on custom),
the super-admin set/clear form, and that a custom-priced checkout bills the custom amount.
"""
import sys
import types
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import Base, get_db
from app.core.config import settings
from app.core.security import create_access_token
from app.core import plan_config
from app.models.organization import Organization
from app.models.user import User
from app.services.billing.pricing_service import PricingService
from app.services.billing.subscription_service import SubscriptionService

if "app.worker" not in sys.modules:
    _fw = types.ModuleType("app.worker")
    _fw.celery = MagicMock()
    sys.modules["app.worker"] = _fw


@compiles(JSONB, "sqlite")
def _jsonb(el, comp, **kw):
    return "TEXT"


_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
_Session = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
SUPER_EMAIL = "root@t.com"


@pytest.fixture(name="db")
def fixture_db():
    Base.metadata.create_all(bind=_engine)
    db = _Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=_engine)


@pytest.fixture(name="client")
def fixture_client(db):
    from fastapi.testclient import TestClient
    from app.main import app

    def _o():
        yield db
    app.dependency_overrides[get_db] = _o
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- pricing math ------------------------------------------------------------

def test_custom_rate_overrides_tiers_flat_per_location():
    # 20 locations: standard graduated = 10*250000 + 10*200000 = 4,500,000.
    assert PricingService.compute_price_paise(20, "monthly", "basic") == 4_500_000
    # Custom ₹1,300/loc (130000 paise) -> flat 20 * 130000 = 2,600,000.
    assert PricingService.compute_price_paise(20, "monthly", "basic", 130_000) == 2_600_000


def test_custom_annual_has_no_discount():
    # Standard annual applies the 20% discount; custom annual is exactly rate*12.
    assert PricingService.compute_price_paise(10, "annual", "basic", 130_000) == 10 * 130_000 * 12
    std = PricingService.compute_price_paise(10, "annual", "basic")
    assert std < 10 * 250_000 * 12   # discount applied for standard


def test_custom_credits_override():
    assert PricingService.get_credits_for_locations(20, "basic") == 20 * 30      # standard
    assert PricingService.get_credits_for_locations(20, "basic", 60) == 20 * 60  # custom


def test_custom_marginal_addon_is_linear():
    # Adding 1 location at a custom ₹1,300 rate costs exactly the rate (no band jumps).
    assert PricingService.marginal_monthly_paise(59, 1, "monthly", "basic", 130_000) == 130_000


# --- super-admin form set / clear -------------------------------------------

def _as_super(db, client):
    o = Organization(name="Super")
    db.add(o)
    db.commit()
    db.refresh(o)
    u = User(email=SUPER_EMAIL, name="root", google_id="g_root", role="Owner", is_active=True, organization_id=o.id)
    db.add(u)
    db.commit()
    db.refresh(u)
    client.cookies.set("gmb_auth_token", create_access_token(u.email, token_version=u.token_version))


def test_superadmin_sets_and_clears_custom_pricing(db, client):
    target = Organization(name="Enterprise", subscription_status="active", location_quota=60, plan_tier="pro")
    db.add(target)
    db.commit()
    db.refresh(target)

    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL):
        _as_super(db, client)
        r = client.patch(f"/api/v1/admin/organizations/{target.id}", json={
            "custom_price_paise": 130000, "custom_credits_per_location": 60, "reason": "enterprise deal",
        })
        assert r.status_code == 200, r.text
        db.refresh(target)
        assert target.custom_price_paise == 130000
        assert target.custom_credits_per_location == 60

        # Clear -> back to standard.
        r2 = client.patch(f"/api/v1/admin/organizations/{target.id}", json={
            "clear_custom_pricing": True, "reason": "revert",
        })
        assert r2.status_code == 200, r2.text
        db.refresh(target)
        assert target.custom_price_paise is None
        assert target.custom_credits_per_location is None


# --- checkout bills the custom amount ---------------------------------------

def test_checkout_uses_custom_rate_for_plan_and_credits(db):
    org = Organization(name="Ent", subscription_status="trial", location_quota=60, plan_tier="pro",
                       custom_price_paise=130_000, custom_credits_per_location=60)
    db.add(org)
    db.commit()
    db.refresh(org)

    captured = {}
    fake = MagicMock()
    fake.subscription.create.side_effect = lambda data: (captured.update(data) or {"id": "sub_ent"})
    with patch.object(SubscriptionService, "ensure_razorpay_customer", return_value="cust_1"), \
         patch.object(SubscriptionService, "_get_or_create_plan", return_value="plan_ent") as plan_mock, \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        SubscriptionService.create_subscription_checkout(
            db, org.id, "Ent", "e@e.com", location_count=60, interval="monthly", plan_tier="pro")

    # The plan was built with the custom per-location rate, and notes carry custom credits.
    assert plan_mock.call_args.args[4] == 130_000       # custom_per_location_paise threaded through
    assert captured["notes"]["credits"] == str(60 * 60)  # 60 locations * 60 custom credits
