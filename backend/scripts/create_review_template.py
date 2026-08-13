"""Create the review-request template on an organization's WABA.

This is the SAME function onboarding calls when a tenant connects
(whatsapp_onboarding_service.ensure_review_template) — templates live on the
sending account, so every tenant gets their own copy created for them. There is
no UI for it because no human should have to author WhatsApp template JSON, and
because Pinzo owns the copy: the tenant cannot write their own message.

    docker compose exec backend python -m scripts.create_review_template --org 1
    docker compose exec backend python -m scripts.create_review_template --org 1 --name pinzo_review_request_v3
"""
import argparse
import sys

from app.db.session import SessionLocal
from app.models.whatsapp_account import WhatsAppAccount
from app.services import whatsapp_onboarding_service as onboarding
from app.services.whatsapp_service import WhatsAppError, _token


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", type=int, required=True)
    parser.add_argument("--name", default=onboarding.REVIEW_TEMPLATE_NAME,
                        help="template name; use a new one to see a fresh creation")
    parser.add_argument("--base", default=None,
                        help="redirect base for the button URL (defaults to FRONTEND_URL)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        account = db.query(WhatsAppAccount).filter(
            WhatsAppAccount.organization_id == args.org,
        ).first()
        if not account or not account.waba_id:
            print(f"No connected WhatsApp account for org {args.org}", file=sys.stderr)
            return 1

        base = args.base or onboarding._redirect_base()
        print(f"WABA          : {account.waba_id}")
        print(f"template name : {args.name}")
        print(f"button base   : {base}/r/<token>")

        # Same call onboarding makes; only the name is overridable so a
        # demonstration can create a fresh one instead of hitting "already exists".
        original = onboarding.REVIEW_TEMPLATE_NAME
        onboarding.REVIEW_TEMPLATE_NAME = args.name
        try:
            result = onboarding.ensure_review_template(account.waba_id, _token(account), base)
        finally:
            onboarding.REVIEW_TEMPLATE_NAME = original

        print(f"created       : id={result.get('id')} status={result.get('status')} "
              f"category={result.get('category')}")
        return 0
    except WhatsAppError as err:
        print(f"WhatsApp API refused it: {err}", file=sys.stderr)
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
