import sys, os
sys.path.append('c:/Users/Shubham/Documents/GitHub/gmb-mvp/backend')
from app.db.session import SessionLocal
from app.models.user import User
from app.models.oauth_account import OAuthAccount
from app.models.user_location_access import UserLocationAccess
from app.models.audit_log import AuditLog

def delete_user(email):
    db = SessionLocal()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        print('User not found')
        return
    # Delete related records
    db.query(OAuthAccount).filter(OAuthAccount.user_id == user.id).delete()
    db.query(UserLocationAccess).filter(UserLocationAccess.user_id == user.id).delete()
    db.query(AuditLog).filter(AuditLog.user_id == user.id).delete()
    db.delete(user)
    db.commit()
    print('User and related data deleted')

if __name__ == '__main__':
    delete_user('bhav.nahar@lucirajewelry.com')
