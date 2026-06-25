import json
import logging
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.push_subscription import PushSubscription

logger = logging.getLogger(__name__)


def send_push_to_org(db: Session, organization_id: int, title: str, body: str, url: str = "/") -> int:
    """Best-effort Web Push to every subscription in an org. Returns count sent.
    Never raises; prunes subscriptions that Push services report as gone (404/410)."""
    if not settings.VAPID_PRIVATE_KEY:
        logger.warning("VAPID_PRIVATE_KEY not set — skipping web push.")
        return 0
    try:
        from pywebpush import webpush, WebPushException
    except Exception as e:  # dependency missing
        logger.warning("pywebpush unavailable: %s", e)
        return 0

    subs = db.query(PushSubscription).filter(PushSubscription.organization_id == organization_id).all()
    payload = json.dumps({"title": title, "body": body, "url": url})
    sent = 0
    for s in subs:
        try:
            webpush(
                subscription_info={"endpoint": s.endpoint, "keys": {"p256dh": s.p256dh, "auth": s.auth}},
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                timeout=8,
            )
            sent += 1
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (404, 410):
                db.delete(s)  # subscription expired/unsubscribed
            else:
                logger.warning("Web push failed (%s): %s", code, e)
        except Exception as e:
            logger.warning("Web push error: %s", e)
    if sent or subs:
        db.commit()
    return sent
