"""Entitlement state machine for the card-required onboarding flow.

Pure logic over an in-memory Organization (no DB/session needed) — asserts the three
states a caller cares about (org_locked / onboarding / premium_unlocked) for every
point in the trial → active → past_due → locked lifecycle.
"""
from datetime import datetime, timedelta, timezone

from app.models.organization import Organization
from app.services.billing.entitlement_service import EntitlementService as E

NOW = datetime.now(timezone.utc)


def _org(**kw) -> Organization:
    o = Organization(name="t")
    o.subscription_status = kw.get("status", "trial")
    o.trial_ends_at = kw.get("trial_ends_at")
    o.grace_period_ends_at = kw.get("grace_period_ends_at")
    o.subscription_ends_at = kw.get("subscription_ends_at")
    o.created_at = kw.get("created_at", NOW)
    return o


def test_onboarding_pre_payment():
    # Synced but no mandate yet: not locked (audit may run) but premium withheld.
    o = _org(status="trial", trial_ends_at=None)
    assert E.is_onboarding(o) is True
    assert E.is_org_locked(o) is False
    assert E.is_premium_unlocked(o) is False


def test_onboarding_expires_after_pending_cap():
    # An abandoned pre-payment signup past the cap locks -> premium stays off.
    o = _org(status="trial", trial_ends_at=None, created_at=NOW - timedelta(days=15))
    assert E.is_org_locked(o) is True
    assert E.is_premium_unlocked(o) is False


def test_trial_running():
    o = _org(status="trial", trial_ends_at=NOW + timedelta(days=7))
    assert E.is_onboarding(o) is False
    assert E.is_org_locked(o) is False
    assert E.is_premium_unlocked(o) is True


def test_trial_expired():
    o = _org(status="trial", trial_ends_at=NOW - timedelta(days=1))
    assert E.is_org_locked(o) is True
    assert E.is_premium_unlocked(o) is False


def test_active():
    o = _org(status="active")
    assert E.is_premium_unlocked(o) is True


def test_active_cancelled_but_still_valid():
    o = _org(status="active", subscription_ends_at=NOW + timedelta(days=5))
    assert E.is_premium_unlocked(o) is True


def test_active_cancelled_period_elapsed():
    o = _org(status="active", subscription_ends_at=NOW - timedelta(days=1))
    assert E.is_org_locked(o) is True
    assert E.is_premium_unlocked(o) is False


def test_past_due_within_grace():
    o = _org(status="past_due", grace_period_ends_at=NOW + timedelta(days=2))
    assert E.is_premium_unlocked(o) is True


def test_past_due_grace_elapsed():
    o = _org(status="past_due", grace_period_ends_at=NOW - timedelta(hours=1))
    assert E.is_org_locked(o) is True
    assert E.is_premium_unlocked(o) is False


def test_locked():
    o = _org(status="locked")
    assert E.is_premium_unlocked(o) is False
