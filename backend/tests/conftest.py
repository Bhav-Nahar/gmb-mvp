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
    tables created. Mirrors the fixture in app/tests/conftest.py for tests that
    live under the top-level tests/ directory."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.session import Base
    import app.models  # noqa: F401 — ensure all models are registered on Base.metadata

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
