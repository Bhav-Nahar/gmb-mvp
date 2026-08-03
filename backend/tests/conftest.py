import sys
import types
from unittest.mock import MagicMock

import pytest

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB

# ── Import-time stubs ─────────────────────────────────────────────────────────
#
# conftest is imported before any test module, so these land in sys.modules in
# time for `import celery` / `import app.worker` further down the tree. Twelve
# suites used to carry their own copy of this block.
#
# Both are no-ops wherever celery is actually installed (the container, CI); they
# only fire on a machine running the suite without the full requirements.
try:  # pragma: no cover — depends on the local environment, not on any test
    import celery
    if not hasattr(celery, "shared_task"):  # partial install
        celery.shared_task = lambda *a, **kw: (lambda fn: fn)
except ImportError:
    if "celery" not in sys.modules:
        _celery = types.ModuleType("celery")
        _celery_schedules = types.ModuleType("celery.schedules")

        class _StubCelery:
            def __init__(self, *args, **kwargs):
                self.conf = types.SimpleNamespace(beat_schedule={}, timezone="UTC")

            def send_task(self, *args, **kwargs):
                return type("T", (), {"id": "stub-task"})()

            def autodiscover_tasks(self, *args, **kwargs):
                return None

        _celery.Celery = _StubCelery
        _celery.shared_task = lambda *a, **kw: (lambda fn: fn)
        _celery_schedules.crontab = lambda *a, **kw: None
        sys.modules["celery"] = _celery
        sys.modules["celery.schedules"] = _celery_schedules

import app as _app_pkg
try:  # pragma: no cover — same
    import app.worker  # real celery app; also sets the app.worker attribute for patch()
except Exception:
    if "app.worker" not in sys.modules:
        _fake_worker = types.ModuleType("app.worker")
        _fake_worker.celery = MagicMock()
        sys.modules["app.worker"] = _fake_worker
    _app_pkg.worker = sys.modules["app.worker"]


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


# --- never let a test run against a database that matters --------------------

_LOCAL_DB_HOSTS = {"", "localhost", "127.0.0.1", "db", "postgres"}


def pytest_sessionstart(session):
    """Abort the run if DATABASE_URL points at a remote database.

    Two suites (test_reliability, test_media) bind to the app's real engine so a task
    under test and the test itself share a session. That is survivable against the local
    dev stack; against production credentials it would write to — and, before the scoping
    fix in test_reliability.setUp, DELETE FROM — the live tenant tables.
    """
    import pytest
    from app.db.session import engine

    if engine.url.get_backend_name() == "sqlite":
        return
    host = engine.url.host or ""
    if host not in _LOCAL_DB_HOSTS:
        raise pytest.UsageError(
            f"refusing to run the test suite against remote database host {host!r} — "
            "tests write to (and clean up in) the configured database."
        )
