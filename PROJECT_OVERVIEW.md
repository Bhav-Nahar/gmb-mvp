Last Updated: 2026-06-12T17:18:00Z
Based On Commit: f0ed7ac
Documentation Version: 1.1

# Project Overview

* **Project Name:** GMB MVP (Google Business Profile MVP)
* **Purpose:** A unified dashboard to manage Google Business Profile (GBP) locations, synchronize location data, track performance metrics, manage custom attributes, view/reply to reviews, and manage billing plans.
* **Business Goals:** Allow organizations to easily connect their Google accounts, manage their GBP presence, respond to reviews with AI assistance, track SLA commitments, monitor analytics, update business profiles, publish localized updates, and scale their organization with flexible location-based billing subscription plans.
* **Problem Being Solved:** The difficulty of managing multiple Google Business Profile locations, reviews, attributes, insights, and posts natively at scale while enforcing fair usage limits and tiered pricing.
* **Target Users:** Organizations and businesses managing one or more physical locations.
* **Current Status:** MVP phase with location sync, AI replies, sentiment tagging, SLA tracking, post scheduling, analytics tracking, business attributes, listing moderation, and a fully integrated Razorpay-based billing & subscription system.
* **Key Features:**
  * **Multi-tenant & RBAC Isolation:** Multi-tenant organization support and explicit user-level location access control (RBAC scoping).
  * **Google OAuth Onboarding:** Seamless Google account connection and secure token persistence.
  * **Location & Review Sync:** Background synchronization of location details and reviews with normalized star ratings.
  * **AI Replies & Sentiment Tagging:** AI-assisted review replies (based on tone matching) and automated sentiment and issue classification.
  * **SLA Tracking:** SLA tracking for review response times with custom response tiers and opt-in boundaries.
  * **GBP Local Posts & Campaigns:** Bulk scheduling, multi-location campaigns, and adaptive jitter pacing.
  * **Daily Performance Insights:** Automatic extraction and tracking of GBP business performance analytics (e.g. search views, maps views, website clicks).
  * **Dynamic Business Attributes:** Dynamic synchronization of platform-specific categories, amenities, attributes, metadata, and rejections.
  * **Listing Profile Moderation:** Granular field-level updates to location profiles utilizing a moderation state machine.
  * **Subscription Billing & Location Quota Enforcement:** Tiered, graduated pricing integrated with Razorpay. Includes location quota limits, automatic grandfathering of pre-existing locations, mid-cycle proration calculations, immediate AI credit adjustments, and secure webhook event parsing with idempotency tracking.

---

# Architecture

The system follows a standard Client-Server architecture with a background worker component for asynchronous data synchronization.

* **Major Architectural Patterns:**
  * **Provider Abstraction Layer:** Third-party integrations (like Google Business Profile) inherit from an abstract `BaseProvider`, standardizing data models (`LocationModel`, `ReviewModel`).
  * **LLM Provider Factory:** AI engines (e.g., Groq/OpenAI) use a swappable factory pattern (`BaseLLMProvider`).
  * **Billing Service Layer:** Encapsulates Razorpay API client logic, subscription billing cycles, prorated calculations for location quota adjustments, credit balance refills, and webhook ingestion using Postgres transaction locks.
  * **Background Processing:** Celery tasks handle long-running operations like API synchronization, insight harvesting, AI tagging, and billing/credit balance checks.

* **Application Lifecycle:**
  * 1. Frontend sends requests to the FastAPI backend.
  * 2. Backend authenticates via JWT, validates multi-tenant (`organization_id`) and RBAC location-level access.
  * 3. API interacts with the database or enqueues a Celery task.
  * 4. Celery workers communicate with external APIs (Google, Groq, Razorpay) using rate-limited, jitter-paced HTTP clients.

* **Event Flow (Async Processing):**
  * 1. User triggers a sync, schedules a post, or requests an attribute edit.
  * 2. Celery task is enqueued.
  * 3. Redis distributed locks prevent concurrent overlaps.
  * 4. Progress is tracked in `sync_logs` or `publish_jobs`.
  * 5. Payments and plan updates are processed asynchronously via Razorpay webhooks, which update subscription states and adjust location quotas.

---

# Technology Stack

## Languages
* Python (Backend)
* TypeScript (Frontend)

## Frameworks
* **Backend:** FastAPI
* **Frontend:** Next.js (App Router), Tailwind CSS

## Libraries
* **Backend:** SQLAlchemy 2.0, Celery, Pydantic, Alembic, httpx
* **Frontend:** React Query, shadcn/ui, lucide-react

## Databases
* PostgreSQL 15 (Primary relational store)
* Redis (Distributed locks, Celery broker, state aggregations)

## Infrastructure
* Docker & Docker Compose

## External Services
* Google Business Profile API
* Groq (LLM provider for AI features)
* Razorpay (Payment Gateway & Subscriptions)

## Third-Party Integrations
* **Google OAuth 2.0:** Used for onboarding and obtaining offline refresh tokens.
* **Google Business Profile (GBP):** Fetching reviews, locations, performance metrics, business attributes, and publishing posts.
* **Razorpay:** Processing user payments, managing subscription plans, checking active subscriptions, and ingesting secure webhooks.

---

# Monorepo Structure

The repository contains two main subprojects that communicate over HTTP REST:

* **backend:** The Python/FastAPI service. Runs on port 8000. Handles business logic, database connections, background tasks.
* **frontend:** The TypeScript/Next.js application. Runs on port 3000. Consumes the backend API.

project/
├── backend/
│   ├── alembic/        # Database migrations
│   ├── app/            # FastAPI application source
│   ├── Dockerfile      # Backend and worker container definition
│   └── requirements.txt
├── frontend/
│   ├── app/            # Next.js App Router pages
│   ├── components/     # UI Components (shadcn/ui)
│   ├── lib/            # Client-side API utilities
│   └── package.json
└── docker-compose.yml  # Local development infrastructure

---

# Core Modules

## backend/app/api
* **Purpose:** HTTP endpoints definition.
* **Responsibilities:** Route handling, dependency injection (auth), input validation via Pydantic. Key endpoints include:
  * `auth.py`: Onboarding and credentials
  * `locations.py`: Location management
  * `reviews.py`: Review listing, replies, and sentiment retagging
  * `posts.py`: GBP campaigns, variants, and scheduling
  * `insights.py`: Performance insights retrieval
  * `dynamic_attributes.py`: Business attribute retrieval and management
  * `listing_edits.py`: Location details modification and moderation
  * `media.py`: Photo/video assets validation and upload
  * `billing.py`: Razorpay subscriptions creation, addon billing, proration pricing, and webhook handling

## backend/app/core
* **Purpose:** Core application configurations.
* **Responsibilities:** Environment variable loading, security (encryption/decryption), JWT utilities, authorization scoping (RBAC and IDOR protection), and `plan_config.py` defining billing features, tiers, and limits.

## backend/app/models & backend/app/schemas
* **Purpose:** Data representation.
* **Responsibilities:** SQLAlchemy models map to PostgreSQL tables; Pydantic schemas validate API requests and responses.

## backend/app/providers
* **Purpose:** External API integrations.
* **Responsibilities:** Abstracted classes to communicate with Google Business Profile APIs, including rate-limit handling and data mapping.

## backend/app/services
* **Purpose:** Business logic execution.
* **Responsibilities:**
  * `insight_sync_service.py`: Fetches and processes GBP metrics.
  * `attribute_sync_service.py`: Syncs categories and business attributes.
  * `listing_edit_service.py`: Manages profile edits and state transitions.
  * `review_sync_service.py`: Handles review pagination, rate-limiting, and upserts.
  * `ai_reply_service.py` & `sentiment_service.py`: Runs LLM-based interactions.
  * `post_service.py`: Handles campaigns and post publishing.
  * `invite_service.py`: Handles secure organization signup flows.
  * `billing/`: Sub-module with pricing calculations (`pricing_service.py`), entitlement validations (`entitlement_service.py`), credit allocation (`credit_service.py`), subscription lifecycles (`subscription_service.py`), and webhook events processing (`webhook_service.py`).

---

# Data Flow

1. **Google OAuth Flow:** User authenticates on frontend -> Backend exchanges code for tokens -> Tokens encrypted and stored in `oauth_accounts`.
2. **Review Sync & Quota Enforce Flow:** Celery beats/API triggers sync -> Backend fetches locations from GBP -> Checks if organization exceeds its location quota. Pre-existing locations are grandfathered (`active`). Excess new locations are saved as `'pending_payment'`. Reviews are synced only for active locations.
3. **AI Reply Flow:** User clicks "Generate Reply" -> Entitlement service checks location status and credit balance -> `ai_reply_service.py` crafts prompt -> LLM returns draft -> User approves -> Backend updates GBP API -> DB updated.
4. **Insights Harvest Flow:** Celery beat schedules metrics retrieval -> `insight_sync_service.py` filters by `billing_status == 'active'` and fetches analytics -> Stored in `location_daily_insights`.
5. **Subscription Upgrade / Addon Flow:** User chooses to unlock locked location -> Pricing service computes prorated charge for the remaining cycle days -> Frontend creates Razorpay order/addon -> Razorpay webhook captures payment -> Organization quota increases -> Locations set to `active`.

---

# Database Documentation

## Database Type
PostgreSQL 15

## Important Tables
* `organizations`: Multi-tenant boundary. Holds subscription details (billing plan, status, reset dates, quotas, and credit balances).
* `users`: System accounts, linked to organizations.
* `oauth_accounts`: Encrypted third-party tokens.
* `locations`: Synchronized GBP locations. Includes `billing_status` ('active', 'pending_payment') to enforce quota gates.
* `user_location_access`: RBAC map defining user-level access to specific locations.
* `reviews`: Synchronized customer reviews.
* `sync_logs`: Audit and progress tracking for async jobs.
* `post`, `post_variant`, `publish_job`: Structures for managing and tracking GBP local posts.
* `location_daily_insights`: Daily metric counts for search, maps, calls, etc.
* `location_edit`: State machine records for profile updates.
* `gbp_attribute_definition`, `gbp_attribute_metadata`, `gbp_location_attribute_rejection`: Storage for dynamic attributes.
* `activity_log`, `activity_log_archive`: Persistent operational audit logs.
* `razorpay_plans`: Available billing plans and pricing templates.
* `billing_transaction`: Log of all processed payment transactions and subscription operations.
* `billing_webhook_event`: Event log with status checking to ensure idempotent processing of webhook payloads.

## Relationships
* Users belong to Organizations.
* Locations belong to Organizations.
* `user_location_access` maps Users to specific Locations.
* Reviews, insights, and attributes belong to Locations.
* Posts generate PostVariants that belong to Locations.
* Transactions and webhook logs reference Organizations.

## Migrations
Managed by Alembic. Run `alembic upgrade head` before starting workers to prevent schema mismatch.

---

# Configuration

## Environment Variables

| Variable | Purpose | Required |
| -------- | ------- | -------- |
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `REDIS_URL` | Redis connection string | Yes |
| `JWT_SECRET` | Secret for signing auth tokens | Yes |
| `ENCRYPTION_KEY` | Secret for encrypting OAuth tokens | Yes |
| `GOOGLE_CLIENT_ID` | OAuth Client ID | Yes |
| `GOOGLE_CLIENT_SECRET`| OAuth Client Secret | Yes |
| `GROQ_API_KEY` | LLM provider key | Yes |
| `RAZORPAY_KEY_ID` | Razorpay API key ID for authenticating payments | Yes |
| `RAZORPAY_KEY_SECRET` | Razorpay API key secret | Yes |
| `RAZORPAY_WEBHOOK_SECRET` | Secret hash to verify Razorpay webhook signature integrity | Yes |

---

# Build, Test & Deployment

## Local Development Setup
Run `docker-compose up` to start all services (db, redis, backend, celery_worker, celery_beat, frontend).

## Build Process
Docker Compose builds the backend from `backend/Dockerfile` and the frontend from `frontend/Dockerfile`. Note: backend and Celery workers share the same Dockerfile.

## Test Process
`pytest` is available for backend testing.
Command: `pytest` inside the backend container.
Billing tests can be run via: `pytest backend/tests/test_billing_fixes.py`

---

# Coding Standards

* **Architecture:** Provider patterns for all external APIs. Service layer encapsulating billing calculations.
* **Security:** Use `app.core.authorization` validators (e.g., `validate_location_access()`) to prevent IDOR vulnerabilities. Enforce billing access control on all paid endpoints.
* **Data Privacy:** Raw OAuth tokens and client payment secrets must never be logged. OAuth tokens must be encrypted at rest.
* **State Management:** Use Pydantic strings instead of Enum objects for DB state validation.

---

# Known Issues & Technical Debt

* **Quirk - CSRF Cookies:** Development frontend and backend run on different ports. API calls must use `{ credentials: 'include' }`.
* **Quirk - 429 Too Many Requests:** Google API rate limits heavily; backend handles this with jitter and exponential backoff.
* **Quirk - N+1 Queries:** Be cautious when querying relational entities in a loop; always use batch queries (`Location.id.in_(...)`).
* **Technical Debt:** Legacy accounts may have provider set to `"google"` instead of `"gbp"`. Queries must check both.
* **Webhook Idempotency:** Double checks `billing_webhook_event` table to ensure duplicate webhook triggers from Razorpay do not result in double entitlement allocation.

---

# Agent Context

## Project Rules
* Never leak raw backend exception text to the frontend.
* Always filter queries by `organization_id` to enforce strict tenant isolation.
* OAuth tokens MUST be encrypted before saving to the DB.
* Always check the `billing_status` of a location before executing any paid operations.

## Safe Refactoring Guidelines

### Safe To Change
* UI cosmetic updates in Next.js.
* Standalone service logic that doesn't modify the database schema.

### Requires Regression Testing
* **Authentication Middleware & RBAC:** Risk of IDOR or user permission leaks. Test via End-to-End auth flows.
* **Celery Background Syncs & Quotas:** High risk of lock contention or 429 storms. Test with local Redis.
* **Billing and Webhooks:** Ensure payment state changes execute cleanly under mock Razorpay triggers.

## Hidden Couplings
* `sentiment_tagged_at` in the `reviews` table is the sole signal for whether a review needs AI tagging. Setting it to NULL triggers re-processing.
* Docker build caching might skip `pip install` if not run with `--no-cache`.
* `billing_status` state transitions directly control background Celery task enrollment. Setting status to `active` immediately triggers full synchronization of pending resources.

---

# Troubleshooting

* **Missing Credentials Crash:** If `GROQ_API_KEY` is empty, `AsyncOpenAI` will crash the app. A dummy string fallback is used to allow the app to start gracefully.
* **Celery Worker Fails to Find Module:** Occurs due to shared Dockerfile caching. Run `docker-compose build --no-cache celery_worker`.
* **Invite Flow Infinite Loop:** Ensure Google OAuth requests `openid email profile` scopes.
* **Webhook Signature Failures:** Validate `RAZORPAY_WEBHOOK_SECRET` matches the secret registered in the Razorpay dashboard.

---

# Quick Start Summary

1. **Purpose:** Manage Google Business Profiles at scale.
2. **Important Folders:** `backend/app/`, `frontend/app/`.
3. **Startup Commands:** `docker-compose up`
4. **Main Entry Points:** `backend/app/main.py` (API), `frontend/app/page.tsx` (UI).
5. **Architectural Constraints:** Always use the Provider abstraction for external APIs, the LLM factory for AI features, and checks to `billing_status`/quotas before initiating paid services. Ensure database is at Alembic head before starting Celery.

---

# Documentation Coverage Report

## Fully Analyzed
* Project Overview
* Architecture
* Technology Stack
* Monorepo Structure
* Core Modules
* Data Flow
* Database Schema
* Agent Context & Known Quirks
* Razorpay Billing System

## Partially Analyzed
* Testing Strategy (Extrapolated from `.pytest_cache` and billing tests)

## Not Analyzed
* CI/CD Pipelines (No `.github/workflows` found in root)
* Detailed Endpoint Routes (Relying on high-level `AGENT_INSTRUCTIONS.md`)

## Assumptions Made
* Assumed `pytest` is the primary backend test runner.

