import logging
import httpx
from typing import List
from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(to: List[str], subject: str, html: str) -> bool:
    """Send a transactional email via Resend. Returns True on success.

    Never raises — if RESEND_API_KEY is unset or the call fails, logs and returns
    False so the caller (lead capture, signup alerts) is never blocked.
    """
    recipients = [t for t in (to or []) if t]
    if not recipients:
        logger.warning("send_email: no recipients for %r — nothing sent", subject)
        return False
    if not settings.RESEND_API_KEY:
        logger.error("send_email: RESEND_API_KEY not set — %r to %s was NOT sent", subject, recipients)
        return False
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={"from": settings.LEAD_EMAIL_FROM, "to": recipients, "subject": subject, "html": html},
            timeout=8.0,
        )
        if resp.status_code >= 400:
            # Resend puts the actual reason in the body — unverified sender domain,
            # bad from-address, suppressed recipient. raise_for_status() discards it,
            # which turns every failure into an unactionable "403 Forbidden".
            logger.error(
                "send_email: Resend rejected %r from=%r to=%s — HTTP %s: %s",
                subject, settings.LEAD_EMAIL_FROM, recipients, resp.status_code, resp.text[:400],
            )
            return False
        logger.info("send_email: sent %r to %s", subject, recipients)
        return True
    except Exception as e:
        logger.error("send_email: %r to %s failed: %s", subject, recipients, e, exc_info=True)
        return False
