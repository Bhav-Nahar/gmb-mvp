import logging
import httpx
from typing import List
from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(to: List[str], subject: str, html: str) -> bool:
    """Send a transactional email via Resend. Returns True on success.

    Never raises — if RESEND_API_KEY is unset or the call fails, logs a warning
    and returns False so the caller (lead capture) is never blocked.
    """
    recipients = [t for t in (to or []) if t]
    if not recipients:
        return False
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — skipping lead email to %s", recipients)
        return False
    try:
        resp = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
            json={"from": settings.LEAD_EMAIL_FROM, "to": recipients, "subject": subject, "html": html},
            timeout=8.0,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("Lead email send failed: %s", e)
        return False
