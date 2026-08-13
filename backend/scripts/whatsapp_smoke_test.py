"""Send `hello_world` from an organization's stored WhatsApp credentials.

Proves the plumbing — credentials decrypt, phone number id is right, Meta
accepts us — without needing the real review template to be approved yet.

    docker compose exec backend python -m scripts.whatsapp_smoke_test \
        --org 1 --phone 919876543210

Deliberately NOT routed through review_request_service: hello_world has no body
variables and no button, so it cannot exercise the token/button path, and
teaching the real send path to special-case a test template is how test-only
branches end up running in production. This stays a throwaway.

What it proves:  auth, phone number id, connectivity, recipient reachability.
What it does not: the {{1}}/{{2}} parameters, the dynamic URL button, the
token -> /r/<token> -> Google redirect. Those need pinzo_review_request_v1.
"""
import argparse
import sys

from app.db.session import SessionLocal
from app.models.whatsapp_account import WhatsAppAccount
from app.services import whatsapp_service
from app.services.whatsapp_service import WhatsAppError, normalize_phone


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", type=int, required=True)
    parser.add_argument("--phone", required=True)
    # hello_world is published as en_US specifically. Passing "en" returns
    # "template name does not exist in the translation" — which reads like the
    # template is missing when it is only the language tag that is wrong.
    parser.add_argument("--lang", default="en_US")
    parser.add_argument("--template", default="hello_world")
    args = parser.parse_args()

    to = normalize_phone(args.phone)
    if not to:
        print(f"Not a usable phone number: {args.phone!r}", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        account = db.query(WhatsAppAccount).filter(
            WhatsAppAccount.organization_id == args.org,
        ).first()
        if not account:
            print(f"No WhatsApp account seeded for org {args.org} — run "
                  f"scripts.seed_whatsapp_test_account first", file=sys.stderr)
            return 1

        try:
            wamid = whatsapp_service.send_template(
                account, to=to, template_name=args.template, language=args.lang,
            )
        except WhatsAppError as err:
            print(f"Send failed: {err}", file=sys.stderr)
            if err.code:
                print(f"Meta error code: {err.code}", file=sys.stderr)
            return 2
    finally:
        db.close()

    print(f"sent to {to}: {wamid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
