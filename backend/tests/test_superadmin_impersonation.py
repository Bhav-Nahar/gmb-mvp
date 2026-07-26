"""Super-admin workspace impersonation via X-Acting-Org (deps.get_current_user).

A super-admin sending X-Acting-Org gets organization_id overridden so downstream
org-scoped queries hit the target workspace; everyone else is ignored.
"""
import os
import sys
import types
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.dialects.postgresql import JSONB
from fastapi import HTTPException

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "TEXT"



from app.db.session import Base
from app.models.organization import Organization
from app.models.user import User
from app.core.roles import Role
from app.core.config import settings
from app.core.security import create_access_token
from app.api.deps import get_current_user


class _FakeRequest:
    def __init__(self, token, headers=None, method="GET", path="/x"):
        self.cookies = {"gmb_auth_token": token}
        self.headers = headers or {}
        self.method = method
        self.url = types.SimpleNamespace(path=path)
        self.state = types.SimpleNamespace()  # real Requests always carry .state


class SuperadminImpersonationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

        self.org1 = Organization(name="Admin Org")
        self.org2 = Organization(name="Target Org")
        self.db.add_all([self.org1, self.org2])
        self.db.commit()

        self.admin = User(email="root@platform.com", name="Root", google_id="g1",
                          role=Role.ADMIN, is_active=True, organization_id=self.org1.id)
        self.normal = User(email="user@acme.com", name="U", google_id="g2",
                           role=Role.ADMIN, is_active=True, organization_id=self.org1.id)
        self.db.add_all([self.admin, self.normal])
        self.db.commit()

        self._orig = settings.SUPERADMIN_EMAILS
        settings.SUPERADMIN_EMAILS = "root@platform.com"

    def tearDown(self):
        settings.SUPERADMIN_EMAILS = self._orig
        self.db.close()

    def _token(self, user):
        return create_access_token(subject=user.email, token_version=user.token_version or 1)

    def test_superadmin_override_applies(self):
        req = _FakeRequest(self._token(self.admin), {"X-Acting-Org": str(self.org2.id)})
        u = get_current_user(request=req, db=self.db)
        self.assertEqual(u.organization_id, self.org2.id)
        # Override must NOT be dirty — a commit elsewhere can't persist it back.
        self.assertNotIn(u, self.db.dirty)
        self.db.commit()
        self.db.refresh(u)
        self.assertEqual(u.organization_id, self.org1.id)

    def test_non_superadmin_ignored(self):
        req = _FakeRequest(self._token(self.normal), {"X-Acting-Org": str(self.org2.id)})
        u = get_current_user(request=req, db=self.db)
        self.assertEqual(u.organization_id, self.org1.id)

    def test_invalid_header_rejected(self):
        req = _FakeRequest(self._token(self.admin), {"X-Acting-Org": "abc"})
        with self.assertRaises(HTTPException) as ctx:
            get_current_user(request=req, db=self.db)
        self.assertEqual(ctx.exception.status_code, 400)

    def test_no_header_unchanged(self):
        req = _FakeRequest(self._token(self.admin))
        u = get_current_user(request=req, db=self.db)
        self.assertEqual(u.organization_id, self.org1.id)


if __name__ == "__main__":
    unittest.main()
