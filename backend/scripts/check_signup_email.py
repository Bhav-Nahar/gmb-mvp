"""Diagnose why the super-admin signup email isn't arriving.

Checks every link in the chain and says which one is broken, then optionally sends
a real test email.

    python scripts/check_signup_email.py            # diagnose only
    python scripts/check_signup_email.py --send     # also send a real test email
"""
import sys

sys.path.insert(0, "/app")

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User  # noqa: E402

problems = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{('  — ' + detail) if detail else ''}")
    if not ok:
        problems.append(label)


print("=== signup email chain ===\n")

recipients = sorted(settings.superadmin_email_set)
check("SUPERADMIN_EMAILS is set", bool(recipients),
      ", ".join(recipients) if recipients else "empty — the task exits before sending")

check("RESEND_API_KEY is set", bool(settings.RESEND_API_KEY),
      "" if settings.RESEND_API_KEY else "unset — send_email no-ops and returns False")

check("LEAD_EMAIL_FROM is set", bool(settings.LEAD_EMAIL_FROM),
      f"{settings.LEAD_EMAIL_FROM} (its domain must be verified in Resend)")

try:
    from app.worker import celery
    registered = "app.tasks.notify_superadmin_signup_task" in celery.tasks
    check("task is registered in this process", registered,
          "" if registered else "worker is running older code — redeploy/restart it")
except Exception as e:
    check("task is registered in this process", False, str(e))

db = SessionLocal()
try:
    total = db.query(User).count()
    print(f"\nusers in DB: {total}")
    print("NOTE: the email only fires for a genuinely NEW workspace. Signing in with a")
    print("      Google account that already has a user row does nothing — that is not")
    print("      a bug. Use an account that has never signed in to test.")

    if "--send" in sys.argv:
        print("\n=== sending a real test email ===")
        from app.tasks import notify_superadmin_signup_task
        newest = db.query(User).order_by(User.created_at.desc()).first()
        if not newest:
            print("no users to build a test email from")
        else:
            print(f"using newest user: {newest.email}")
            print("result:", notify_superadmin_signup_task(newest.id))
            print("If this says success but no mail arrives, check Resend's dashboard")
            print("for the delivery — the API accepted it, so the problem is downstream.")
finally:
    db.close()

print("\n" + ("ALL CHECKS PASSED" if not problems else "BROKEN: " + ", ".join(problems)))
sys.exit(1 if problems else 0)
