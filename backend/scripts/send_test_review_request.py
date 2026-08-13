"""Send ONE review request from the command line — the end-to-end smoke test.

    docker compose exec backend python -m scripts.send_test_review_request \
        --org 1 --location 5 --phone 919876543210 --name Bhav

Dev scaffolding. The product will trigger this from the dashboard and from a
Celery task for bulk sends; this exists so the whole loop (template -> WhatsApp
-> button -> /r/<token> -> Google) can be proven with one command.

NOTE while on the test WABA: Meta test numbers can only message recipients that
were added and code-verified in App Dashboard -> WhatsApp -> API Setup. Sending
to any other number fails, and that is Meta's restriction, not a bug here.
"""
import argparse
import sys

from app.db.session import SessionLocal
from app.models.review_request import ReviewRequest
from app.services.review_request_service import send_review_request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--org", type=int, required=True)
    parser.add_argument("--location", type=int, required=True)
    parser.add_argument("--phone", required=True, help="recipient, e.g. 919876543210")
    parser.add_argument("--name", default=None, help="customer first name for {{1}}")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        row = send_review_request(
            db,
            organization_id=args.org,
            location_id=args.location,
            phone_raw=args.phone,
            customer_name=args.name,
            source="manual",
        )
        # Read everything BEFORE the session closes. SQLAlchemy expires attributes
        # on commit and refreshes them lazily, so touching row.status after
        # db.close() raises DetachedInstanceError — which looks like a send
        # failure when the message has in fact already gone out.
        result = {
            "status": row.status,
            "token": row.token,
            "wamid": row.wamid,
            "error_code": row.error_code,
            "error_detail": row.error_detail,
        }
    except ValueError as err:
        print(f"Refused: {err}", file=sys.stderr)
        return 1
    finally:
        db.close()

    print(f"status   : {result['status']}")
    print(f"token    : {result['token']}")
    print(f"link     : https://pinzo.io/r/{result['token']}")
    if result["wamid"]:
        print(f"wamid    : {result['wamid']}")
    if result["error_code"]:
        print(f"error    : {result['error_code']} — {result['error_detail']}")
    return 0 if result["status"] == ReviewRequest.STATUS_SENT else 2


if __name__ == "__main__":
    raise SystemExit(main())
