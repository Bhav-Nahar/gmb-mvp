"""Accept/reject shape conversion.

These four failed in production shapes before the resolver existed: Google's payload,
our stored column, and the edit pipeline's validator each want a different shape, and
getting it wrong is silent — a 409 the user can't act on, or a PATCH Google rejects.
"""
from types import SimpleNamespace

import pytest

from app.services import google_update_resolver as r
from app.services.validators import validate_field_value
from app.core.listing_fields import FIELD_MAP, GBP_MASK_TO_FIELD


def _loc(**kw):
    base = dict(location_name="Shop", phone="+911111111111", website="https://a.example",
                description="desc", address='{"locality":"Mumbai","regionCode":"IN"}',
                business_hours=[{"openDay": "MONDAY", "closeDay": "MONDAY",
                                 "openTime": {"hours": 10, "minutes": 30},
                                 "closeTime": {"hours": 20, "minutes": 0}}],
                primary_category="Jewellery Store", google_category_resource_name=None,
                open_info={"status": "OPEN"}, special_hours=None, service_items=[{"x": 1}],
                gbp_raw={"categories": {"primaryCategory": {"name": "categories/gcid:jewelry_store"}}})
    base.update(kw)
    return SimpleNamespace(**base)


def _valid(mask, value):
    """Would the edit pipeline actually accept this value?"""
    return validate_field_value(FIELD_MAP[GBP_MASK_TO_FIELD[mask]].field_type, value)


# ── accept: Google's shape -> a value the pipeline validates ──────────────────
@pytest.mark.parametrize("mask,google_value", [
    ("title", "New Name"),
    ("websiteUri", "https://b.example"),
    ("phoneNumbers", {"primaryPhone": "+912222222222"}),
    ("profile", {"description": "New description"}),
    ("categories", {"primaryCategory": {"name": "categories/gcid:cafe", "displayName": "Cafe"}}),
    ("storefrontAddress", {"locality": "Pune", "regionCode": "IN"}),
    ("regularHours", {"periods": [{"openDay": "MONDAY", "closeDay": "MONDAY",
                                   "openTime": {"hours": 9, "minutes": 5},
                                   "closeTime": {"hours": 17, "minutes": 0}}]}),
])
def test_accept_produces_a_value_the_pipeline_accepts(mask, google_value):
    value = r.from_google(mask, google_value)
    assert _valid(mask, value), f"{mask} -> {value!r} would be rejected by the edit pipeline"


def test_accept_converts_google_timeofday_to_hhmm():
    periods = r.from_google("regularHours", {"periods": [
        {"openDay": "MONDAY", "closeDay": "MONDAY",
         "openTime": {"hours": 9, "minutes": 5}, "closeTime": {"hours": 17, "minutes": 0}}]})
    assert periods[0]["openTime"] == "09:05" and periods[0]["closeTime"] == "17:00"


def test_accept_keeps_category_resource_name():
    """Publishing a category needs Google's id — a display name alone PATCHes garbage."""
    value = r.from_google("categories", {"primaryCategory": {
        "name": "categories/gcid:cafe", "displayName": "Cafe"}})
    assert value["name"] == "categories/gcid:cafe"


# ── reject: our stored shape -> a value the pipeline validates ────────────────
@pytest.mark.parametrize("mask", ["title", "websiteUri", "phoneNumbers", "profile",
                                  "categories", "storefrontAddress", "regularHours"])
def test_reject_produces_a_value_the_pipeline_accepts(mask):
    value = r.from_stored(GBP_MASK_TO_FIELD[mask], _loc())
    assert _valid(mask, value), f"{mask} -> {value!r} would be rejected by the edit pipeline"


def test_reject_parses_the_json_encoded_address_back_to_an_object():
    assert r.from_stored("address", _loc())["locality"] == "Mumbai"


def test_reject_falls_back_to_gbp_raw_for_the_category_id():
    """The dedicated column is often NULL; gbp_raw is the merchant's own version."""
    value = r.from_stored("primary_category", _loc(google_category_resource_name=None))
    assert value["name"] == "categories/gcid:jewelry_store"
    assert value["displayName"] == "Jewellery Store"


# ── unresolvable cases must be honest, not a confusing 409 ───────────────────
def test_removal_is_refused_with_an_explanation():
    with pytest.raises(r.Unresolvable, match="Clearing a field"):
        r.from_google("phoneNumbers", None)


def test_restoring_a_value_we_never_had_is_refused():
    with pytest.raises(r.Unresolvable, match="nothing to restore"):
        r.from_stored("website", _loc(website=None))


def test_all_day_hours_are_refused_rather_than_silently_dropped():
    with pytest.raises(r.Unresolvable, match="all-day or 24-hour"):
        r.from_google("regularHours", {"periods": [{"openDay": "MONDAY", "closeDay": "MONDAY"}]})


def test_every_detected_field_can_be_resolved():
    """A field we detect but cannot resolve becomes a permanently stuck row."""
    from app.providers.gbp.provider import GBPProvider
    detected = {f for f in GBPProvider.GOOGLE_UPDATED_READ_MASK.split(",") if f != "name"}
    assert detected <= set(GBP_MASK_TO_FIELD), (
        f"detected but unresolvable: {detected - set(GBP_MASK_TO_FIELD)}")
