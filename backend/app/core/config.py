import os
from urllib.parse import urlparse, urlunparse
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )

    # Environment. Defaults to "production" so a deployment that forgets to set
    # APP_ENV fails CLOSED (CSRF/HSTS/secret-validation stay on) rather than
    # silently running in development mode. Local dev sets APP_ENV=development
    # explicitly (see docker-compose.yml).
    APP_ENV: str = "production"

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@db:5432/gmb_db"

    # Database connection pool. Defaults match SQLAlchemy's prior implicit
    # behavior (pool_size=5, max_overflow=10, pool_timeout=30) so steady-state
    # is unchanged; pool_recycle is added to avoid stale-connection errors on
    # managed Postgres. All are env-tunable to right-size for concurrency.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE_SECONDS: int = 1800
    DB_POOL_TIMEOUT_SECONDS: int = 30

    @property
    def sqlalchemy_database_url(self) -> str:
        """Normalises the DATABASE_URL to use the postgresql+psycopg2 scheme."""
        url = self.DATABASE_URL
        parsed = urlparse(url)
        scheme = parsed.scheme
        # Only Postgres needs scheme normalisation; leave others (e.g. sqlite, used in
        # tests) untouched — urlunparse collapses sqlite's empty-netloc triple slash
        # ('sqlite:///x' -> 'sqlite:/x') into something SQLAlchemy can't parse.
        if scheme in ("postgres", "postgresql"):
            return urlunparse(parsed._replace(scheme="postgresql+psycopg2"))
        # If driver is already present (e.g. postgresql+asyncpg) leave it alone
        return url

    # Redis & Celery
    REDIS_URL: str = "redis://redis:6379/0"

    # Security
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    ENCRYPTION_KEY: str = ""

    # Platform super-admin allowlist (comma-separated emails). These users get the
    # cross-org /admin panel; they still log in normally via Google. Set in
    # docker-compose `backend` env. Empty = no super-admins. No DB column/migration,
    # so the first admin needs no manual DB edit — just add their email here.
    SUPERADMIN_EMAILS: str = ""

    @model_validator(mode="after")
    def _validate_secrets(self) -> "Settings":
        # JWT_SECRET signs every auth token and ENCRYPTION_KEY encrypts OAuth
        # tokens at rest. An empty value here means tokens are signed with an
        # empty key (forgeable) or tokens are not truly encrypted — there is no
        # environment, development included, where that is acceptable. Validate
        # unconditionally so misconfiguration fails loudly at startup.
        if not self.JWT_SECRET:
            raise ValueError(
                "FATAL: JWT_SECRET must be set via environment variable"
            )
        if not self.ENCRYPTION_KEY:
            raise ValueError(
                "FATAL: ENCRYPTION_KEY must be set via environment variable"
            )
        return self

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # LLM Settings
    GROQ_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    # Gemini's OpenAI-compatible endpoint — lets us reuse the AsyncOpenAI client.
    GEMINI_BASE_URL: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    LLM_PROVIDER: str = "groq"  # "groq" | "gemini"
    LLM_MODEL: str = "llama-3.3-70b-versatile"  # set to e.g. "gemini-2.5-flash" when LLM_PROVIDER=gemini
    # Per-feature override. Review replies + descriptions use the global provider
    # above (Gemini in prod); sentiment tagging runs on Groq to keep its high-volume
    # batch classification off the Gemini quota. Provider + model must be set together.
    LLM_PROVIDER_SENTIMENT: str = "groq"
    LLM_MODEL_SENTIMENT: str = "llama-3.3-70b-versatile"

    # Frontend
    FRONTEND_URL: str = "http://localhost:3000"
    # Extra browser origins allowed to call the API, in addition to FRONTEND_URL
    # (and its www/non-www twin). Comma-separated, e.g.
    #   "https://www.pinzo.io,https://pinzo.io,https://app.vercel.app"
    # Use this when the app is served from more than one domain.
    ADDITIONAL_CORS_ORIGINS: str = ""

    # Backend
    BACKEND_URL: str = "http://localhost:8000"
    REVALIDATE_SECRET: str = ""

    # Lead-notification email (Resend). Empty key => email silently skipped (leads
    # are still stored and shown in the dashboard).
    RESEND_API_KEY: str = ""
    LEAD_EMAIL_FROM: str = "Pinzo Leads <leads@pinzo.io>"

    # Web Push (VAPID). Dev defaults below; OVERRIDE in production via env and keep
    # the private key secret. Empty private key => push silently skipped.
    VAPID_PUBLIC_KEY: str = "BAP6iNtANNGg0NHuPbpgwEhcRJrogJnFhQ_V22wVmbKT6_C2TAJehuMplEeF9eh8dev_HIuAkJPNvQdNGxqCdmg"
    VAPID_PRIVATE_KEY: str = "Fn5whJh_EjnOCnsOtLiPdV0Eniypj4aoONcP3byQQfU"
    VAPID_SUBJECT: str = "mailto:leads@pinzo.io"

    # Shared cookie domain. When the frontend and API are served from sibling
    # subdomains of ONE registrable domain (e.g. app.pinzo.io + api.pinzo.io),
    # set this to the parent WITH a leading dot (".pinzo.io") so the auth cookies
    # (gmb_auth_token / gmb_refresh_token / gmb_csrf_token / oauth_state) are
    # first-party to both hosts and sent in every browser — including those that
    # block third-party cookies. Leave EMPTY for single-host or localhost dev,
    # where cookies stay host-only. Never set this to a bare public suffix.
    COOKIE_DOMAIN: str = ""

    @field_validator("COOKIE_DOMAIN", mode="after")
    @classmethod
    def _normalize_cookie_domain(cls, v: str) -> str:
        """Strip any scheme/port a user may paste and ensure a leading dot so the
        cookie is shared across subdomains. '' stays '' (host-only)."""
        v = (v or "").strip()
        if not v:
            return ""
        # Tolerate someone pasting "https://api.pinzo.io" or "pinzo.io".
        if "://" in v:
            v = urlparse(v).hostname or ""
        v = v.split(":")[0].strip().lstrip(".")
        return f".{v}" if v else ""

    @field_validator("FRONTEND_URL", "BACKEND_URL", mode="after")
    @classmethod
    def _ensure_url_scheme(cls, v: str) -> str:
        """A URL env set without a scheme (e.g. 'www.pinzo.io') silently breaks CORS,
        secure-cookie detection, and OAuth redirects. Default a bare host to https://."""
        v = (v or "").strip()
        if v and "://" not in v:
            v = f"https://{v}"
        return v

    # DataForSEO — local rank grid + competitor maps data (one vendor, one client).
    # Defaults to the FREE sandbox (simulated data) so nothing is billed until you
    # set the base URL to https://api.dataforseo.com. Same login/password for both.
    # Sign up (sandbox + $1 live credit, no card): https://app.dataforseo.com
    DATAFORSEO_LOGIN: str = ""
    DATAFORSEO_PASSWORD: str = ""
    DATAFORSEO_BASE_URL: str = "https://sandbox.dataforseo.com"

    # AEO (AI-search visibility). Defaults to the "mock" provider — realistic
    # sample results, zero external calls, zero spend — so the whole UI/UX is
    # explorable in a sandbox before wiring the real DataForSEO AI endpoints
    # (set AEO_PROVIDER="dataforseo"). See app/services/aeo_service.py.
    AEO_PROVIDER: str = "mock"          # "mock" | "dataforseo"
    AEO_QUERIES_PER_SCAN: int = 10      # auto-generated (category+city) queries
    AEO_MAX_CUSTOM_QUERIES: int = 10    # extra queries an Owner/Admin may add per location
    AEO_MAX_QUERIES: int = 20           # hard cap on total (custom + auto) per scan
    # Location targeting for real (dataforseo) scans. DataForSEO wants a numeric
    # location_code; 2356 = India (country-level). City-level codes exist but need
    # a lookup — country-level is fine for a first pass.
    AEO_LOCATION_CODE: int = 2356

    # Task Settings
    REVIEW_SYNC_CHUNK_SIZE: int = 20
    REVIEW_SYNC_SLEEP_SECONDS: float = 0.2
    EDIT_STALE_TIMEOUT_MINUTES: int = 5

    # Storage Settings
    STORAGE_PROVIDER: str = "local"  # "local", "r2"
    LOCAL_STORAGE_DIR: str = "static/uploads"

    # Cloudflare R2 Configuration
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = ""

    # Optional CDN
    CDN_DOMAIN: str = ""
    # Razorpay Configuration
    RAZORPAY_KEY_ID: str = ""
    RAZORPAY_KEY_SECRET: str = ""
    RAZORPAY_WEBHOOK_SECRET: str = ""

    # Card-required trial onboarding. OFF (default) = legacy frictionless trial:
    # the 7-day trial starts on first sync, no payment method needed. ON = sync the
    # audit first, then require a card / UPI Autopay mandate to START the trial;
    # premium stays locked until then. Flagged so the new money path can be built and
    # rolled out (or A/B'd) without disturbing the live frictionless flow — delete the
    # flag and the legacy branches once fully cut over.
    CARD_REQUIRED_ONBOARDING: bool = False

    # Server-side conversions (fired from the Razorpay webhook). All blank by default —
    # each integration stays inert until its credentials are provided.
    # Meta Conversions API
    META_PIXEL_ID: str = ""
    META_CAPI_ACCESS_TOKEN: str = ""
    META_CAPI_API_VERSION: str = "v21.0"
    # Google Ads offline click-conversion upload
    GOOGLE_ADS_DEVELOPER_TOKEN: str = ""
    GOOGLE_ADS_CLIENT_ID: str = ""
    GOOGLE_ADS_CLIENT_SECRET: str = ""
    GOOGLE_ADS_REFRESH_TOKEN: str = ""
    GOOGLE_ADS_CUSTOMER_ID: str = ""          # digits only, no dashes
    GOOGLE_ADS_LOGIN_CUSTOMER_ID: str = ""    # optional, for manager accounts
    GOOGLE_ADS_CONVERSION_ACTION_ID: str = ""

    # Google Search Console (pSEO organic performance). Service-account credential,
    # separate from the per-org GBP OAuth flow — pSEO pages aren't org-scoped, so one
    # shared read-only credential on the property covers every pSEO page.
    GSC_SERVICE_ACCOUNT_JSON: str = ""  # raw JSON key content
    GSC_PROPERTY_URL: str = ""          # e.g. "sc-domain:pinzo.io" or "https://pinzo.io/"

    @model_validator(mode="after")
    def _validate_razorpay(self) -> "Settings":
        import os
        # Skip validation in Celery worker processes — they don't handle billing routes
        if os.environ.get("CELERY_WORKER") == "1":
            return self
        if self.APP_ENV != "development":
            if not self.RAZORPAY_KEY_ID or not self.RAZORPAY_KEY_SECRET or not self.RAZORPAY_WEBHOOK_SECRET:
                raise ValueError("FATAL: Razorpay credentials must be set in production")
        return self

    @property
    def superadmin_email_set(self) -> frozenset:
        return frozenset(
            e.strip().lower()
            for e in (self.SUPERADMIN_EMAILS or "").split(",")
            if e.strip()
        )

    def is_superadmin(self, email: str | None) -> bool:
        return bool(email) and email.strip().lower() in self.superadmin_email_set

settings = Settings()
