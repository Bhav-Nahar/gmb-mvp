import pytest

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    # Postgres-only JSONB columns must map to TEXT so models can be created on
    # the in-memory SQLite engine used by the `db` fixture below.
    return "TEXT"


@pytest.fixture
def db():
    """A SQLAlchemy session backed by a fresh in-memory SQLite database with all
    tables created. Used by service-layer tests that need real persistence."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    from app.db.session import Base
    import app.models  # noqa: F401 — ensure all models are registered on Base.metadata

    # SQLAlchemy strips the query string off a sqlite URL, so the old
    # "sqlite:///file:testdb?mode=memory&cache=shared" never reached SQLite as a URI:
    # it opened a real file named `file:testdb` that survived between runs. StaticPool
    # keeps the one connection alive, which is what made shared-cache tempting.
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
