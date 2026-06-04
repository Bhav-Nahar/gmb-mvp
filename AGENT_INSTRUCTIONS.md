# GMB MVP - Agentic AI Context

This document is designed to provide comprehensive context about the GMB MVP project to any AI agent working on the codebase. Read this carefully to understand the architecture, tech stack, database schemas, and core workflows before making changes.

## 1. Project Overview
This project is a Minimum Viable Product (MVP) for managing Google Business Profile (GBP) locations. It allows organizations to connect their Google accounts, synchronize location data, and view aggregate ratings and reviews in a unified dashboard.

## 2. Tech Stack
- **Backend:** FastAPI (Python), SQLAlchemy, PostgreSQL, Celery, Redis.
- **Frontend:** Next.js (TypeScript), Tailwind CSS.
- **Infrastructure:** Docker Compose.

## 3. Directory Structure
```text
C:\Users\Shubham\Documents\GitHub\gmb-mvp\
├── backend\                # FastAPI Application
│   ├── alembic\            # Database migrations
│   ├── app\
│   │   ├── api\            # API Endpoints
│   │   │   ├── auth.py     # Auth & Google OAuth routes
│   │   │   ├── deps.py     # API dependencies (security, auth)
│   │   │   ├── locations.py # Location routes
│   │   │   ├── posts.py    # Posts creation, media, and launch routes [NEW]
│   │   │   ├── reviews.py  # Review listing, sync, and reply routes [NEW]
│   │   │   └── users.py    # User routes
│   │   ├── core\           # Core logic (Config, Security, GBP Client)
│   │   ├── db\             # Database session management
│   │   ├── llm\            # Swappable LLM Provider Abstraction
│   │   │   ├── base.py     # BaseLLMProvider interface
│   │   │   ├── exceptions.py
│   │   │   ├── groq.py     # Groq provider implementation via OpenAI SDK
│   │   │   └── factory.py  # LLM provider factory
│   │   ├── models\         # SQLAlchemy Models
│   │   │   ├── invite.py
│   │   │   ├── location.py
│   │   │   ├── oauth_account.py
│   │   │   ├── organization.py
│   │   │   ├── post.py     # Core GBP Post metadata [NEW]
│   │   │   ├── post_variant.py # Per-location localized post [NEW]
│   │   │   ├── post_media.py # Post attachments [NEW]
│   │   │   ├── publish_job.py # Job state machine [NEW]
│   │   │   ├── post_audit_log.py # Append-only state transitions [NEW]
│   │   │   ├── review.py   # SQLAlchemy Review model [NEW]
│   │   │   ├── sync_log.py
│   │   │   └── user.py
│   │   ├── providers\      # External API integrations (e.g. Google Business Profile)
│   │   │   ├── base\       # Abstract BaseProvider and standardized models
│   │   │   │   ├── auth.py
│   │   │   │   ├── exceptions.py
│   │   │   │   ├── models.py # Standardized ReviewModel, LocationModel, etc.
│   │   │   │   └── provider.py
│   │   │   ├── gbp\        # Google Business Profile specific implementation
│   │   │   │   ├── auth.py
│   │   │   │   ├── client.py
│   │   │   │   ├── exceptions.py
│   │   │   │   ├── mapper.py # GBP Review & Location Mappers
│   │   │   │   ├── provider.py # GBP implementation of BaseProvider
│   │   │   │   └── schemas.py
│   │   │   ├── factory.py  # Provider factory
│   │   │   └── registry.py # Provider registry
│   │   ├── schemas\        # Pydantic Schemas
│   │   │   ├── invite.py
│   │   │   ├── posts.py    # Post schemas (CampaignLaunchRequest, etc.) [NEW]
│   │   │   ├── review.py   # Review schemas (ReviewResponse, ReviewReplyRequest) [NEW]
│   │   │   └── schemas.py
│   │   ├── services\       # Business logic
│   │   │   ├── ai_reply_service.py # AI-assisted review reply generator
│   │   │   ├── invite_service.py
│   │   │   ├── post_service.py # Post CRUD and transactional job creation [NEW]
│   │   │   └── review_sync_service.py # Review sync service using batch upserts [NEW]
│   │   ├── main.py         # FastAPI Entry point
│   │   ├── tasks.py        # Celery background tasks (sync_reviews_task)
│   │   └── worker.py       # Celery worker configuration
│   └── requirements.txt
└── frontend\               # Next.js Application
    ├── app\                # App Router
    │   ├── dashboard\      # Dashboard layouts and pages
    │   │   ├── reviews\    # Reviews management UI tab [NEW]
    │   │   │   └── page.tsx # Glassmorphic reviews dashboard page
    │   │   └── page.tsx
    │   ├── invite\
    │   └── login\
    ├── components\         # Shared UI components
    ├── lib\                # Client-side API utilities
    └── package.json
```

---

## 4. Architectural Conventions

### Provider Abstraction Layer
The system uses a flexible provider architecture to support multiple third-party platforms (Google, Facebook, Yelp, etc.).
- **Strategy:** All third-party integrations inherit from an abstract `BaseProvider` interface located in `backend/app/providers/base/provider.py`.
- **Mapping:** Provider-specific data (like GBP JSON responses) are mapped to standard models (`LocationModel`, `ReviewModel`) using dedicated mappers (e.g., `GBPLocationMapper`, `GBPReviewMapper`).
- **Clients:** Each provider has its own async HTTP client (e.g., `GBPAsyncClient` using `httpx`) with built-in retry logic and rate limit handling.

### LLM Provider Abstraction Layer
The application utilizes an abstract factory pattern for AI features, making LLM vendors fully swappable.
- **Strategy:** All LLM engines inherit from `BaseLLMProvider` in `app/llm/base.py`.
- **Implementations:** E.g., `GroqLLMProvider` wraps the OpenAI async SDK to communicate with Groq (`api.groq.com`).
- **Configuration:** The active provider is dynamically loaded by `get_llm_provider()` using `settings.LLM_PROVIDER`.

### Security and Data Privacy
- **Token Storage:** All OAuth tokens (Access and Refresh) are strictly encrypted before database storage using encryption utilities in `app.core.security`. Never log raw tokens.
- **Authorization:** Endpoints are protected via dependency injection (`admin_required`, `staff_required`) found in `app.api.deps`. Ensure robust multi-tenancy by verifying `organization_id` on all data requests.

---

## 5. Database Schema & Data Models

### 5.1 Relational Schema
All tables reside in a PostgreSQL database and are managed using SQLAlchemy models. The exact column structures and details are outlined below.

#### Organizations Table (`organizations` / `Organization` Model)
| Column Name | SQLAlchemy Type | Constraints | Description |
|---|---|---|---|
| `id` | `Integer` | `primary_key=True`, `index=True` | Unique Organization identifier |
| `name` | `String` | `nullable=False` | Display name of the organization |
| `created_at` | `DateTime(timezone=True)` | `nullable=False`, `server_default=now()` | Creation timestamp |

#### Users Table (`users` / `User` Model)
| Column Name | SQLAlchemy Type | Constraints | Description |
|---|---|---|---|
| `id` | `Integer` | `primary_key=True`, `index=True` | Unique User identifier |
| `email` | `String` | `nullable=False`, `unique=True`, `index=True` | User email address |
| `name` | `String` | `nullable=False` | Full name |
| `avatar` | `String` | `nullable=True` | Profile avatar URL |
| `google_id` | `String` | `nullable=False`, `unique=True`, `index=True` | External Google account identifier |
| `role` | `String` | `nullable=False`, `default="Staff"` | Access level (`"Admin"` or `"Staff"`) |
| `organization_id` | `Integer` | `ForeignKey("organizations.id", ondelete="CASCADE")`, `nullable=False` | Multi-tenancy parent key |
| `created_at` | `DateTime(timezone=True)` | `nullable=False`, `server_default=now()` | Creation timestamp |

#### OAuth Accounts Table (`oauth_accounts` / `OAuthAccount` Model)
| Column Name | SQLAlchemy Type | Constraints | Description |
|---|---|---|---|
| `id` | `Integer` | `primary_key=True`, `index=True` | Unique OAuth account identifier |
| `user_id` | `Integer` | `ForeignKey("users.id", ondelete="CASCADE")`, `nullable=False` | Owner's User identifier |
| `provider` | `String` | `nullable=False`, `default="google"` | OAuth provider identifier |
| `provider_account_id` | `String` | `nullable=False`, `index=True` | External provider user ID |
| `access_token` | `String` | `nullable=False` | **Encrypted** access token |
| `refresh_token` | `String` | `nullable=True` | **Encrypted** refresh token |
| `expires_at` | `DateTime(timezone=True)` | `nullable=False` | Access token expiration timestamp |
| `created_at` | `DateTime(timezone=True)` | `nullable=False`, `server_default=now()` | Creation timestamp |

#### Locations Table (`locations` / `Location` Model)
| Column Name | SQLAlchemy Type | Constraints | Description |
|---|---|---|---|
| `id` | `Integer` | `primary_key=True`, `index=True` | Unique Location identifier |
| `organization_id` | `Integer` | `ForeignKey("organizations.id", ondelete="CASCADE")`, `nullable=False` | Multi-tenancy parent key |
| `google_location_id` | `String` | `nullable=False`, `index=True` | External location identifier (e.g. `locations/123`) |
| `location_name` | `String` | `nullable=False` | Display name of the location |
| `primary_category` | `String` | `nullable=True` | Main business category |
| `address` | `String` | `nullable=True` | Combined address lines |
| `phone` | `String` | `nullable=True` | Primary phone number |
| `website` | `String` | `nullable=True` | Website URL |
| `average_rating` | `Float` | `nullable=True` | Aggregate score (1.0 to 5.0) |
| `total_reviews` | `Integer` | `nullable=True` | Total number of reviews synced |
| `sync_status` | `String` | `nullable=False`, `default="Pending"` | Sync state (`"Pending"`, `"Synced"`, `"Failed"`) |
| `last_synced_at` | `DateTime(timezone=True)` | `nullable=True` | Timestamp of last success sync |
| `sla_tracking_started_at` | `DateTime(timezone=True)` | `nullable=True`, `index=True` | Opt-in timestamp for SLA tracking |
| `created_at` | `DateTime(timezone=True)` | `nullable=False`, `server_default=now()` | Creation timestamp |

#### Sync Logs Table (`sync_logs` / `SyncLog` Model)
| Column Name | SQLAlchemy Type | Constraints | Description |
|---|---|---|---|
| `id` | `Integer` | `primary_key=True`, `index=True` | Unique log entry identifier |
| `organization_id` | `Integer` | `ForeignKey("organizations.id", ondelete="CASCADE")`, `nullable=False` | Multi-tenancy key |
| `location_id` | `Integer` | `ForeignKey("locations.id", ondelete="SET NULL")`, `nullable=True` | Linked Location (null if org-wide sync) |
| `status` | `String` | `nullable=False` | Log outcome state (`"Success"` or `"Failed"`) |
| `error_message` | `Text` | `nullable=True` | Detailed status message or traceback if failed |
| `run_type` | `String` | `nullable=False`, `default="Scheduled"` | Sync initiator type (`"Scheduled"` or `"Manual"`) |
| `created_at` | `DateTime(timezone=True)` | `nullable=False`, `server_default=now()` | Sync log execution timestamp |

#### Reviews Table (`reviews` / `Review` Model)
| Column Name | SQLAlchemy Type | Constraints | Description |
|---|---|---|---|
| `id` | `Integer` | `primary_key=True`, `index=True` | Local unique database primary key |
| `organization_id` | `Integer` | `ForeignKey("organizations.id", ondelete="CASCADE")`, `index=True`, `nullable=False` | Multi-tenancy isolation key |
| `location_id` | `Integer` | `ForeignKey("locations.id", ondelete="CASCADE")`, `index=True`, `nullable=False` | Foreign key to the local location |
| `provider` | `String` | `nullable=False` | External platform identity (e.g. `"gbp"`) |
| `provider_review_id` | `String` | `index=True`, `nullable=False` | Third-party platform review ID |
| `reviewer_name` | `String` | `nullable=False` | Display name of the author |
| `reviewer_profile_photo` | `String` | `nullable=True` | URL to author's avatar/photo |
| `rating` | `Integer` | `nullable=True` | Standardized star rating (`1-5` scale, `None` if unspecified) |
| `comment` | `Text` | `nullable=True` | Textual content of the review |
| `is_replied` | `Boolean` | `nullable=False`, `default=False` | Flag indicating if a reply has been posted |
| `reply_text` | `Text` | `nullable=True` | Textual content of the reply |
| `reply_created_at` | `DateTime(timezone=True)` | `nullable=True`, `index=True` | Timestamp when the first reply was created |
| `review_created_at` | `DateTime(timezone=True)` | `nullable=False` | Original review timestamp from provider |
| `review_updated_at` | `DateTime(timezone=True)` | `nullable=True` | Last modification timestamp from provider |
| `raw_payload` | `JSONB` | `nullable=True` | Entire unmapped JSON structure for historical auditing |
| `created_at` | `DateTime(timezone=True)` | `nullable=False`, `server_default=now()` | Local database insertion timestamp |
| `updated_at` | `DateTime(timezone=True)` | `nullable=False`, `server_default=now()`, `onupdate=now()` | Local database record update timestamp |
| `is_deleted` | `Boolean` | `nullable=False`, `default=False` | Soft deletion status flag |
| `deleted_at` | `DateTime(timezone=True)` | `nullable=True` | Soft deletion timestamp |
| `sentiment` | `String` | `nullable=True`, `index=True` | AI-tagged sentiment classification |
| `issue_category` | `String` | `nullable=True`, `index=True` | AI-tagged issue category classification |
| `sentiment_tagged_at` | `DateTime(timezone=True)` | `nullable=True` | Timestamp when AI sentiment tagging completed successfully (used as the processing signal) |

**Table Constraints & Indices:**
- **Unique Constraint (`uq_review_provider_id`):** Enforces a combination of `(provider, provider_review_id)` to prevent duplicating reviews.
- **Sorted Composite Index (`idx_reviews_location_created_at_desc`):** Defined over `(location_id, review_created_at DESC)` for O(1) page lookups on sorting.
- **SLA Optimizations:** Includes `ix_reviews_sla_lookup` covering `(organization_id, location_id, is_deleted, is_replied, review_created_at)` to support rapid SLA grouping and time-based filtering.

#### GBP Local Posts Foundation (New in Phase 1)
- **`Campaign`**: Aggregates multi-location post deployments and tracks success/failure metrics.
- **`Post`**: The canonical representation of the post metadata (`title`, `summary`, `post_type`, `cta_url`) before localization.
- **`PostVariant`**: Links a `Post` to a specific `Location`, storing computed text/URLs after substituting per-location variables. Unique constraint on `(post_id, location_id)`.
- **`PostMedia`**: Handles attachments (Photos/Videos) with `sha256_hash` for deduplication.
- **`PublishJob`**: Represents the state machine for the physical delivery of a variant to GBP (`PENDING`, `RUNNING`, `SUCCESS`, `FAILED`).
- **`PostAuditLog`**: Append-only log capturing all status changes for compliance and debugging.

#### Listing Profile Edits & Activity Log (New)
- **`LocationEdit`**: Tracks granular field-level edits to locations (e.g. `businessHours`, `description`). Implements a state machine (`Draft`, `Pending`, `Approved`, `Publishing`, `Published`, `Failed`, `Rejected`). Supports granular versioning, warnings, and retry attempts.
- **`ActivityLog`**: A centralized, append-only log capturing all operational and entity-level activity (e.g. "Location created", "Review Replied"). Links to `organization_id`, `location_id`, and `actor_user_id`.

---

### 5.2 Abstraction Layer Data Models
External provider payloads are strictly mapped to normalized Pydantic objects before entering business logic layers.

#### Standardized `ReviewModel` (`app/providers/base/models.py`)
```python
class ReviewModel(BaseModel):
    id: str                        # External review identifier
    location_id: str               # External location identifier
    reviewer_name: str             # Author name
    reviewer_profile_photo: Optional[str] = None
    rating: Optional[int] = None   # Standardized 1-5 integer scale
    body: Optional[str] = None     # Review body comment
    reply: Optional[str] = None    # Text of reply (if already replied)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    provider: str                  # e.g., "gbp"
    provider_metadata: Dict[str, Any] = {} # Whole raw payload stored here
```

---

## 6. Core Workflows

### 6.1 Google OAuth & Onboarding
1. Frontend calls `/api/v1/auth/google/login` to obtain the OAuth consent URL.
2. User authenticates with Google, which redirects to `/api/v1/auth/google/callback`.
3. Backend exchanges the authorization `code` for an `access_token` and `refresh_token`.
4. Tokens are securely encrypted and saved in the `oauth_accounts` table. User is attached to an Organization.

### 6.2 Location Synchronization (Background Sync)
- **Execution:** Triggered via scheduled Celery tasks (`sync_all_organizations_task`) or manually via API endpoints.
- **Process:**
  1. A background task is enqueued for a specific organization.
  2. A **Redis Distributed Lock** is acquired to prevent concurrent overlapping sync tasks for the same organization (`lock:sync_all:{organization_id}`). If a lock is already held, the task gracefully skips execution.
  3. A `SyncLog` entry is immediately created in the `Pending` state to track real-time sync progress.
  4. Encrypted tokens are decrypted. Expired access tokens are refreshed using the `refresh_token`.
  5. The specific provider instance (e.g., `GBPProvider`) fetches accounts, locations, and aggregate rating/review counts. Locations are only processed if their metadata indicates they are verified (e.g., `hasVoiceOfMerchant`).
  6. Data is mapped to standard schemas (`LocationModel`) and bulk upserted into the local `locations` table.
  7. The `Pending` `SyncLog` is updated to `Success` upon completion, or `Failed` (with full exception details in `error_message`) if an error is caught.

### 6.3 Review Synchronization & Replies
Reviews are kept in sync continuously using Celery background tasks or manual client requests.

#### 1. Background Polling & Fetching (Pagination & Quotas)
- **Trigger:** Scheduled celery task (`sync_reviews_task` for a specific location) or a manual sync API request.
- **Concurrency Control:** Acquires a **Redis Distributed Lock** (`lock:sync_reviews:{organization_id}:{location_id}`) to ensure only one sync runs per location at a time. Creates a `Pending` `SyncLog`.
- **API Page Constraints:** Google Business Profile API paginates reviews in pages. To handle large datasets, the `GBPProvider` implements pagination:
  - Fetches in batches of `pageSize = 50`.
  - Loops continuously checking for a returned `nextPageToken` and passes it back via the `pageToken` parameter until exhausted.
- **API Rate Limiting & Resilience:**
  - Google enforces rigorous quota limits. Retries and backoffs are isolated in `GBPAsyncClient` (`backend/app/providers/gbp/client.py`).
  - Intercepts **`429 (Too Many Requests)`** responses and applies a **5-attempt exponential backoff retry mechanism**:
    `delay = base_delay * (2 ** attempt)` (starting at 1.0 seconds).
  - Intercepts standard network/socket errors, performing a full retry up to 5 times.
- **Processing:** Once all location reviews are fetched, the `ReviewSyncService` receives `List[ReviewModel]`, chunks them into batches of 500, and performs a PostgreSQL `ON CONFLICT DO UPDATE` bulk upsert matching the `uq_review_provider_id` constraint. Stale soft-deleted reviews are automatically restored if they still reside in Google's API payload.
- **Error Surfacing:** Updates the `Pending` `SyncLog` to `Success` or `Failed`. If failed, the raw error is stored in `error_message` for the frontend to consume.

#### 2. Star Rating Normalization
- **Mapping Layer:** Standardizing string ratings to integer scales happens exclusively inside the mapper layer: `GBPReviewMapper` (`backend/app/providers/gbp/mapper.py`).
- **Standardization logic:**
  Google My Business API represents reviewer scores as string constants (`"FIVE"`, `"FOUR"`, `"THREE"`, `"TWO"`, `"ONE"`, or `"STAR_RATING_UNSPECIFIED"`). The mapper standardizes these via a static lookup dictionary:
  ```python
  star_map = {
      "FIVE": 5,
      "FOUR": 4,
      "THREE": 3,
      "TWO": 2,
      "ONE": 1,
      "STAR_RATING_UNSPECIFIED": None
  }
  ```
  This guarantees that all core services, dashboards, and aggregates operate on a normalized integer scale (`1 to 5` stars).

#### 3. Review Replies & Local State Updates
- **Process:**
  1. A dashboard user inputs text and clicks "Send Reply" in the frontend.
  2. The frontend triggers a `POST` request to `/api/v1/reviews/{id}/reply` with `reply_text`.
  3. The API validates organization ownership of the review, resolves the correct provider instance via `ProviderFactory`, and calls `provider.reply_review(review.provider_review_id, payload.reply_text)`.
  4. The provider uses the async client to execute a `PUT` request targeting:
     `https://mybusiness.googleapis.com/v4/{accountName}/{locationName}/reviews/{reviewId}/reply`
  5. Upon a successful response from Google, the backend updates the **local state fields** on the matching `Review` database record:
     - **`is_replied`** is set to `True`
     - **`reply_text`** is populated with the posted text
     - **`review_updated_at`** is set to `datetime.utcnow()` (reflecting the local time the reply transaction completed)
     - **`updated_at`** is automatically updated via database triggers (`onupdate=func.now()`)
  6. The updated database record is returned to the frontend as a `ReviewResponse` to trigger an instant reactive UI render.

#### 4. Frontend Real-Time Sync Monitoring (Polling)
- The Next.js dashboard uses a dynamic real-time polling mechanism to display sync states.
- When a location or review sync is triggered, the frontend polls the `GET /api/v1/locations/{location_id}/sync-status` endpoint every 3 seconds.
- Badges dynamically update to reflect states: `Checking...` (initial), `Syncing...` (yellow spinner for `Pending`), `Failed` (red badge with error details and retry button), and `Success` (green badge displaying relative time since last sync).

### 6.4 Invitation System
1. Admin user sends an email invitation.
2. `InviteService` generates a cryptographically secure token and stores it in the `invites` table.
3. The invited user follows the link: `/invite/[token]`.
4. Upon sign-up, the user is joined to the inviter's organization.

### 6.5 AI-Assisted Review Replies
- **Trigger:** Dashboard user clicks "Generate Reply" on a review.
- **Tone Mapping:** The `ai_reply_service.py` infers an appropriate tone based on the original review's star rating (Grateful for 4-5 stars, Professional for 3, Empathetic for 1-2).
- **Security:** To defend against prompt injection attacks, the original review text is truncated to 2000 characters and strictly wrapped in `<review>` XML elements before being injected into the prompt.
- **LLM Call:** The abstract LLM provider calls the vendor (e.g., Groq) and returns the generated text.
- **Frontend Interaction:** The generated text populates an editable textarea alongside a dynamic word-count tracker and an AI tone badge. The user can manually refine the AI draft before finalizing via the `POST /api/v1/reviews/{id}/reply` endpoint.

### 6.6 AI Sentiment Tagging for Reviews
- **Trigger:** Enqueued asynchronously after a successful location review sync (`tag_reviews_sentiment_task`), or manually triggered via `/api/v1/locations/{location_id}/retag-sentiment`.
- **Locking:** Uses a Redis Distributed Lock (`lock:sentiment_tag:{organization_id}:{location_id}`) to prevent overlapping runs for the same location.
- **Processing Signal:** The `sentiment_tagged_at` column in the `reviews` table acts as the *sole signal* for whether a review needs processing. If `NULL`, it requires tagging. The manual retag endpoint simply sets this back to `NULL` for all non-deleted reviews of a location and triggers the task.
- **Classification:** Reviews are processed in batches (default 5) via `SentimentService`. The system prompt instructs the LLM to output a strict JSON array assigning a sentiment (e.g., `Positive`, `Negative`) and an issue category (e.g., `Staff Praise`, `Service Issue`). The allowed labels have a single source of truth in `app/constants/review_sentiment.py`.
- **Error Resilience:** Uses `temperature=0.1` for consistency. Individual JSON item failures (e.g., invalid label or missing ID) do not fail the entire batch. If the response isn't parseable as JSON, the batch is safely skipped.

### 6.7 SLA Tracking & Metrics
- **Opt-in Design:** Locations must explicitly opt-in to SLA tracking to avoid artificially punishing locations with years of historical, unanswered reviews. Opting in sets `sla_tracking_started_at`.
- **Time Constraints:** SLA computations (in `sla_service.py`) and API filtering (`reviews.py`) STRICTLY gate calculations to only include reviews where `review_created_at >= sla_tracking_started_at`.
- **N+1 Query Avoidance:** `get_organization_sla_summary` computes metrics for all locations belonging to an organization at once by utilizing SQLAlchemy `group_by` and aggregate functions (`func.sum`, `func.avg`, `case`), completely avoiding per-location N+1 iteration.
- **Tiers:** Time cutoffs (e.g. Best < 12h, Good < 24h) are defined exclusively in `app/constants/sla.py`. Tiers dynamically categorize response speed (based on `reply_created_at` - `review_created_at`).

### 6.8 GBP Local Posts (Phase 4B: SaaS Scale & Throughput Hardening)
The posts architecture has been extensively hardened to support high-volume safe throughput, burst protection, and operational scalability.
- **Chunked Campaign Shards**: Campaigns are processed in batches (chunks of 50 locations) via `orchestrate_campaign_task` which delegates to `process_campaign_shard_task` to prevent queue congestion and database lock contention.
- **Queue Jitter & Adaptive Pacing**: Inside each shard processor, adaptive randomized jitter (e.g., 0.8s to 1.5s) is injected between sequential Google API requests to prevent ingestion spikes and `429 Too Many Requests` storms.
- **Redis Aggregate Counters & Circuit Breakers**: 
  - Campaign metrics (`success`, `failed`, `pending_shards`) are aggregated natively in Redis to bypass PostgreSQL row-lock contention. 
  - A pre-flight and mid-shard Circuit Breaker reads `campaign:{id}:status`. If a campaign is `Paused` or `Cancelled`, remaining jobs are instantly drained/aborted, allowing rapid scaling down of rogue campaigns.
- **Advanced Retry Idempotency**: Single jobs that fail transiently are retried via `process_campaign_shard_task.apply_async`. A Redis lock (`retry_registered:{job_id}:{attempt}`) guarantees jobs can never be double-registered in the queue on worker crashes.
- **Storage Abstraction Layer**: Media processing utilizes an abstract `StorageProviderFactory` supporting `local`, `s3`, and `r2`. Media payloads are entirely optional for posts. If present, background tasks (`optimize_media_task`, `generate_thumbnail_task`) handle compression before publishing.
- **Explicit Primary Post Linkage**: Campaigns strictly track their root post via `campaign.primary_post_id` as the source of truth, avoiding fragile `.order_by` heuristics.
- **Scheduled Post Polling**: A Celery beat task (`check_scheduled_posts_task`) sweeps the database for `SCHEDULED` posts whose `scheduled_at` timestamp has matured, atomically locking and converting them to `QUEUED`/`PROCESSING` campaigns.

### 6.9 Listing Profile Edits & Moderation
- **State Machine**: The `LocationEdit` model manages field updates with states: `Draft` -> `Pending` -> `Approved` -> `Publishing` -> `Published`. Staff create drafts, and Admins can approve/publish.
- **Stale Publishing Recovery**: A safety mechanism built into `list_edits` dynamically checks for edits stuck in `Publishing` for >5 minutes. If found, they are automatically marked as `Failed` with reason `"Publishing timeout: stale recovery triggered"`, preventing hanging records if a Celery worker crashes mid-publish.
- **Activity Logging**: All edits, approvals, rejections, and publications generate corresponding immutable events in the `ActivityLog` table.
- **Field Configuration**: Field permissions (e.g. `is_staff_editable`, `is_admin_editable`, `is_critical`) are controlled exclusively by `LISTING_FIELDS` constants logic.

---

## 7. Development Operations
- **Start Services:** Run `docker-compose up` to spin up the PostgreSQL, Redis, FastAPI, Next.js, and Celery worker.
- **Database Migrations:** Run `alembic upgrade head` inside the backend container to apply schema changes.
- **Background Tasks:** Monitor Celery worker execution using `docker-compose logs -f worker`. 

---

## 8. Security & Authorization Conventions

### 8.1 Centralized Authorization
- **IDOR Prevention:** Always use centralized authorization helpers located in `app/core/authorization.py`. Specifically, use `validate_location_access()` and `validate_user_access()` when dealing with location or user mutations to ensure the user has appropriate permissions within their organization.

### 8.2 Audit Logging
- **Required Fields:** All security-sensitive actions (invites, role changes, location reassignments, deactivations) must be logged in the `AuditLog` table. Ensure that both `actor_user_id` (the user performing the action) and `target_user_id` (the user being acted upon) are populated for accurate security analysis.

### 8.3 Session Invalidation
- **Token Versions:** Always increment `current_user.token_version` on **ALL** security events (e.g., user deactivation, password reset, role changes, Google account disconnection) to ensure consistent and immediate session invalidation across all active JWTs.

### 8.4 Concurrency & Locking
- **Token Refresh Thundering Herd:** Use SQLAlchemy's `with_for_update()` pessimistic row-level lock when refreshing OAuth tokens to prevent multiple workers from simultaneously refreshing the same token (e.g., in `providers/gbp/auth.py`). 
- **Future Scaling:** Do not over-engineer Redis distributed locking for this yet. Stick to the DB lock for early production and leave `# TODO` comments for future scaling if needed.

### 8.5 Error Handling & Redirects
- **Frontend Error Mapping:** Never leak or trust raw backend exception text on the frontend or in redirects. For OAuth flows (like `google_callback`), sanitize errors to generic query parameters (e.g., `?error=oauth_failed`) and map them to user-friendly messages client-side (e.g., in `frontend/app/login/page.tsx`). Log the detailed exception internally.

---

## 9. Important Bug Fixes & Known Quirks
Any new agent working on this project must be aware of these historical bug fixes to avoid re-introducing them:

### 9.1 CSRF & Cross-Origin Cookies
- **Quirk:** The Next.js frontend (`localhost:3000`) and FastAPI backend (`localhost:8000`) run on different ports in development, making cookies cross-origin.
- **Fix:** The `oauth_state` cookie is dynamically set to `secure=True` only if `FRONTEND_URL` starts with `https://`. Furthermore, all Next.js API client calls in `frontend/lib/api.ts` must use `{ credentials: 'include' }` by default to ensure the browser stores and transmits these cross-origin cookies. Do not remove this option.

### 9.2 GBP / Google Provider Mismatch
- **Quirk:** Existing legacy users might have their `OAuthAccount.provider` set to `"google"`, while the system relies on it being `"gbp"`.
- **Fix:** Provider queries in `factory.py`, `gbp/auth.py`, and `tasks.py` must ALWAYS check for both `provider.in_(["gbp", "google"])` for backward compatibility. All new insertions should exclusively use `"gbp"`.

### 9.3 Review Sync API Errors (404 NOT FOUND)
- **Quirk:** Google's API might return a 404 for a location's reviews if they are inaccessible or the location is unverified.
- **Fix:** In `GBPProvider.get_reviews`, DO NOT silently catch and swallow exceptions. Explicitly raise them so that the `ReviewSyncService` marks the background `SyncLog` task as `Failed` and surfaces the real error on the dashboard.

### 9.4 GBP Location Account Name Discovery
- **Quirk:** Fallback discovery of a location's account using the nested endpoint `accounts/{accountId}/locations/{locationId}` always returns 404 in Google Business Information API v1.
- **Fix:** Always use the standard list endpoint `accounts/{accountId}/locations` to discover if an account manages a location. After discovery, the `google_account_id` is cached in the local `locations` database table to bypass future lookups.

### 9.5 Google OAuth Scopes & Email Fallbacks
- **Quirk:** If `openid email profile` scopes are omitted, the backend cannot retrieve the user's real email, falling back to a dummy `"connected-account@google.com"`. This causes catastrophic infinite loops in the invitation system due to email mismatches.
- **Fix:** The Google OAuth login URL and GBP client MUST always request `openid email profile` scopes alongside `https://www.googleapis.com/auth/business.manage`.

### 9.6 OpenAI SDK Missing Credentials Crash
- **Quirk:** When `AsyncOpenAI` initializes, if the `api_key` evaluates to a falsy value (e.g., an empty string from `.env`), the SDK instantly crashes the application with `OpenAIError: Missing credentials`.
- **Fix:** In `groq.py` (and similar implementations), pass a fallback like `api_key=settings.GROQ_API_KEY or "dummy_key_to_prevent_crash"`. This allows the application to start safely; subsequent API calls will fail gracefully with a 401 Unauthorized, which is then caught and handled via `LLMProviderError` to return a 502 response to the client.

### 9.7 Docker Compose Environment Variable Isolation
- **Quirk:** Adding new variables (like `GROQ_API_KEY`) to the root `.env` file does not automatically expose them to Docker containers running Python code.
- **Fix:** Always explicitly inject new environment variables into the respective container's `environment:` block within `docker-compose.yml`. Without this, Pydantic's `SettingsConfigDict` might fallback to reading a non-existent or misaligned `.env` path inside the isolated container.

### 9.8 Docker Layer Caching with Shared Dockerfile
- **Quirk:** The backend and celery worker share the same `Dockerfile`. If a new dependency (e.g., `openai`) is added to `requirements.txt`, running `docker compose build celery_worker` or `docker compose up --build` might incorrectly hit a cached `pip install` layer from an earlier build that didn't include the new dependency. This leads to a `ModuleNotFoundError` inside the container at runtime.
- **Fix:** Always explicitly run `docker compose build --no-cache [service_name]` when adding new dependencies to a shared `requirements.txt` file to force a clean installation.

### 9.9 SLA Time Handling and Filter Gating
- **Quirk:** Pre-SLA historical reviews can get accidentally caught in SLA aggregations (e.g., "Overdue" metrics) if boundary conditions aren't strictly joined. Moreover, using Python's naive `datetime.utcnow()` instead of the database's `func.now()` can introduce skew and boundary errors during evaluation.
- **Fix:** All SLA time filtering strictly joins the `Location` table and filters by `review_created_at >= Location.sla_tracking_started_at`. Additionally, writing SLA-critical timestamps to the DB must universally use `func.now()` to guarantee correct PostgreSQL evaluation. The endpoint to enable SLA is also explicitly locked to `admin_required`.

### 9.10 True Atomic Batch Publishing
- **Quirk:** Looping over locations and committing per-location inside a `publish_post_to_location` method breaks transactionality. If a batch publish fails halfway through, previous locations are already committed and cannot be rolled back, leading to partial states.
- **Fix:** Split the logic into two phases. Phase 1 runs read-only pre-flight validation on all locations. Phase 2 stages flush-only ORM objects (e.g., `_stage_publish_job`) without committing. Finally, a single `db.commit()` at the endpoint level ensures the entire batch is saved or rolled back atomically. Background tasks (like Celery delays) must ONLY be dispatched *after* the successful commit loop closes.

### 9.11 Frontend FormData Authentication & Base URL Fetching
- **Quirk:** Using raw `fetch` for `multipart/form-data` uploads in Next.js bypasses the application's global API client, frequently missing the `credentials: 'include'` cookie auth, mis-prefixing the API URL path (`/api/v1/api/v1`), and manually reading from `localStorage` which might not have the token stored.
- **Fix:** Always use the centralized `api.post()` client even for file uploads. The `api` client handles base URL resolution, cookie-based authentication, and automatically strips the `Content-Type` header when detecting a `FormData` payload so the browser can accurately set the multipart boundary.

### 9.12 Enum vs String Validation in Pydantic Updates
- **Quirk:** Pydantic v2 `model_dump()` can return Enum objects (e.g., `<PostStatus.Draft>`) instead of their raw string `.value`, even if the Enum inherits from `str`. Comparing this directly against a raw database string will silently fail validation dict checks (e.g. `new_status not in allowed_transitions`).
- **Fix:** Always manually normalize status values to raw strings (e.g., `new_status.value if hasattr(new_status, "value") else str(new_status)`) before evaluating state machine transition rules (`_ALLOWED_PATCH_TRANSITIONS`).

### 9.13 N+1 Query in Bulk Jobs Endpoint
- **Quirk:** Querying relational entities sequentially within a mapping loop (e.g., `db.query(Location).filter(id==job.location_id).first()` inside a `for job in jobs` loop) scales linearly and bogs down the database.
- **Fix:** Pre-aggregate all unique foreign keys (e.g., `location_ids`) and execute a single batch query (`Location.id.in_(location_ids)`). Build a Python dictionary lookup table before running the O(N) mapping loop in memory.

---

## 10. AI Agent Guidelines for this Project
- Always verify provider abstraction compatibility when adding new external APIs.
- Avoid making raw requests in routes; abstract them into the `providers` package.
- Respect the existing Pydantic validation schemas in `schemas/` and keep them separate from SQLAlchemy `models/`.
- Maintain strict typing with Python type hints.
- Ensure strict tenant isolation: always filter by `organization_id` when reading or writing models.
