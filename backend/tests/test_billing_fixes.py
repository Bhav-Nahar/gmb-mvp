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
        subscription_status="trial_pending_activation",
        monthly_ai_credits_balance=200,
        topup_ai_credits_balance=0
    )
    db.add(org)
    db.commit()
    db.refresh(org)

    payload = {
        "event": "subscription.charged",
        "contains": {
            "subscription": {
                "entity": {
                    "id": "sub_12345",
                    "current_end": 1774880000,
                    "notes": {
                        "organization_id": str(org.id)
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
    assert org.monthly_ai_credits_balance == 200

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
        "contains": {
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
