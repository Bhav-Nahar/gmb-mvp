"""The OAuth callback must guarantee offline access.

Google only issues a refresh token when consent is actually granted; a repeat
authorization with prompt=select_account returns an access token and nothing else.
That left accounts looking connected while every scheduled sync failed with
"Refresh token missing" — the callback now re-requests consent once.
"""
from app.api.auth import _parse_oauth_state
from app.providers.gbp.provider import GBPProvider


def test_state_parsing_marks_the_consent_retry():
    csrf, invite, retried = _parse_oauth_state("abc123:")
    assert (csrf, invite, retried) == ("abc123", None, False)

    csrf, invite, retried = _parse_oauth_state("abc123:inv_tok")
    assert (csrf, invite, retried) == ("abc123", "inv_tok", False)

    # Second pass: the marker is set, so the callback must not redirect again.
    csrf, invite, retried = _parse_oauth_state("abc123:inv_tok:c")
    assert (csrf, invite, retried) == ("abc123", "inv_tok", True)

    # Invite tokens are secrets.token_urlsafe (no colons), but a stray one must not
    # be mistaken for the retry marker.
    _, invite, retried = _parse_oauth_state("abc123:inv:nope")
    assert retried is False


def test_consent_retry_url_asks_google_for_offline_consent():
    """prompt=consent is what actually makes Google re-issue a refresh token;
    access_type=offline alone is not enough on a repeat authorization."""
    url = GBPProvider.get_oauth_url("csrf:inv:c", prompt="consent")
    assert "prompt=consent" in url
    assert "access_type=offline" in url

    # The default login path stays on select_account — no extra consent screen for
    # users who already have a working refresh token.
    assert "prompt=select_account" in GBPProvider.get_oauth_url("csrf:")
