# Location Quota Enforcement + Mid-Cycle Proration — Implementation Plan

Status: Draft for review
Author: prepared with Claude Code
Related files: `backend/app/tasks.py`, `backend/app/api/deps.py`,
`backend/app/services/billing/*`, `backend/app/models/location.py`,
`backend/app/models/organization.py`

---

## 1. Model (the behaviour we're building)

- **Grandfather everything that already exists.** On rollout, every location currently
  in the DB becomes `active`. We never retroactively lock a location a customer is
  already using.
- **Only newly detected locations are gated.** When a sync discovers a location that is
  not already in the DB, and the org is already at its paid quota, that location is
  inserted in a **`pending_payment`** (locked) state.
- **Locked = visible but inert.** A `pending_payment` location shows in the UI as
  "Pending payment — unlock", but receives **no paid processing**: no review sync, no
  attribute sync, no insights, no AI replies, no posts, no SLA clock.
- **Unlock = pay prorated.** To activate a locked location mid-cycle, the customer pays a
  **prorated** amount for the remainder of the current billing cycle. On payment we bump
  `location_quota`, flip the location(s) to `active`, grant credits, and raise the
  recurring amount for future cycles.

### Decisions locked in
- **Credits for a mid-cycle add:** grant the **full** `CREDITS_PER_LOCATION` (30) per
  unlocked location immediately. (Rationale below.)
- **Grandfathering:** yes — only NEW locations are ever blocked.

---

## 2. Credits for a mid-cycle add — explained

`plan_config.CREDITS_PER_LOCATION = 30`. A normal subscription grants
`location_count * 30` monthly credits, which reset each cycle on
`ai_credits_reset_date` (set from Razorpay `current_end`).

When a location is unlocked mid-cycle we **add a full 30** credits to
`org.monthly_ai_credits_balance` immediately, rather than prorating the credit grant.

Why full, not prorated:
1. **Goodwill > cost.** 30 AI credits is a tiny marginal cost; nickel-and-diming a
   fractional credit grant creates a worse first impression on a location the customer
   just paid to add.
2. **No drift at reset.** Credits are a *balance that resets*, not a meter we bill on.
   At the next `ai_credits_reset_date` the subscription renews on the new plan
   (`new_total * 30`) and the balance is recomputed cleanly. So a generous mid-cycle
   grant self-corrects at the cycle boundary — it never compounds.
3. **Matches the money model.** We *do* prorate the **rupees** (that's the fair part).
   Credits are an entitlement, not the thing being metered, so they don't need to be
   prorated to be fair.

> Note: the **rupees are prorated, the credits are not.** Keep these two separate in
> code and in any customer-facing copy.

---

## 3. Grandfathering — explained

"Grandfathering" here means: when we turn enforcement on, no existing customer
experiences a location going dark. We achieve it purely through defaults + backfill:

- New column `Location.billing_status` defaults to `'active'`.
- The migration backfills **all existing rows** to `'active'`.
- The new gate only ever assigns `'pending_payment'` to a location at **insert time**,
  and only when `active_count >= quota`.

Consequence for an org that is *already* over quota (e.g. 5 locations in DB, paid for 4
before enforcement existed): all 5 stay `active`. They are simply not charged
retroactively. Because `active_count (5) >= quota (4)`, any *future* new location will
correctly land in `pending_payment`. This is the desired, non-disruptive behaviour.

---

## 4. Data model changes

### 4.1 `Location.billing_status`
`backend/app/models/location.py`
```python
# 'active'           -> counts against quota, fully processed
# 'pending_payment'  -> locked: visible but excluded from all paid processing
billing_status = Column(
    String, nullable=False, default="active", server_default=text("'active'")
)
```
Add an index for the hot `active`-count query:
```python
Index("ix_locations_org_billing_status", "organization_id", "billing_status")
```

### 4.2 Alembic migration
- Add the column with `server_default='active'` (backfills existing rows = grandfather).
- Add the composite index.
- Chain off the current head (check `alembic heads`).

> No change needed to `Organization` — `location_quota` already exists and already
> means "active locations allowed". We are finally *enforcing* it.

---

## 5. Backend — enforce the cap during sync (the core fix)

`backend/app/tasks.py`, location sync loop (~lines 259-319).

Today every provider location is inserted unconditionally. Change the **insert-new**
branch to respect quota. Existing-location updates are untouched (grandfather + never
disrupt).

```python
# Before the loop:
quota = org.location_quota if org.location_quota is not None else plan_config.TRIAL_LOCATION_QUOTA
active_count = sum(1 for loc in existing_locations if loc.billing_status == "active")

# Inside the loop, only in the "Insert new" branch:
if active_count < quota:
    billing_status = "active"
    active_count += 1
else:
    billing_status = "pending_payment"
new_loc = Location(..., billing_status=billing_status)
```

Then, **only enqueue downstream work for active locations**:
```python
if billing_status == "active":
    sync_jobs.append(loc_id)   # review sync, attribute sync, etc. only for active
```
Existing active locations continue to be added to `sync_jobs` as today.

Net effect: locked locations get a DB row (visible in the UI) but never enter the
review/attribute/insight fan-out at lines 324-331.

### 5.1 Surface the held-back count
Add the locked count to the sync log message and `sync_state` so the frontend can show
"2 locations need payment to activate":
```python
locked_count = <count of pending_payment inserted this run>
log_message = f"Synchronized {synced_count} locations. {locked_count} pending payment."
```

---

## 6. Backend — gate paid features on `billing_status`

A locked location must be inert everywhere, not just at sync. Audit and gate each path:

| Path | File | Gate |
| --- | --- | --- |
| Review sync fan-out | `tasks.py` (sync_jobs) | only `active` (done in §5) |
| Attribute sync | `tasks.py:330` | only `active` |
| Insight harvest | `insight_sync_service.py` / beat | filter `billing_status == "active"` |
| AI reply generation | `ai_reply_service.py` / `api/reviews.py` | 402 if location locked |
| Post publishing | `post_service.py` / `api/posts.py` | reject locked target locations |
| Listing edits | `api/listing_edits.py` | reject locked |
| SLA clock | wherever `sla_tracking_started_at` is set | don't start for locked |

Add one helper to centralise the check, e.g. in `app/core/authorization.py` or a small
`billing_guards.py`:
```python
def assert_location_active(location: Location):
    if location.billing_status != "active":
        raise HTTPException(status_code=402, detail="location_locked: unlock to use this feature.")
```

### 6.1 Retire / repurpose the dead `check_location_quota`
`deps.py:190` `check_location_quota` is currently dead code (never wired). Either delete
it or repurpose it as the guard for any **manual** "add location" endpoint. The sync path
(§5) is the authoritative enforcement point because it's a Celery task the HTTP
dependency can never gate.

---

## 7. Backend — proration pricing

`backend/app/services/billing/pricing_service.py` — add:

```python
@staticmethod
def marginal_monthly_paise(current_quota: int, added: int, interval: str) -> int:
    """Graduated delta for going from current_quota -> current_quota+added."""
    new_total = current_quota + added
    return PricingService.compute_price_paise(new_total, interval) \
         - PricingService.compute_price_paise(current_quota, interval)

@staticmethod
def prorated_addon_paise(current_quota: int, added: int, interval: str,
                         days_left: int, days_in_cycle: int) -> int:
    marginal = PricingService.marginal_monthly_paise(current_quota, added, interval)
    # guard against div-by-zero / clamp to [0, marginal]
    if days_in_cycle <= 0:
        return marginal
    return max(0, min(marginal, round(marginal * days_left / days_in_cycle)))
```

Notes:
- Because pricing is **graduated**, the marginal cost is a *delta of totals*, not a flat
  per-location price — `compute_price_paise` already handles the bands.
- `days_left` / `days_in_cycle` come from the Razorpay subscription's `current_start` /
  `current_end` (we store `current_end` as `ai_credits_reset_date`). Fetch
  `current_start` from Razorpay at add-time, or store it on the org.
- **Annual caveat:** for annual cycles `days_in_cycle ≈ 365`, so a mid-year add is a
  large one-time charge. Show the amount clearly before charging; optionally offer
  "add at renewal" for annual.

---

## 8. Backend — the unlock / add-location flow (Razorpay)

This is a **two-part** operation. Razorpay does not auto-prorate quantity like Stripe,
so we orchestrate it.

### 8.1 Create the prorated charge (one-time Order)
New `SubscriptionService.create_location_addon_order(...)`, modelled on
`create_topup_order` (subscription_service.py:128):
```python
amount = PricingService.prorated_addon_paise(quota, added, interval, days_left, days_in_cycle)
order = client.order.create(data={
    "amount": amount,
    "currency": "INR",
    "receipt": f"addon_org_{org_id}",
    "notes": {
        "organization_id": str(org_id),
        "type": "location_addon",
        "added": str(added),
        "location_ids": ",".join(map(str, pending_location_ids)),
    },
})
```

### 8.2 Raise the recurring amount for future cycles
After (or alongside) the one-time charge, update the subscription to the new plan so
renewals bill the new total:
```python
new_plan_id = SubscriptionService._get_or_create_plan(quota + added, interval)
client.subscription.update(org.razorpay_subscription_id, {
    "plan_id": new_plan_id,
    "schedule_change_at": "cycle_end",   # don't double-charge this cycle
    # IMPORTANT: also update notes.location_count to (quota + added) — see risk below
})
```

> **Critical subtlety:** `apply_subscription_charged` reads `location_count` from the
> **subscription notes** to grant quota + credits on every renewal
> (webhook_service.py:121). If we change the plan but leave `notes.location_count` stale,
> the next renewal will *reset quota/credits to the old number*. So the plan change MUST
> also update `notes.location_count`. Verify Razorpay's `subscription.update` accepts
> `notes`; if not, store the authoritative location_count on the org and have
> `apply_subscription_charged` prefer the org value over notes.

### 8.3 Apply the unlock on payment
Extend `WebhookService._handle_payment_captured` (webhook_service.py:182) to handle
`notes.type == "location_addon"` (today it only handles `topup`):
```python
if notes.get("type") == "location_addon":
    added = int(notes.get("added", "0"))
    loc_ids = [int(x) for x in notes.get("location_ids", "").split(",") if x]
    org.location_quota += added
    org.monthly_ai_credits_balance += added * plan_config.CREDITS_PER_LOCATION  # full grant
    db.query(Location).filter(Location.id.in_(loc_ids)).update(
        {Location.billing_status: "active"}, synchronize_session=False)
    # then enqueue the deferred review/attribute/insight sync for loc_ids
    # record a BillingTransaction(transaction_type="location_addon")
```
Mirror this in a `reconcile_location_addon_payment` safety-net (like
`reconcile_topup_payment`, subscription_service.py:183) for missed webhooks.

### 8.4 Idempotency
Reuse the existing `BillingTransaction.razorpay_payment_id` dedupe guard
(webhook_service.py:198) so a re-delivered webhook + reconcile can't unlock twice or
double-grant credits.

---

## 9. API endpoints

`backend/app/api/billing.py`:
- `GET /billing/pending-locations` → list locked locations + the prorated quote to
  unlock them (count, amount_paise, days_left).
- `POST /billing/locations/unlock` → body `{ location_ids: [...] }`; validates the
  locations belong to the org and are `pending_payment`, creates the addon order (§8.1),
  schedules the plan change (§8.2), returns the Razorpay order for checkout.
- Existing return-from-checkout reconcile path extended to also reconcile addon payments.

`GET /billing/me` (billing.py:160) → already returns `location_quota`; add
`active_location_count` and `pending_location_count`.

---

## 10. Frontend

- **Locations list** (`frontend/app/dashboard/locations`): render `pending_payment`
  locations with a distinct "Locked / Pending payment" badge and disabled actions.
- **Banner** (`components/billing/BillingBanners.tsx`): "N locations are pending payment —
  unlock for ₹X" with a CTA opening an unlock modal.
- **Unlock modal** (new, or extend `TopUpModal`/`UpgradeModal`): shows prorated amount and
  days remaining, runs Razorpay checkout against the addon order, then polls
  `GET /billing/me` until quota/active count updates.
- **`useBilling` hook**: expose `active_location_count`, `pending_location_count`, and an
  `unlockLocations` mutation.
- Homepage pricing copy already says "pay only for the locations you manage" — this work
  makes that literally true; no copy change required.

---

## 11. Edge cases & risks

1. **Stale subscription notes on plan change** — §8.2. Highest-risk item: get this wrong
   and renewals silently reset quota/credits. Prefer storing authoritative
   `location_count` on the org and reading it in `apply_subscription_charged`.
2. **Trial orgs.** During trial, `quota = TRIAL_LOCATION_QUOTA (5)`. New locations beyond
   5 lock as `pending_payment`; they unlock when the org subscribes at a higher count
   (the `subscription.charged` flow already sets quota). The unlock-via-addon flow assumes
   an existing active subscription — for trial users the path is "subscribe", not "addon".
   Handle both: if no active subscription, route to checkout instead of addon order.
3. **Concurrent syncs** assigning the same active slots — reuse the existing Redis
   `lock:add_location:{org_id}` pattern around the active-count read+insert.
4. **Over-quota grandfathered orgs** — by design they keep all active locations; the gate
   only blocks *new* detections. No retroactive charge.
5. **Removed/disappeared locations.** If Google stops returning a location, we currently
   keep the row. Decide later whether quota frees up; out of scope here.
6. **Annual proration size** — §7. Large one-time charge; surface clearly.
7. **Razorpay test coverage** — proration + plan-change should be validated against
   Razorpay test mode before launch.

---

## 12. Testing

Extend `backend/tests/test_billing_fixes.py`:
- New location inserted **under** quota → `active`, enqueued for sync.
- New location inserted **at/over** quota → `pending_payment`, NOT enqueued.
- Grandfather: existing rows backfilled `active`; over-quota org keeps all active.
- `marginal_monthly_paise` across band boundaries (4→5, 10→11, 25→26).
- `prorated_addon_paise` mid-cycle, start-of-cycle, end-of-cycle, div-by-zero guard.
- `location_addon` payment.captured → quota bumped, locations flipped active, full
  credits granted, idempotent on re-delivery.
- Locked location → AI reply / post / edit endpoints return 402.

---

## 13. Rollout order

1. Migration (column + index + backfill) — safe, additive, grandfathers everyone.
2. Sync-task enforcement (§5) + downstream gating (§6) — quota now enforced; new
   over-quota locations lock. (No payment flow yet → they just stay locked.)
3. Proration pricing (§7) + addon order + webhook unlock (§8) + endpoints (§9).
4. Frontend unlock UX (§10).
5. Razorpay test-mode validation, then enable in production.

Steps 1-2 stop the revenue leak immediately; 3-5 add the monetised unlock path.
