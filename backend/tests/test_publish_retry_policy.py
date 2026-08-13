"""One retry policy, one test. These used to be five pasted copies that disagreed:
the media-delete path never retried a Google 5xx and the shard path hardcoded its
own limit. If they drift apart again, this fails."""
import httpx
import pytest

from app.tasks import (
    PUBLISH_MAX_RETRIES,
    _google_error_code,
    _retry_countdown,
    _should_retry_publish,
)
from app.providers.gbp.auth import PermanentAuthError


def _http_error(status: int) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://mybusiness.googleapis.com/v1/x")
    return httpx.HTTPStatusError("boom", request=req,
                                 response=httpx.Response(status, request=req))


@pytest.mark.parametrize("exc, retryable", [
    (_http_error(500), True),    # Google's fault — the case the delete path used to drop
    (_http_error(503), True),
    (_http_error(429), True),
    (_http_error(400), False),   # our payload is wrong; retrying sends the same payload
    (_http_error(403), False),
    (_http_error(404), False),   # already gone
    (_http_error(409), False),
    (httpx.ConnectTimeout("timeout"), True),
    (PermanentAuthError("revoked"), False),
    (ValueError("bug in our code"), False),
])
def test_retry_decision(exc, retryable):
    assert _should_retry_publish(exc, attempt=0) is retryable


def test_attempts_are_capped():
    err = _http_error(500)
    assert _should_retry_publish(err, PUBLISH_MAX_RETRIES - 1) is True
    assert _should_retry_publish(err, PUBLISH_MAX_RETRIES) is False


def test_backoff_doubles():
    assert [_retry_countdown(n) for n in range(3)] == [60, 120, 240]


def test_error_code():
    assert _google_error_code(PermanentAuthError("x")) == "AUTH_REVOKED"
    assert _google_error_code(_http_error(400)) == "400"
    assert _google_error_code(ValueError("x")) is None
