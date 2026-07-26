import pytest

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    # Postgres-only JSONB columns must map to TEXT so models can be created on
    # the in-memory SQLite engine used by the `db` fixture below.
    return "TEXT"


@pytest.fixture(autouse=True)
def _fresh_flag_cache(monkeypatch):
    """Runtime feature flags are TTL-cached per process; tests insert AppSetting
    rows directly (sometimes mid-test) and must always read fresh — disable the TTL."""
    from app.services import app_settings
    app_settings.clear_flag_cache()
    monkeypatch.setattr(app_settings, "_FLAG_TTL_SECONDS", 0.0)
    yield
    app_settings.clear_flag_cache()


@pytest.fixture
def db():
    """A SQLAlchemy session backed by a fresh in-memory SQLite database with all
    tables created. Used by service-layer tests that need real persistence."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db.session import Base
    import app.models  # noqa: F401 — ensure all models are registered on Base.metadata

    # StaticPool keeps the single connection alive: with the default pool, a second
    # connection to :memory: would get its own empty database.
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def fake_admin_user():
    """A lightweight stand-in for an authenticated Owner/Admin user.

    Avoids touching the database so API-layer tests can run without a live
    Postgres instance.
    """
    from types import SimpleNamespace

    return SimpleNamespace(
        id=1,
        email="admin@example.com",
        organization_id=1,
        role="Admin",
        is_active=True,
        viewer_scope=None,
    )
