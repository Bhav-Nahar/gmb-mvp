import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.models.organization import Organization
from app.models.user import User
from app.models.billing_webhook_event import BillingWebhookEvent
from app.models.billing_transaction import BillingTransaction
from app.services.billing.webhook_service import WebhookService
from app.services.billing.subscription_service import SubscriptionService
from app.api.deps import get_current_user

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"

# Setup SQLite in-memory database
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(name="db")
def fixture_db():
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture(name="client")
def fixture_client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()

def test_webhook_bypasses_auth(client):
    """Verify that public webhook endpoints bypass authentication/CSRF checks."""
    # Sending a post request to the webhook without token should not return 401.
    # It should fail with 400 due to missing signature/invalid signature, not 401 or 403 CSRF.
    response = client.post("/api/v1/webhooks/razorpay", json={"event": "payment.captured"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Missing signature"

def test_check_billing_lock_enforces_402_only_on_mutations(client, db):
    """Verify check_billing_lock blocks mutating actions for locked orgs but allows GET."""
    # Seed locked organization and active admin user
    org = Organization(
        name="Locked Org",
        plan="starter",
        subscription_status="locked",
        monthly_ai_credits_balance=0,
        topup_ai_credits_balance=0
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    user = User(
        email="admin@locked.com",
        name="Admin User",
        google_id="google_locked",
        role="Admin",
        is_active=True,
        organization_id=org.id
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Generate a realistic JWT token for our seeded user and set in client cookies
    from app.core.security import create_access_token
    token = create_access_token(user.email, token_version=user.token_version)
    client.cookies.set("gmb_auth_token", token)

    # 1. GET requests should succeed/pass through billing lock (returns 404 since location 999 doesn't exist, but NOT 402)
    response = client.get("/api/v1/locations/999")
    assert response.status_code != 402

    # 2. POST (mutating) requests on locked org should fail with 402
    response = client.post("/api/v1/locations/sync")
    assert response.status_code == 402
    assert "Organization is locked" in response.json()["detail"]



def test_webhook_processing_success(db):
    """Test webhook processing saves events with payload and updates organization billing data."""
    org = Organization(
        name="Test Org",
        plan="starter",
        subscription_status="trial",
        monthly_ai_credits_balance=200,
        topup_ai_credits_balance=0
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    # Mirrors Razorpay's real webhook shape: `contains` is a list of entity names,
    # and the entities themselves live under `payload`.
    payload = {
        "event": "subscription.charged",
        "contains": ["subscription", "payment"],
        "payload": {
            "subscription": {
                "entity": {
                    "id": "sub_12345",
                    "current_end": 1774880000,
                    "notes": {
                        "organization_id": str(org.id),
                        "location_count": "2"
                    }
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_12345",
                    "amount": 100000,
                    "currency": "INR",
                    "order_id": "order_12345"
                }
            }
        }
    }

    # Process the webhook directly via service
    WebhookService.process_webhook(db, "evt_12345", "subscription.charged", payload)

    # Verify event stored in DB with payload
    stored_event = db.query(BillingWebhookEvent).filter_by(razorpay_event_id="evt_12345").first()
    assert stored_event is not None
    assert stored_event.payload == payload

    # Verify org updated
    db.refresh(org)
    assert org.subscription_status == "active"
    assert org.monthly_ai_credits_balance == 60  # 2 locations * 30 credits

    # Verify transaction logged with correct fields
    tx = db.query(BillingTransaction).filter_by(organization_id=org.id).first()
    assert tx is not None
    assert tx.transaction_type == "subscription_charge"
    assert tx.amount_paise == 100000
    assert tx.currency == "INR"
    assert tx.razorpay_payment_id == "pay_12345"
    assert tx.razorpay_order_id == "order_12345"
    assert tx.razorpay_subscription_id == "sub_12345"
    assert tx.credits is None  # Subscription charged does not change specific topups

def test_webhook_processing_topup(db):
    """Test webhook processing for topup charge updates balance and logs transaction."""
    org = Organization(
        name="Test Org",
        plan="starter",
        subscription_status="active",
        monthly_ai_credits_balance=200,
        topup_ai_credits_balance=0
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    payload = {
        "event": "payment.captured",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_topup",
                    "amount": 49900,
                    "currency": "INR",
                    "order_id": "order_topup",
                    "notes": {
                        "type": "topup",
                        "organization_id": str(org.id),
                        "credits": "500"
                    }
                }
            }
        }
    }

    WebhookService.process_webhook(db, "evt_topup", "payment.captured", payload)

    db.refresh(org)
    assert org.topup_ai_credits_balance == 500

    tx = db.query(BillingTransaction).filter_by(organization_id=org.id, transaction_type="topup_charge").first()
    assert tx is not None
    assert tx.amount_paise == 49900
    assert tx.razorpay_payment_id == "pay_topup"
    assert tx.razorpay_order_id == "order_topup"

def test_reconcile_subscription_activates_on_missed_webhook(db):
    """Safety net: if the subscription.charged webhook never arrived, pulling the
    live subscription from Razorpay should activate the org and grant entitlements."""
    org = Organization(
        name="Pending Org",
        subscription_status="trial",
        razorpay_subscription_id="sub_live_1",
        monthly_ai_credits_balance=0,
        location_quota=5,
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    fake_client = MagicMock()
    fake_client.subscription.fetch.return_value = {
        "id": "sub_live_1",
        "status": "active",
        "current_end": 1774880000,
        "notes": {"organization_id": str(org.id), "location_count": "3"},
    }

    with patch(
        "app.services.billing.subscription_service.SubscriptionService.get_razorpay_client",
        return_value=fake_client,
    ):
        activated = SubscriptionService.reconcile_subscription(db, org.id)

    assert activated is True
    db.refresh(org)
    assert org.subscription_status == "active"
    assert org.location_quota == 3
    assert org.monthly_ai_credits_balance == 90  # 3 locations * 30 credits


def test_reconcile_subscription_noop_when_not_active(db):
    """Reconcile must NOT activate if Razorpay still reports the subscription as
    not-yet-paid (e.g. created but never charged)."""
    org = Organization(
        name="Unpaid Org",
        subscription_status="trial",
        razorpay_subscription_id="sub_unpaid",
        monthly_ai_credits_balance=0,
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    fake_client = MagicMock()
    fake_client.subscription.fetch.return_value = {"id": "sub_unpaid", "status": "created"}

    with patch(
        "app.services.billing.subscription_service.SubscriptionService.get_razorpay_client",
        return_value=fake_client,
    ):
        activated = SubscriptionService.reconcile_subscription(db, org.id)

    assert activated is False
    db.refresh(org)
    assert org.subscription_status == "trial"


def test_is_org_locked_state_matrix(db):
    """Lock semantics for the collapsed 4-state model."""
    from datetime import datetime, timezone, timedelta
    from app.services.billing.entitlement_service import EntitlementService

    now = datetime.now(timezone.utc)

    pending = Organization(name="pending", subscription_status="trial", trial_ends_at=None)
    active_trial = Organization(name="trial", subscription_status="trial", trial_ends_at=now + timedelta(days=3))
    expired_trial = Organization(name="exp", subscription_status="trial", trial_ends_at=now - timedelta(days=1))
    active = Organization(name="active", subscription_status="active")
    cancelled_valid = Organization(name="cv", subscription_status="active", subscription_ends_at=now + timedelta(days=5))
    cancelled_ended = Organization(name="ce", subscription_status="active", subscription_ends_at=now - timedelta(days=1))
    grace = Organization(name="grace", subscription_status="past_due", grace_period_ends_at=now + timedelta(days=1))
    past_due_done = Organization(name="pd", subscription_status="past_due", grace_period_ends_at=now - timedelta(days=1))
    locked = Organization(name="locked", subscription_status="locked")

    assert EntitlementService.is_org_locked(pending) is False
    assert EntitlementService.is_org_locked(active_trial) is False
    assert EntitlementService.is_org_locked(expired_trial) is True
    assert EntitlementService.is_org_locked(active) is False
    assert EntitlementService.is_org_locked(cancelled_valid) is False
    assert EntitlementService.is_org_locked(cancelled_ended) is True
    assert EntitlementService.is_org_locked(grace) is False
    assert EntitlementService.is_org_locked(past_due_done) is True
    assert EntitlementService.is_org_locked(locked) is True


def test_ensure_razorpay_customer_two_pass(db):
    """Verify ensure_razorpay_customer returns existing customer id without database write locks."""
    org = Organization(
        name="Org with Customer",
        razorpay_customer_id="cust_already_exists"
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    # Calling ensure_razorpay_customer should return the existing customer ID
    # and not invoke Razorpay client or fail with transaction rollback issues.
    with patch("app.services.billing.subscription_service.SubscriptionService.get_razorpay_client") as mock_client:
        customer_id = SubscriptionService.ensure_razorpay_customer(db, org.id, org.name, "admin@test.com")
        assert customer_id == "cust_already_exists"
        mock_client.assert_not_called()


def test_renewal_preserves_unlocked_quota(db):
    """A renewal of an already-charged subscription must NOT reset quota back to the
    stale notes count. Mid-cycle unlocks bump org.location_quota; renewals trust the org."""
    org = Organization(
        name="Unlocked Org",
        subscription_status="active",
        razorpay_subscription_id="sub_renew",
        monthly_ai_credits_balance=0,
        location_quota=5,  # started at 4, unlocked a 5th mid-cycle
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    # Simulate a PRIOR charge for this subscription so this counts as a renewal.
    db.add(BillingTransaction(
        organization_id=org.id,
        transaction_type="subscription_charge",
        amount_paise=1,
        currency="INR",
        status="success",
        razorpay_payment_id="pay_prev",
        razorpay_subscription_id="sub_renew",
    ))
    db.commit()

    subscription = {
        "id": "sub_renew",
        "current_end": 1774880000,
        "notes": {"organization_id": str(org.id), "location_count": "4"},  # stale: was 4
    }
    payment = {"id": "pay_renew", "amount": 1000000, "currency": "INR"}
    WebhookService.apply_subscription_charged(db, org, subscription, payment)
    db.commit()
    db.refresh(org)

    # Quota stays at the unlocked 5, NOT reset to the notes' 4.
    assert org.location_quota == 5
    assert org.monthly_ai_credits_balance == 150  # 5 * 30


def test_assert_location_active_blocks_locked():
    """The paid-feature guard raises 402 for a locked location and passes for active."""
    from app.core.authorization import assert_location_active, assert_locations_active

    class FakeQuery:
        def __init__(self, value): self._value = value
        def filter(self, *a, **k): return self
        def scalar(self): return self._value
        def first(self): return (1,) if self._value not in ("active", None) else None

    class FakeDB:
        def __init__(self, value): self._value = value
        def query(self, *a, **k): return FakeQuery(self._value)

    # Locked -> 402
    with pytest.raises(HTTPException) as exc:
        assert_location_active(FakeDB("pending_payment"), 1)
    assert exc.value.status_code == 402

    # Active -> no raise
    assert_location_active(FakeDB("active"), 1)

    # Bulk: any locked -> 402
    with pytest.raises(HTTPException) as exc2:
        assert_locations_active(FakeDB("pending_payment"), [1, 2])
    assert exc2.value.status_code == 402


def test_proration_math():
    """Graduated marginal delta and time-based proration."""
    from app.services.billing.pricing_service import PricingService

    # Band 1 is ₹2,500 (250000 paise) per location for 1-10. 4 -> 5 adds one band-1 slot.
    assert PricingService.marginal_monthly_paise(4, 1, "monthly") == 250000
    # 10 -> 11 crosses into band 2 (₹2,000 = 200000) for the 11th.
    assert PricingService.marginal_monthly_paise(10, 1, "monthly") == 200000

    # Half a cycle -> half the marginal cost.
    assert PricingService.prorated_addon_paise(4, 1, "monthly", days_left=15, days_in_cycle=30) == 125000
    # Start of cycle -> full marginal.
    assert PricingService.prorated_addon_paise(4, 1, "monthly", days_left=30, days_in_cycle=30) == 250000
    # End of cycle -> 0.
    assert PricingService.prorated_addon_paise(4, 1, "monthly", days_left=0, days_in_cycle=30) == 0
    # Guard against div-by-zero.
    assert PricingService.prorated_addon_paise(4, 1, "monthly", days_left=5, days_in_cycle=0) == 250000


def test_location_addon_unlock_grants_and_activates(db):
    """A captured location_addon payment unlocks the locations, bumps quota, grants full
    per-location credits, and is idempotent on re-delivery."""
    from app.models.location import Location

    org = Organization(
        name="Addon Org",
        subscription_status="active",
        razorpay_subscription_id="sub_addon",
        location_quota=4,
        monthly_ai_credits_balance=120,  # 4 * 30
        billing_cycle="monthly",
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    locked = Location(
        organization_id=org.id,
        google_location_id="loc_pending_1",
        location_name="Pending Branch",
        sync_status="Synced",
        billing_status="pending_payment",
    )
    db.add(locked)
    db.commit()
    db.refresh(locked)

    payload = {"payload": {"payment": {"entity": {
        "id": "pay_addon_1",
        "amount": 125000,
        "currency": "INR",
        "order_id": "order_addon_1",
        "notes": {
            "organization_id": str(org.id),
            "type": "location_addon",
            "added": "1",
            "location_ids": str(locked.id),
        },
    }}}}

    # Avoid real Razorpay calls from the best-effort plan update / celery enqueue.
    with patch("app.services.billing.subscription_service.SubscriptionService.update_subscription_plan_for_quota"), \
         patch("app.worker.celery.send_task"):
        WebhookService._handle_payment_captured(db, payload)
        db.commit()

    db.refresh(org)
    db.refresh(locked)
    assert locked.billing_status == "active"
    assert org.location_quota == 5
    assert org.monthly_ai_credits_balance == 150  # 120 + 30

    # Idempotent: re-delivering the same payment must not double-grant.
    with patch("app.services.billing.subscription_service.SubscriptionService.update_subscription_plan_for_quota"), \
         patch("app.worker.celery.send_task"):
         WebhookService._handle_payment_captured(db, payload)
         db.commit()
    db.refresh(org)
    assert org.location_quota == 5
    assert org.monthly_ai_credits_balance == 150


def test_razorpay_mode_isolation(db):
    """Verify that customer and plan IDs are isolated by environment mode (test vs live)."""
    from app.core.config import settings
    from app.models.razorpay_plan import RazorpayPlan

    org = Organization(
        name="Mode Test Org",
        subscription_status="active",
        location_quota=1,
        billing_cycle="monthly",
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    # Mock Razorpay customer.create and plan.create
    fake_client = MagicMock()
    fake_client.customer.create.side_effect = lambda data: {"id": f"cust_mock_{data['email']}"}
    fake_client.plan.create.side_effect = lambda data: {"id": f"plan_mock_{data['item']['amount']}"}

    with patch("app.services.billing.subscription_service.SubscriptionService.get_razorpay_client", return_value=fake_client):
        # 1. Test environment
        with patch.object(settings, "RAZORPAY_KEY_ID", "rzp_test_key"):
            cust_id = SubscriptionService.ensure_razorpay_customer(db, org.id, org.name, "user@mode.com")
            assert cust_id == "cust_mock_user@mode.com"
            db.refresh(org)
            assert org.razorpay_customer_id == "test:cust_mock_user@mode.com"

            plan_id = SubscriptionService._get_or_create_plan(db, 1, "monthly")
            assert plan_id == "plan_mock_250000"  # Per-location graduated: 1 loc = 2500 INR = 250000 paise
            plan_row = db.query(RazorpayPlan).filter_by(location_count=1, interval="monthly").first()
            assert plan_row.razorpay_plan_id == "test:plan_mock_250000"

        # 2. Transition to live environment: should create new live records and ignore test ones
        fake_client.customer.create.side_effect = lambda data: {"id": "cust_live_123"}
        fake_client.plan.create.side_effect = lambda data: {"id": "plan_live_123"}

        with patch.object(settings, "RAZORPAY_KEY_ID", "rzp_live_key"):
            cust_id_live = SubscriptionService.ensure_razorpay_customer(db, org.id, org.name, "user@mode.com")
            assert cust_id_live == "cust_live_123"
            db.refresh(org)
            assert org.razorpay_customer_id == "live:cust_live_123"

            plan_id_live = SubscriptionService._get_or_create_plan(db, 1, "monthly")
            assert plan_id_live == "plan_live_123"
            # There should be two rows now: test and live
            plans = db.query(RazorpayPlan).filter_by(location_count=1, interval="monthly").all()
            assert len(plans) == 2
            plan_ids = [p.razorpay_plan_id for p in plans]
            assert "test:plan_mock_250000" in plan_ids
            assert "live:plan_live_123" in plan_ids

        # 3. Transition back to test: plans are stored durably per-mode (razorpay_plans
        # table), so the test plan from step 1 is reused. Customer ids are NOT stored
        # per-mode (single Organization.razorpay_customer_id column), so a live->test
        # round-trip can't recover the original test customer. That round-trip never
        # happens for a real org, so we only assert plan-level isolation here.
        with patch.object(settings, "RAZORPAY_KEY_ID", "rzp_test_key"):
            plan_id_test2 = SubscriptionService._get_or_create_plan(db, 1, "monthly")
            assert plan_id_test2 == "plan_mock_250000"
