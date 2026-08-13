"""The reviewer login is a door in the front of a production app.

These tests exist because every one of them is a way that door could be left
wider than intended.
"""
import pytest

from app.api.auth_demo import hash_password, verify_password


def test_password_round_trips():
    stored = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", stored) is True


def test_wrong_password_rejected():
    stored = hash_password("correct horse battery staple")
    assert verify_password("Correct horse battery staple", stored) is False
    assert verify_password("", stored) is False


def test_same_password_hashes_differently_each_time():
    """Per-hash salt. Without it, two accounts sharing a password would be
    visibly identical in the config, and one cracked hash would break both."""
    a = hash_password("same password")
    b = hash_password("same password")
    assert a != b
    assert verify_password("same password", a)
    assert verify_password("same password", b)


def test_plaintext_never_appears_in_the_hash():
    stored = hash_password("hunter2-and-then-some")
    assert "hunter2" not in stored


@pytest.mark.parametrize("garbage", ["", "not-a-hash", "scrypt$onlyonepart", "bcrypt$salt$key"])
def test_malformed_stored_hash_denies_rather_than_crashes(garbage):
    # A misconfigured env var must fail closed, not raise a 500 that reveals
    # the endpoint is misconfigured.
    assert verify_password("anything", garbage) is False
