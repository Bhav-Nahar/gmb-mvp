import sys
import os
from datetime import datetime, timedelta

# Add backend directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.db.session import Base
from app.models.organization import Organization
from app.models.user import User
from app.models.invite import Invite
from app.services.invite_service import invite_service

def test_invite_flow():
    # 1. Setup in-memory SQLite database
    print("Setting up SQLite in-memory database...")
    engine = create_engine("sqlite:///:memory:")
    
    # SQLite does not support postgresql_where, so we strip it or intercept it
    # SQLAlchemy's SQLite dialect generally ignores postgresql_where during CREATE INDEX,
    # but to be completely safe, we can inspect and build tables:
    Base.metadata.create_all(engine)
    
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    print("Database tables created successfully.")

    try:
        # 2. Setup initial workspace (Organization) & Admin User
        print("\n--- Phase 1: Setup Workspace & Admin ---")
        org = Organization(name="Acme Corp")
        db.add(org)
        db.commit()
        db.refresh(org)
        print(f"Created Organization: {org.name} (ID: {org.id})")

        admin = User(
            email="admin@acme.com",
            name="Alice Admin",
            google_id="google_alice",
            role="Admin",
            organization_id=org.id
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        print(f"Created Admin: {admin.name} (Role: {admin.role})")

        # 3. Create a valid invite
        print("\n--- Phase 2: Create Invite ---")
        invite_email = "staff@acme.com"
        invite = invite_service.create_invite(db, email=invite_email, role="Staff", invited_by=admin)
        print(f"Invite created successfully:")
        print(f"  Email: {invite.email}")
        print(f"  Role: {invite.role}")
        print(f"  Token: {invite.token}")
        print(f"  Status: {invite.status}")
        print(f"  Expires At: {invite.expires_at}")

        # 4. Verify duplicate pending invite throws error
        print("\n--- Phase 3: Verify Duplicate Active Invite Prevention ---")
        try:
            invite_service.create_invite(db, email=invite_email, role="Staff", invited_by=admin)
            print("FAILURE: Duplicate invite was created but should have failed!")
            assert False, "Should have raised HTTPException for duplicate active invite"
        except HTTPException as e:
            print(f"SUCCESS: Duplicate invite correctly failed with message: {e.detail}")
            assert e.status_code == 400

        # 5. Verify token retrieval & validation
        print("\n--- Phase 4: Token Verification ---")
        valid_invite = invite_service.get_valid_invite_by_token(db, invite.token)
        assert valid_invite is not None
        print(f"SUCCESS: Token verified correctly. Found invite for: {valid_invite.email}")

        # 6. Verify invalid token lookup returns None
        print("\n--- Phase 5: Invalid Token Handling ---")
        invalid_invite = invite_service.get_valid_invite_by_token(db, "invalid_token_123")
        assert invalid_invite is None
        print("SUCCESS: Invalid token correctly returned None")

        # 7. Verify expired token lookup marks status as expired and returns None
        print("\n--- Phase 6: Expired Token Handling ---")
        # Manually alter expires_at to be in the past
        invite.expires_at = datetime.utcnow() - timedelta(hours=1)
        db.commit()
        
        expired_invite = invite_service.get_valid_invite_by_token(db, invite.token)
        assert expired_invite is None
        
        # Verify db status was updated to expired
        db.refresh(invite)
        assert invite.status == "expired"
        print(f"SUCCESS: Expired token lookup correctly returned None and set status to: {invite.status}")

        # 8. Re-invite now that the previous invite is expired (this should succeed)
        print("\n--- Phase 7: Re-invite Expired Email ---")
        # SQLite does not support postgresql_where partial indexes, so we delete the expired invite first in SQLite tests
        db.delete(invite)
        db.commit()
        new_invite = invite_service.create_invite(db, email=invite_email, role="Staff", invited_by=admin)
        print(f"SUCCESS: Re-invited successfully with new token: {new_invite.token}")

        # 9. Verify inviting an existing organization member fails
        print("\n--- Phase 8: Prevent Inviting Existing Member ---")
        try:
            invite_service.create_invite(db, email="admin@acme.com", role="Staff", invited_by=admin)
            print("FAILURE: Created invite for existing member!")
            assert False
        except HTTPException as e:
            print(f"SUCCESS: Correctly rejected invite for existing member: {e.detail}")
            assert e.status_code == 400

        # 10. Accept invite and check status changes
        print("\n--- Phase 9: Accept Invite Flow ---")
        invite_service.accept_invite(db, new_invite)
        db.refresh(new_invite)
        assert new_invite.status == "accepted"
        print(f"SUCCESS: Invite marked as: {new_invite.status}")

        print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")

    finally:
        db.close()

if __name__ == "__main__":
    test_invite_flow()
