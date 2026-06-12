import pytest


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
