import sys
import argparse
import logging
from app.db.session import SessionLocal
from app.models.user import User
from app.models.oauth_account import OAuthAccount
from app.models.user_location_access import UserLocationAccess
from app.models.audit_log import AuditLog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def delete_user(email: str, force: bool = False):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            logger.error(f"User with email '{email}' not found.")
            return

        if not force:
            confirm = input(f"ARE YOU SURE you want to permanently delete user '{email}' and all related OAuth/Access data? (y/N): ")
            if confirm.lower() != 'y':
                logger.info("Deletion cancelled.")
                return

        # Delete related records
        logger.info(f"Deleting data for user ID: {user.id}")
        db.query(OAuthAccount).filter(OAuthAccount.user_id == user.id).delete()
        db.query(UserLocationAccess).filter(UserLocationAccess.user_id == user.id).delete()
        db.query(AuditLog).filter(AuditLog.user_id == user.id).delete()
        
        db.delete(user)
        db.commit()
        logger.info(f"Successfully deleted user '{email}' and all related data.")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete user: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Securely delete a user and all related data by email.")
    parser.get_default("email")
    parser.add_argument("email", help="The email of the user to delete.")
    parser.add_argument("--force", action="store_true", help="Skip the confirmation prompt.")
    
    args = parser.parse_args()
    delete_user(args.email, args.force)
