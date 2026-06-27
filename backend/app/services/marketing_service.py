"""Server-side ad conversions (Meta CAPI + Google Ads).

Fired from a Celery task after a first subscription charge — never inline in the
webhook, so external HTTP never holds the org row lock. Each integration is inert
until its credentials are set, and failures are swallowed (analytics must never
break billing).
"""
import hashlib
import logging
from datetime import datetime, timezone

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)
_TIMEOUT = 8.0


def _sha256(v: str | None) -> str | None:
    return hashlib.sha256(v.strip().lower().encode()).hexdigest() if v else None


def fire_purchase_conversion(
    *, payment_id: str, amount_paise: int, currency: str,
    email: str | None, attribution: dict,
) -> None:
    """Best-effort Purchase conversion to Meta + Google. attribution is a plain dict
    with gclid/gbraid/wbraid/fbclid/fbp/fbc/landing_page (whatever was captured)."""
    value = round((amount_paise or 0) / 100, 2)
    try:
        _meta_capi(payment_id, value, currency, email, attribution)
    except Exception as e:
        logger.error("Meta CAPI conversion failed for payment %s: %s", payment_id, e)
    try:
        _google_ads(value, currency, attribution)
    except Exception as e:
        logger.error("Google Ads conversion failed for payment %s: %s", payment_id, e)


def _meta_capi(payment_id, value, currency, email, attr) -> None:
    if not (settings.META_PIXEL_ID and settings.META_CAPI_ACCESS_TOKEN):
        return
    user_data = {}
    em = _sha256(email)
    if em:
        user_data["em"] = [em]
    if attr.get("fbp"):
        user_data["fbp"] = attr["fbp"]
    if attr.get("fbc"):
        user_data["fbc"] = attr["fbc"]
    if not user_data:
        logger.info("Meta CAPI skipped (payment %s): no match keys", payment_id)
        return

    event = {
        "event_name": "Purchase",
        "event_time": int(datetime.now(timezone.utc).timestamp()),
        "event_id": f"evt_{payment_id}",  # same id the browser uses -> Meta dedupes
        "action_source": "website",
        "user_data": user_data,
        "custom_data": {"currency": currency, "value": value},
    }
    url = f"https://graph.facebook.com/{settings.META_CAPI_API_VERSION}/{settings.META_PIXEL_ID}/events"
    resp = httpx.post(
        url,
        params={"access_token": settings.META_CAPI_ACCESS_TOKEN},
        json={"data": [event]},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    logger.info("Meta CAPI Purchase sent for payment %s", payment_id)


def _google_ads(value, currency, attr) -> None:
    g = settings
    if not (g.GOOGLE_ADS_DEVELOPER_TOKEN and g.GOOGLE_ADS_CLIENT_ID and g.GOOGLE_ADS_CLIENT_SECRET
            and g.GOOGLE_ADS_REFRESH_TOKEN and g.GOOGLE_ADS_CUSTOMER_ID and g.GOOGLE_ADS_CONVERSION_ACTION_ID):
        return
    gclid, gbraid, wbraid = attr.get("gclid"), attr.get("gbraid"), attr.get("wbraid")
    if not (gclid or gbraid or wbraid):
        logger.info("Google Ads skipped: no click id")
        return

    # refresh token -> short-lived access token
    tok = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": g.GOOGLE_ADS_CLIENT_ID,
            "client_secret": g.GOOGLE_ADS_CLIENT_SECRET,
            "refresh_token": g.GOOGLE_ADS_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=_TIMEOUT,
    )
    tok.raise_for_status()
    access_token = tok.json()["access_token"]

    cid = g.GOOGLE_ADS_CUSTOMER_ID
    conversion = {
        "conversionAction": f"customers/{cid}/conversionActions/{g.GOOGLE_ADS_CONVERSION_ACTION_ID}",
        "conversionDateTime": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00:00"),
        "conversionValue": value,
        "currencyCode": currency,
    }
    # gclid preferred; gbraid/wbraid are the iOS/privacy-safe fallbacks.
    if gclid:
        conversion["gclid"] = gclid
    elif gbraid:
        conversion["gbraid"] = gbraid
    else:
        conversion["wbraid"] = wbraid

    headers = {
        "Authorization": f"Bearer {access_token}",
        "developer-token": g.GOOGLE_ADS_DEVELOPER_TOKEN,
    }
    if g.GOOGLE_ADS_LOGIN_CUSTOMER_ID:
        headers["login-customer-id"] = g.GOOGLE_ADS_LOGIN_CUSTOMER_ID

    url = f"https://googleads.googleapis.com/v17/customers/{cid}:uploadClickConversions"
    resp = httpx.post(
        url, headers=headers,
        json={"conversions": [conversion], "partialFailure": True},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    logger.info("Google Ads conversion uploaded (value=%s %s)", value, currency)
