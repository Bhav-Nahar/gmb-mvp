# GMB MVP - Project Documentation

## Project Overview
This project is an MVP for managing Google Business Profile (GBP) locations. It allows organizations to connect their Google accounts, synchronize location data, and view aggregate ratings and reviews in a unified dashboard.

## Tech Stack
- **Backend:** FastAPI (Python), SQLAlchemy, PostgreSQL, Celery, Redis.
- **Frontend:** Next.js (TypeScript), Tailwind CSS.
- **Infrastructure:** Docker Compose.

## Directory Structure
```text
C:\Users\Shubham\Documents\GitHub\gmb-mvp\
├───backend\                # FastAPI Application
│   ├───alembic\            # Database migrations
│   ├───app\
│   │   ├───api\            # API Endpoints (Auth, Locations, Users, Reviews)
│   │   ├───core\           # Core logic (Config, Security, GBP Client)
│   │   ├───db\             # Database session management
│   │   ├───models\         # SQLAlchemy Models
│   │   ├───providers\      # Provider abstraction (GBP, Base Interfaces)
│   │   ├───schemas\        # Pydantic Schemas
│   │   ├───services\       # Business logic (e.g., Invite Service, Review Sync)
│   │   ├───main.py         # Entry point
│   │   ├───tasks.py        # Celery background tasks (Locations, Reviews)
│   │   └───worker.py       # Celery worker configuration
│   └───requirements.txt
└───frontend\               # Next.js Application
    ├───app\                # App Router (Dashboard, Login, Invites)
    ├───components\         # Shared UI components
    ├───lib\                # Client-side API utilities
    └───package.json
```

## Core Workflows

### 1. Google OAuth & Onboarding
- **Trigger:** User clicks "Connect Google Account".
- **Process:**
  1. Frontend calls `/api/v1/auth/google/login` to get the OAuth URL.
  2. User authenticates with Google.
  3. Google redirects to `/api/v1/auth/google/callback`.
  4. Backend exchanges the `code` for `access_token` and `refresh_token`.
  5. Tokens are encrypted and stored in the `oauth_accounts` table.
  6. The user's email is verified, and they are associated with an Organization.

### 2. Location Synchronization (Background Sync)
- **Trigger:** Manual trigger via API or Scheduled Celery Task (`sync_all_organizations_task`).
- **Process:**
  1. `sync_locations_task` is enqueued for a specific organization.
  2. Access token is decrypted. If expired, it is refreshed using the `refresh_token`.
  3. `GBPClient` fetches accounts and locations from the Google Business Information API.
  4. Aggregate ratings and reviews are fetched for each location.
  5. Data is "upserted" into the `locations` table.
  6. Sync results are logged in the `sync_logs` table.

### 3. Invitation System
- **Process:**
  1. Admin invites a user via email.
  2. `InviteService` generates a secure token and stores it in the `invites` table.
  3. The user receives a link: `/invite/[token]`.
  4. On acceptance, the user is registered and linked to the inviter's organization.

### 4. Review Synchronization & Management
- **Trigger:** Manual trigger via API (`/api/v1/reviews/sync`) for specific or all locations.
- **Process:**
  1. `sync_reviews_task` is enqueued for a specific location.
  2. `ReviewSyncService` uses `ProviderFactory` to fetch paginated reviews from the Google Business API.
  3. External star ratings are standardized to a 1-5 integer scale.
  4. Reviews are bulk "upserted" into the `reviews` table using `ON CONFLICT DO UPDATE` (matching by `provider` + `provider_review_id`).
  5. Sync results are logged in `sync_logs`.
- **Review Replies:**
  - A user can post a reply via the UI which calls `/api/v1/reviews/{id}/reply`.
  - The API forwards the reply payload to the external provider API, and updates the local DB upon success.

## Architectural Conventions

### Provider Abstraction
The system is built on a multi-provider architecture to easily support Google, Facebook, Yelp, etc.
- **Strategy:** All APIs interact with an abstract `BaseProvider` interface and models (`ReviewModel`, `LocationModel`).
- **Factory:** Providers are instantiated via `ProviderFactory.get_provider(provider_name)`.
- **Persistence:** Background tasks and services (e.g., `ReviewSyncService`) use the generic provider models and handle database bulk upserts, ensuring the core logic is provider-agnostic.

### Security
- **Token Storage:** All OAuth tokens (Access and Refresh) MUST be encrypted before being stored in the database using the utility in `app.core.security`.
- **Authorization:** Use `admin_required` and `staff_required` dependencies in `app.api.deps` to protect sensitive endpoints.

## Development Commands
- **Start All:** `docker-compose up`
- **Backend Shell:** `docker-compose exec backend bash`
- **Run Migrations:** `alembic upgrade head` (inside backend container)
- **Celery Logs:** `docker-compose logs -f worker`
