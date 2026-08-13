"""Create the demo organization used for Meta App Review.

    docker compose exec backend python -m scripts.seed_demo_org --email test@gmail.com

Why a separate organization rather than pointing the reviewer at a real one:
your production org holds actual GBP locations, leads and customer phone
numbers. Handing a third party a login into that exposes your customers'
personal data for no reason. This org contains only synthetic data.

It creates:
  * organization "Pinzo Demo"
  * an Owner user with the given email (login itself is handled by
    /auth/demo-login — see app/api/auth_demo.py)
  * one location with a REAL Google review URI, so the review button in a demo
    actually lands somewhere rather than 404ing on camera
  * a WhatsApp account row wired to the dev test WABA from the environment
"""
import argparse
import os
import sys
from datetime import datetime, timezone

from app.core.security import encrypt_token
from app.db.session import SessionLocal
from app.models.location import Location
from app.models.organization import Organization
from app.models.user import User
from app.models.whatsapp_account import WhatsAppAccount

DEMO_ORG_NAME = "Pinzo Demo"

# A real, public place so the review link resolves to a genuine Google page.
# Defaults to the Google Sydney office — a well-known public listing, not a
# customer's business, which is the point: nothing here belongs to a real client.
DEMO_PLACE_ID = os.environ.get("DEMO_PLACE_ID", "ChIJN1t_tDeuEmsRUsoyG83frY4")
DEMO_LOCATION_NAME = os.environ.get("DEMO_LOCATION_NAME", "Pinzo Demo Store")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True, help="reviewer login email")
    parser.add_argument("--name", default="App Reviewer")
    args = parser.parse_args()
    email = args.email.strip().lower()

    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.name == DEMO_ORG_NAME).first()
        if not org:
            org = Organization(name=DEMO_ORG_NAME)
            db.add(org)
            db.flush()
            print(f"created organization '{DEMO_ORG_NAME}' (id={org.id})")
        else:
            print(f"organization '{DEMO_ORG_NAME}' already exists (id={org.id})")

        # Present the org as an established paying customer, not a fresh signup.
        # A trial with no trial_ends_at is what triggers the onboarding audit
        # screen ("Building your audit"), which waits forever on a Google sync
        # this account can never have — a reviewer would sit on that spinner and
        # conclude the product is broken.
        org.subscription_status = "active"
        org.plan = "active"
        org.plan_tier = os.environ.get("DEMO_PLAN_TIER", "pro")   # so premium screens are visible
        org.trial_ends_at = org.trial_ends_at or datetime.now(timezone.utc)
        org.location_quota = max(org.location_quota or 0, 3)
        db.flush()
        print(f"org set to active / {org.plan_tier} so onboarding gates are skipped")

        user = db.query(User).filter(User.email == email).first()
        if user and user.organization_id != org.id:
            print(f"REFUSING: {email} already belongs to organization {user.organization_id}. "
                  f"Use an address that is not attached to a real org.", file=sys.stderr)
            return 1
        if not user:
            # google_id is NOT NULL because every real user arrives via Google
            # OAuth. This account authenticates through /auth/demo-login instead,
            # so it gets a synthetic, clearly-labelled id — never a value that
            # could collide with a real Google subject.
            user = User(email=email, name=args.name, organization_id=org.id, role="Owner",
                        google_id=f"demo-login:{email}")
            db.add(user)
            db.flush()
            print(f"created user {email} (id={user.id}, Owner of org {org.id})")
        else:
            print(f"user {email} already exists (id={user.id})")

        location = db.query(Location).filter(
            Location.organization_id == org.id,
            Location.location_name == DEMO_LOCATION_NAME,
        ).first()
        if not location:
            location = Location(
                organization_id=org.id,
                google_location_id=f"locations/demo-{org.id}",
                location_name=DEMO_LOCATION_NAME,
                city="Mumbai",
                sync_status="Synced",
                # The redirect reads the review URI straight out of gbp_raw, the
                # same field the real Google sync populates — so the demo
                # exercises the production code path, not a special case.
                gbp_raw={"metadata": {
                    "placeId": DEMO_PLACE_ID,
                    "newReviewUri": f"https://search.google.com/local/writereview?placeid={DEMO_PLACE_ID}",
                }},
            )
            db.add(location)
            db.flush()
            print(f"created location '{DEMO_LOCATION_NAME}' (id={location.id})")
        else:
            print(f"location '{DEMO_LOCATION_NAME}' already exists (id={location.id})")

        token = os.environ.get("WHATSAPP_SYSTEM_TOKEN", "").strip()
        phone_id = os.environ.get("WHATSAPP_TEST_PHONE_NUMBER_ID", "").strip()
        waba_id = os.environ.get("WHATSAPP_TEST_WABA_ID", "").strip()
        if token and phone_id and waba_id:
            wa = db.query(WhatsAppAccount).filter(
                WhatsAppAccount.organization_id == org.id).first()
            if not wa:
                wa = WhatsAppAccount(organization_id=org.id)
                db.add(wa)
            wa.waba_id = waba_id
            wa.phone_number_id = phone_id
            wa.access_token = encrypt_token(token)
            wa.template_name = os.environ.get("WHATSAPP_REVIEW_TEMPLATE", "review")
            wa.template_status = "APPROVED"
            wa.status = WhatsAppAccount.STATUS_READY
            wa.status_detail = "Demo WhatsApp account (scripts/seed_demo_org.py)"
            wa.connected_at = wa.connected_at or datetime.now(timezone.utc)
            print(f"wired WhatsApp account (waba={waba_id})")
        else:
            print("WHATSAPP_* env not set — skipped the WhatsApp account "
                  "(the dashboard will show 'not connected')")

        db.commit()
        print(f"\nDone. org_id={org.id} location_id={location.id}")
        print("Login needs: DEMO_LOGIN_ENABLED=true, DEMO_LOGIN_EMAIL="
              f"{email}, DEMO_LOGIN_PASSWORD_HASH=<from scripts.hash_demo_password>")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
