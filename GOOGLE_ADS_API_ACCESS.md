# Google Ads API access — checklist

> **Status:** paused pending Basic access. Decision was to hold off building the
> reporting port until the tier is granted, even though Explorer already reaches
> production at 2,880 ops/day.
>
> **Next action: Step 3 (brand verification), then Step 4 (apply for Basic).**
> Both are console work, no code. Nothing has been submitted yet — the review
> clock has not started.

Goal: let tenants link their own Google Ads account so Pinzo can read spend,
conversions and call data alongside GMB insights.

**Current tier: Explorer** — which already reaches production accounts at 2,880
operations/day. Enough to build and pilot on. Basic (15,000/day) is needed for
rollout, not for starting.

Do not apply for Standard yet — see the last section for why.

---

## What we can do at each stage

The developer token tier and OAuth verification are **different axes**. The token
controls quota; verification controls whether a tenant can grant `adwords` at all.
Rollout is gated by verification, not by Basic.

| Stage | Demo to a client | Pilot | Rollout |
|---|---|---|---|
| Explorer, Testing status | yes | yes, weekly re-auth | no |
| Basic, Testing status | yes | yes, weekly re-auth | no |
| Basic, `adwords` verified | yes | yes | yes |

**The 7-day catch:** a consent screen with External user type and *Testing*
publishing status issues refresh tokens that **expire in 7 days** whenever
non-basic scopes are involved. Every pilot tenant re-authorizes weekly. Fine for
2–3 design partners, unworkable past that.

**Run the pilot on a second Cloud project** in Testing status. Do not iterate on
ads scopes against the production consent screen that authorizes `business.manage`
for paying tenants. A developer token can serve multiple projects — the constraint
is the reverse, one token per project.

**Ordering this forces:** verification requires a demo video of the working OAuth
flow, so we cannot submit before building. Build → record → submit → roll out. The
pilot runs on Testing status by construction.

---

## Step 0 — find out what we already have (do this first)

`marketing_service.py` already calls the Google Ads API to upload offline click
conversions for Pinzo's *own* signups. That means a developer token may already
exist, and steps 1–4 may be partly done.

Already established:

- Local `.env` has **no `GOOGLE_ADS_*` vars at all** — only the GBP OAuth trio.
  `_google_ads()` hits its guard at `marketing_service.py:90` and returns
  silently, so that path has never run locally.
- **Cloud project number `385594025448`** — decoded from the `GOOGLE_CLIENT_ID`
  prefix. This is the project holding the GBP OAuth client, and the one to inspect.

Still to check:

- [ ] **Prod env** — Railway → backend service → Variables → filter `GOOGLE_ADS`.
      (Or `railway variables | grep GOOGLE_ADS`.) Looking for a non-empty
      `GOOGLE_ADS_DEVELOPER_TOKEN`. All seven vars default to `""` in
      `config.py:261-267` and the function early-returns if any of six are blank,
      so a partial set means it never fired either. Logs cannot tell you this —
      the unconfigured path returns before logging.
- [ ] **Access level** — if a token exists, <https://ads.google.com/aw/apicenter>
      on the owning manager account. Note Explorer / Basic / Standard, and whether
      an application is already pending. If `GOOGLE_ADS_LOGIN_CUSTOMER_ID` is set
      in prod, that value *is* the manager account
- [ ] **OAuth consent screen** — Cloud Console → project `385594025448` → APIs &
      Services → OAuth consent screen. Record: User type (External/Internal),
      Publishing status (In production/Testing), verification status, and whether
      `adwords` is already in the scopes list alongside `business.manage`
- [ ] **API enabled?** — same project → Enabled APIs & services → "Google Ads API"

If the token is already at Basic, skip to Step 5.

**Important distinction:** that existing use is single-tenant — our own account,
our own conversions. Touching *tenants'* ad accounts is a different posture and
is what the rest of this checklist is for.

---

## Step 1 — Google Ads manager account (MCC) — DONE

The API Center only exists on manager accounts, so the fact that we can see an
access level at all confirms the MCC exists and holds a token.

**Current state: Explorer Access.**

Explorer is not test-only — it reaches production accounts at **2,880
operations/day** (15,000 against test accounts). Basic raises that to 15,000
against production.

Two consequences:

- The existing offline conversion upload in `marketing_service.py` is fine at
  this tier. Nothing is broken.
- **We can build and pilot the reporting port today.** 2,880 ops/day covers a
  handful of tenants refreshing daily. The Basic upgrade is a scaling step, not
  a blocker — it only has to land before real rollout.

---

## Step 2 — Google Cloud project

- [ ] Decide: reuse the existing Pinzo Cloud project (the one holding the GBP
      OAuth client) or create a dedicated one
- [ ] Constraint: **one developer token per Cloud project.** A token can serve
      many projects, but a project can only use one token. If the existing
      project is already bound to the marketing-conversions token, that is fine —
      it is the same token we want
- [ ] Enable the **Google Ads API** — API Library → search "Google Ads API" → Enable
- [ ] Billing is not required

---

## Step 3 — Brand verification (the fast lane)

This is the July 7, 2026 pilot. It is optional, and it is the difference between
**a few hours** and **up to 5 business days** on the Basic access review. Do it
before submitting the token application.

In Cloud Console → APIs & Services → OAuth consent screen:

- [ ] User type is **External** (not Internal)
- [ ] Publishing status is **In production** (not Testing)
- [ ] Branding section complete: app name, support email, app logo, application
      home page, privacy policy URL, terms of service URL
- [ ] All URLs are on a domain we own and have verified in Search Console
- [ ] Click **Verify Branding** — validation is automated

The pilot only counts if the app is External *and* In production. An Internal or
Testing-status project gets the slow lane regardless.

---

## Step 4 — Apply for Basic Access (upgrade from Explorer)

At <https://ads.google.com/aw/apicenter>, signed in to the manager account.
Do Step 3 first — brand verification is what buys the hours-instead-of-days lane.

- [ ] Confirm the access level still reads **Explorer**
- [ ] **Update the API Contact Email** to a current, monitored inbox. The
      compliance team emails here and a missed reply stalls the application
- [ ] **Link all active Google Ads accounts to the manager account.** This is a
      stated prerequisite and the most common place an upgrade request stalls
- [ ] Click the dropdown next to **Access level** → **Apply for Basic Access**

The form wants company name and a **website URL that is real and functional** —
placeholder domains are auto-rejected.

Review is ~5 business days, or a few hours if brand verification is done.

### What gets applications rejected

- Website does not exist, is under construction, or is a landing page with no
  product on it
- Website makes no mention of the ads functionality being applied for. The
  reviewer looks for evidence the described tool is real — if Pinzo's site says
  nothing about Google Ads management, say so explicitly in the description and
  have a page to point at
- Contact email bounces or goes unread
- Description is vague about *whose* ad accounts the tool touches. Be direct:
  managing ad accounts on behalf of our SMB customers, who link their own accounts

---

## Step 5 — Add the `adwords` scope to the OAuth consent screen

We need `https://www.googleapis.com/auth/adwords`. It is a **sensitive** scope —
same category as the `business.manage` scope we already use for GBP.

- [ ] Add the scope to the existing consent screen
- [ ] Submit for verification as a **scope addition** on the already-verified app,
      not a new app verification

**Prerequisite:** `adwords` will not appear in the scope picker until the Google
Ads API is enabled on that Cloud project (Step 2).

**Which project:** submit on the already-verified production project
`385594025448` as a scope addition. It reuses the verified brand and domain, and
the existing `business.manage` scope keeps working throughout the review — the new
scope just cannot be requested until approved. The second Testing project stays
for building and the pilot.

### Steps

1. [ ] Enable the Google Ads API on the project if not already
2. [ ] Cloud Console → OAuth consent screen → **Data Access** → *Add or remove
       scopes* → add `https://www.googleapis.com/auth/adwords`
3. [ ] Write the scope justification — what we do with Ads data and why the scope
       is needed for that
4. [ ] Homepage on the **Search Console-verified domain** that describes the ads
       functionality, not just GMB and reviews. **We do not have this page yet.**
5. [ ] Privacy policy linked from **both** the homepage and the consent screen
6. [ ] Record the demo video (spec below)
7. [ ] Submit, then answer reviewer emails quickly — each round trip adds days

### Demo video spec — this is where submissions get rejected

- [ ] Shows the **same app** that was submitted: matching app name and branding
- [ ] Shows the **complete OAuth consent screen**, not a cut to after-consent
- [ ] Consent screen displays the **exact scopes** being requested
- [ ] Consent screen language toggled to **English** (bottom-left corner)
- [ ] **URL bar visible throughout** — hiding it is an instant rejection
- [ ] Shows end-to-end: sign-in → consent → and then **how each requested scope's
      data is actually used** in the product

Top rejection causes, in order:

1. Video does not show the OAuth consent screen workflow
2. Video does not demonstrate how each requested scope is used
3. Branding mismatch between the sign-in screen and what was submitted
4. URL bar hidden or consent screen skipped

Sensitive scopes need full OAuth verification but **not** a CASA third-party
security assessment — that is restricted scopes only (Gmail, Drive). No security
vendor, no assessment fee.

**Do not skip this.** Apps in *Testing* status are capped at 100 users; for
production, verification is required before a sensitive scope is granted at all.
Either way this blocks rollout, not the pilot.

---

## Step 6 — After approval

- [ ] Confirm the token reports Basic access in the API Center
- [ ] Basic quota is 15,000 operations/day — ample for read-only reporting across
      our location count. Track usage anyway so we see the ceiling coming
- [ ] Smoke test: `googleAds:search` against a linked test account

---

## Basic → Standard

Same place as the Basic upgrade: API Center → dropdown next to **Access level** →
**Apply for Standard Access**. What decides the difficulty is the tool category
we declare.

| Category | RMF requirement |
|---|---|
| Internal use only | none |
| **Reporting-only** | reporting features only |
| Full-service | creation + management + reporting |

Full-service RMF means campaign setup, geo/language targeting, conversion
tracking, bidding strategies (tCPA / tROAS / Maximize Conversions), budgets, ad
groups, keywords and match types; edit / pause / enable / remove across campaigns,
ads and keywords; and reporting at customer, campaign, ad, keyword and search-term
level.

**Two exemptions that matter for us:**

1. Reporting-only clients may **omit hierarchy levels they don't display** — the
   reporting port qualifies without surfacing search-term data
2. Tools built for **specific campaign types, Performance Max included**, only need
   the RMF features relevant to those types. A local-ads product doing PMax for
   store goals never has to build the Search keyword/match-type machinery

So: apply as **reporting-only** once the reporting screen is real. Re-declare if
and when we add campaign creation.

The audit is real — the API Review Team checks the tool against the declared
category and a non-compliance finding can carry fees. Declare what we actually are.

### Do we even need Standard?

Basic is 15,000 operations/day. A reporting sync that batches many locations into
a single `googleAds:search` clears a thousand-plus locations comfortably. One
query per location per metric hits the ceiling at a couple hundred.

**Query design, not headcount, decides when Standard becomes urgent.** Build the
sync batched from the start and this stays a next-year problem.

---

## Per-tenant consent — not Google approving us, but the bigger drop-off

Neither of these is an application. Both are actions the tenant has to take
inside their own accounts, and both will cost more conversions than any review:

- [ ] Tenant accepts an **MCC link invite** in their Google Ads account, or
      completes OAuth directly
- [ ] Tenant links **Google Business Profile ↔ Google Ads**. This is what makes
      location assets and store-goal Performance Max possible, and it is a
      separate action from the account link above

Design the onboarding flow around these two steps rather than treating them as
paperwork. They are the funnel.

## Conditional — only if we build audience features

**Customer Match** (uploading customer lists to build audiences) has its own
policy eligibility bar based on account history and compliance, separate from
access level. Not needed for reporting or basic campaign management.

## Reference

- Developer token: <https://developers.google.com/google-ads/api/docs/get-started/dev-token>
- Cloud project setup: <https://developers.google.com/google-ads/api/docs/oauth/cloud-project>
- Access levels + RMF: <https://developers.google.com/google-ads/api/docs/productionize/access-levels>
- Brand verification pilot (Jul 2026): <https://ppc.land/google-cuts-ads-api-review-time-to-hours-with-brand-check/>
