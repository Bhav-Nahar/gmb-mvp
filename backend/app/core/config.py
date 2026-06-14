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
        # Normalise bare 'postgres' or 'postgresql' to 'postgresql+psycopg2'
        if scheme in ("postgres", "postgresql"):
            scheme = "postgresql+psycopg2"
        # If driver is already present (e.g. postgresql+asyncpg) leave it alone
        rebuilt = urlunparse(parsed._replace(scheme=scheme))
        return rebuilt

    # Redis & Celery
    REDIS_URL: str = "redis://redis:6379/0"

    # Security
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    ENCRYPTION_KEY: str = ""

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
    LLM_PROVIDER: str = "groq"
    LLM_MODEL: str = "llama-3.3-70b-versatile"

    # Frontend
    FRONTEND_URL: str = "http://localhost:3000"

    # Backend
    BACKEND_URL: str = "http://localhost:8000"

    # Task Settings
    REVIEW_SYNC_CHUNK_SIZE: int = 20
    REVIEW_SYNC_SLEEP_SECONDS: float = 0.2
    EDIT_STALE_TIMEOUT_MINUTES: int = 5

    # Storage Settings
    STORAGE_PROVIDER: str = "local"  # "local", "s3", "r2"
    LOCAL_STORAGE_DIR: str = "static/uploads"

    # AWS S3 Configuration
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = ""
    S3_ENDPOINT_URL: str = ""

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

    @model_validator(mode="after")
    def _validate_razorpay(self) -> "Settings":
        if self.APP_ENV != "development":
            if not self.RAZORPAY_KEY_ID or not self.RAZORPAY_KEY_SECRET or not self.RAZORPAY_WEBHOOK_SECRET:
                raise ValueError("FATAL: Razorpay credentials must be set in production")
        return self

settings = Settings()
