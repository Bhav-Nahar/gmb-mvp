"""Seed the DEV test WABA into whatsapp_accounts, so the send pipeline can be
exercised before Meta grants advanced access.

This is development scaffolding, not part of the product. In production an
organization's credentials arrive from Embedded Signup and are written by the
onboarding flow — never from env, and never by a script.

    docker compose exec backend python -m scripts.seed_whatsapp_test_account --org 1

Reads WHATSAPP_SYSTEM_TOKEN / WHATSAPP_TEST_PHONE_NUMBER_ID /
WHATSAPP_TEST_WABA_ID from the environment and encrypts the token at rest with
the same Fernet helper used for Google OAuth tokens.
"""
import argparse
import os
import sys
from datetime import datetime, timezone

from app.core.security import encrypt_token
from app.db.session import SessionLocal
from app.models.organization import Organization
from app.models.whatsapp_account import WhatsAppAccount

TEMPLATE_NAME = os.environ.get("WHATSAPP_REVIEW_TEMPLATE", "pinzo_review_request_v1")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", type=int, required=True, help="organization id to attach the test WABA to")
    parser.add_argument("--template", default=TEMPLATE_NAME)
    args = parser.parse_args()

    token = os.environ.get("WHATSAPP_SYSTEM_TOKEN", "").strip()
    phone_number_id = os.environ.get("WHATSAPP_TEST_PHONE_NUMBER_ID", "").strip()
    waba_id = os.environ.get("WHATSAPP_TEST_WABA_ID", "").strip()

    missing = [k for k, v in {
        "WHATSAPP_SYSTEM_TOKEN": token,
        "WHATSAPP_TEST_PHONE_NUMBER_ID": phone_number_id,
        "WHATSAPP_TEST_WABA_ID": waba_id,
    }.items() if not v]
    if missing:
        print(f"Missing env: {', '.join(missing)}", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        org = db.query(Organization).filter(Organization.id == args.org).first()
        if not org:
            print(f"Organization {args.org} not found", file=sys.stderr)
            return 1

        account = db.query(WhatsAppAccount).filter(
            WhatsAppAccount.organization_id == args.org,
        ).first()
        if not account:
            account = WhatsAppAccount(organization_id=args.org)
            db.add(account)

        account.waba_id = waba_id
        account.phone_number_id = phone_number_id
        account.access_token = encrypt_token(token)
        account.template_name = args.template
        # Marked ready deliberately: this is the dev shortcut past the onboarding
        # state machine, which in production walks through connect -> register ->
        # payment -> template approval before anything can send.
        account.status = WhatsAppAccount.STATUS_READY
        account.status_detail = "Seeded dev test WABA (scripts/seed_whatsapp_test_account.py)"
        account.connected_at = account.connected_at or datetime.now(timezone.utc)
        db.commit()

        print(f"Seeded test WABA for org {args.org} "
              f"(waba={waba_id}, phone_number_id={phone_number_id}, template={args.template})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
