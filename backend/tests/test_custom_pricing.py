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
    # 20 locations: flat ₹1,999/loc = 20 * 199,900.
    assert PricingService.compute_price_paise(20, "monthly", "basic") == 20 * 199_900
    # Custom ₹1,300/loc (130000 paise) -> flat 20 * 130000 = 2,600,000.
    assert PricingService.compute_price_paise(20, "monthly", "basic", 130_000) == 2_600_000


def test_custom_annual_has_no_discount():
    # Standard annual uses the plan's discounted annual bands; custom annual is exactly rate*12.
    assert PricingService.compute_price_paise(10, "annual", "basic", 130_000) == 10 * 130_000 * 12
    # 10 locations annual = 10 * ₹1,599/mo * 12.
    assert PricingService.compute_price_paise(10, "annual", "basic") == 10 * 159_900 * 12


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
            "custom_prices": {"pro": 130000}, "custom_credits_per_location": 60, "reason": "enterprise deal",
        })
        assert r.status_code == 200, r.text
        db.refresh(target)
        assert target.custom_prices == {"pro": 130000}
        assert target.custom_credits_per_location == 60

        # Clear -> back to standard.
        r2 = client.patch(f"/api/v1/admin/organizations/{target.id}", json={
            "clear_custom_pricing": True, "reason": "revert",
        })
        assert r2.status_code == 200, r2.text
        db.refresh(target)
        assert target.custom_prices is None
        assert target.custom_credits_per_location is None


# --- checkout bills the custom amount ---------------------------------------

def test_checkout_uses_custom_rate_for_plan_and_credits(db):
    org = Organization(name="Ent", subscription_status="trial", location_quota=60, plan_tier="pro",
                       custom_prices={"pro": 130_000}, custom_credits_per_location=60)
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


def test_price_change_on_active_sub_schedules_next_renewal(db, client):
    target = Organization(name="Ent", subscription_status="active", location_quota=60, plan_tier="pro",
                          razorpay_subscription_id="sub_ent", billing_cycle="monthly")
    db.add(target)
    db.commit()
    db.refresh(target)
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL), \
         patch.object(SubscriptionService, "update_subscription_plan_for_quota", return_value="upgraded") as sched:
        _as_super(db, client)
        r = client.patch(f"/api/v1/admin/organizations/{target.id}",
                         json={"custom_prices": {"pro": 130000}, "reason": "deal"})
    assert r.status_code == 200, r.text
    sched.assert_called_once()                       # scheduled the plan change (at cycle end)
    assert r.json()["plan_change"] == "upgraded"
    assert "next renewal" in r.json()["message"]


def test_price_change_without_subscription_does_not_schedule(db, client):
    target = Organization(name="NewEnt", subscription_status="trial", location_quota=10, plan_tier="pro")
    db.add(target)
    db.commit()
    db.refresh(target)
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL), \
         patch.object(SubscriptionService, "update_subscription_plan_for_quota") as sched:
        _as_super(db, client)
        r = client.patch(f"/api/v1/admin/organizations/{target.id}",
                         json={"custom_prices": {"pro": 130000}, "reason": "deal"})
    assert r.status_code == 200, r.text
    sched.assert_not_called()                        # no live subscription to reschedule
    assert r.json()["plan_change"] is None


# --- per-tier scoping: the whole point of the map ----------------------------

def test_custom_rate_is_scoped_to_the_negotiated_tier(db):
    """A ₹799 Basic deal must not price Pro at ₹799, and must still be upsellable."""
    org = Organization(name="Deal", plan_tier="basic", custom_prices={"basic": 79_900})
    assert PricingService.custom_rate(org, "basic") == 79_900
    assert PricingService.custom_rate(org, "pro") is None   # standard Pro price applies
    # No map at all = standard everywhere.
    assert PricingService.custom_rate(Organization(name="Std", plan_tier="basic"), "basic") is None


def test_checkout_on_an_undiscounted_tier_bills_standard(db):
    """Same org, Pro checkout: the Basic rate must NOT leak into the Razorpay plan."""
    org = Organization(name="Deal", subscription_status="trial", location_quota=2, plan_tier="basic",
                       custom_prices={"basic": 79_900})
    db.add(org)
    db.commit()
    db.refresh(org)

    fake = MagicMock()
    fake.subscription.create.side_effect = lambda data: {"id": "sub_x"}
    with patch.object(SubscriptionService, "ensure_razorpay_customer", return_value="cust_1"), \
         patch.object(SubscriptionService, "_get_or_create_plan", return_value="plan_x") as plan_mock, \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        SubscriptionService.create_subscription_checkout(
            db, org.id, "Deal", "d@d.com", location_count=2, interval="monthly", plan_tier="pro")
    assert plan_mock.call_args.args[4] is None            # standard Pro pricing, no custom rate

    with patch.object(SubscriptionService, "ensure_razorpay_customer", return_value="cust_1"), \
         patch.object(SubscriptionService, "_get_or_create_plan", return_value="plan_x") as plan_mock, \
         patch.object(SubscriptionService, "get_razorpay_client", return_value=fake):
        SubscriptionService.create_subscription_checkout(
            db, org.id, "Deal", "d@d.com", location_count=2, interval="monthly", plan_tier="basic")
    assert plan_mock.call_args.args[4] == 79_900          # the negotiated Basic rate


def test_rate_for_a_tier_they_are_not_on_does_not_reschedule(db, client):
    """Editing the Pro rate for a Basic client touches no money today."""
    target = Organization(name="Ent", subscription_status="active", location_quota=5, plan_tier="basic",
                          razorpay_subscription_id="sub_b", billing_cycle="monthly")
    db.add(target)
    db.commit()
    db.refresh(target)
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL), \
         patch.object(SubscriptionService, "update_subscription_plan_for_quota") as sched:
        _as_super(db, client)
        r = client.patch(f"/api/v1/admin/organizations/{target.id}",
                         json={"custom_prices": {"pro": 149900}, "reason": "future upsell rate"})
    assert r.status_code == 200, r.text
    sched.assert_not_called()
    assert "basic" in r.json()["message"]


def test_unknown_tier_is_rejected(db, client):
    target = Organization(name="Ent", plan_tier="basic")
    db.add(target)
    db.commit()
    db.refresh(target)
    with patch.object(settings, "SUPERADMIN_EMAILS", SUPER_EMAIL):
        _as_super(db, client)
        r = client.patch(f"/api/v1/admin/organizations/{target.id}",
                         json={"custom_prices": {"platinum": 100}, "reason": "typo"})
    assert r.status_code == 400
    assert "platinum" in r.text


# --- /billing/quote reflects the org's own rate, but stays public ------------

def test_public_quote_is_standard_and_needs_no_auth(client):
    r = client.get("/api/v1/billing/quote", params={"location_count": 2, "plan_tier": "basic"})
    assert r.status_code == 200, r.text
    # Marketing homepage path: the standard Basic sticker price (GST-inclusive total).
    assert r.json()["total_paise"] == 2 * 199_900


def test_quote_uses_the_callers_negotiated_rate(db, client):
    org = Organization(name="Deal", plan_tier="basic", custom_prices={"basic": 79_900},
                       custom_credits_per_location=30, subscription_status="active")
    db.add(org)
    db.commit()
    db.refresh(org)
    u = User(email="deal@x.com", name="d", google_id="g_deal", role="Owner",
             is_active=True, organization_id=org.id)
    db.add(u)
    db.commit()
    db.refresh(u)
    client.cookies.set("gmb_auth_token", create_access_token(u.email, token_version=u.token_version))

    r = client.get("/api/v1/billing/quote", params={"location_count": 2, "plan_tier": "basic"})
    assert r.status_code == 200, r.text
    assert r.json()["total_paise"] == 2 * 79_900          # their deal, not the ₹1,999 sheet
    # A tier they have no deal on still quotes standard price.
    r2 = client.get("/api/v1/billing/quote", params={"location_count": 2, "plan_tier": "pro"})
    assert r2.json()["total_paise"] == 2 * 299_900
