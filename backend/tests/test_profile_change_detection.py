"""Change detection: does a Google-side edit produce exactly one activity entry?"""
from types import SimpleNamespace

from app.services import profile_change_service as pcs


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass


def _location(**overrides):
    base = dict(id=1, organization_id=1, location_name="Cafe", phone="+911111111111",
                website="https://a.example", address="1 Main St", primary_category="Cafe",
                additional_categories=[], additional_phones=[], description=None,
                business_hours=None, special_hours=None, open_info=None, service_area=None,
                is_verified=True, is_suspended=False,
                google_attributes=[], last_google_sync="2026-07-01T00:00:00Z")
    base.update(overrides)
    return SimpleNamespace(**base)


def test_phone_change_is_detected():
    db = FakeDB()
    changes = pcs.detect(db, _location(), {"phone": "+912222222222"})
    assert [c["field"] for c in changes] == ["phone"]
    assert changes[0]["old"] == "+911111111111"
    assert changes[0]["new"] == "+912222222222"
    assert len(db.added) == 1
    assert db.added[0].entity_type == "ProfileChange"


def test_identical_sync_logs_nothing():
    db = FakeDB()
    loc = _location()
    same = {"phone": loc.phone, "website": loc.website, "location_name": loc.location_name}
    assert pcs.detect(db, loc, same) == []
    assert db.added == []


def test_empty_and_none_are_the_same_value():
    db = FakeDB()
    assert pcs.detect(db, _location(description=None), {"description": ""}) == []
    assert pcs.detect(db, _location(additional_phones=[]), {"additional_phones": []}) == []
    assert db.added == []


def test_list_reordering_is_not_a_change():
    db = FakeDB()
    loc = _location(additional_categories=[{"displayName": "Bakery"}, {"displayName": "Deli"}])
    reordered = {"additional_categories": [{"displayName": "Deli"}, {"displayName": "Bakery"}]}
    assert pcs.detect(db, loc, reordered) == []


def test_our_own_published_edit_is_not_an_unauthorised_change():
    # Publishing patches Google without writing the value back onto our row, so the
    # next sync sees a difference. It is ours, and must not be reported.
    db = FakeDB()
    assert pcs.detect(db, _location(), {"phone": "+912222222222"},
                      skip_fields={"phone"}) == []
    assert db.added == []
    # A different field still gets reported while that edit is in the window.
    assert [c["field"] for c in pcs.detect(db, _location(), {"website": "https://b.example"},
                                           skip_fields={"phone"})] == ["website"]


def test_unwatched_and_absent_fields_are_ignored():
    db = FakeDB()
    # average_rating is not watched; store_code is absent from the payload entirely.
    assert pcs.detect(db, _location(), {"average_rating": 4.9}) == []
    assert db.added == []


class FakeQueryDB(FakeDB):
    """FakeDB whose query() replays previously-logged activity rows, so the
    dedup-via-activity-log path can be exercised without a real session."""

    def __init__(self, history=()):
        super().__init__()
        self.history = list(history)

    def query(self, _model):
        return self

    def filter(self, *_a):
        return self

    def order_by(self, *_a):
        return self

    def limit(self, _n):
        return self

    def all(self):
        # filter() above is a no-op, so emulate the one filter whose behaviour the
        # dedup logic depends on: resolved entries are excluded in SQL.
        return [r for r in self.history if not (r.payload or {}).get("resolved")]


def _logged(field, new):
    return SimpleNamespace(payload={"field": field, "new": new, "source": "google"})


def _blob(diff_mask, live=None):
    return {"diffMask": diff_mask, "location": live or {}}


def test_google_side_override_is_reported():
    db = FakeQueryDB()
    changes = pcs.detect_google_updates(db, _location(), _blob(
        "phoneNumbers.primaryPhone,regularHours",
        {"phoneNumbers": {"primaryPhone": "+913333333333"}, "regularHours": {"periods": []}}))
    assert sorted(c["field"] for c in changes) == ["phoneNumbers", "regularHours"]
    assert changes[0]["source"] == "google"
    assert db.added[0].action.startswith("Google changed")


def test_unresolved_divergence_is_not_relogged_every_week():
    live = {"primaryPhone": "+913333333333"}
    db = FakeQueryDB([_logged("phoneNumbers", live)])
    assert pcs.detect_google_updates(db, _location(), _blob("phoneNumbers", {"phoneNumbers": live})) == []
    assert db.added == []


def test_divergence_changing_value_is_relogged():
    db = FakeQueryDB([_logged("phoneNumbers", {"primaryPhone": "+913333333333"})])
    changes = pcs.detect_google_updates(
        db, _location(), _blob("phoneNumbers", {"phoneNumbers": {"primaryPhone": "+914444444444"}}))
    assert len(changes) == 1


def test_google_reapplying_a_resolved_change_is_reported_again():
    # The user already accepted/rejected this one. If Google does it again, it is new.
    live = {"primaryPhone": "+913333333333"}
    resolved = _logged("phoneNumbers", live)
    resolved.payload["resolved"] = "accepted"
    db = FakeQueryDB([resolved])
    changes = pcs.detect_google_updates(db, _location(), _blob("phoneNumbers", {"phoneNumbers": live}))
    assert len(changes) == 1
    assert len(db.added) == 1


def test_no_diffmask_means_google_agrees():
    db = FakeQueryDB()
    assert pcs.detect_google_updates(db, _location(), _blob("")) == []
    assert db.added == []


def _attr(name, values):
    return {"name": name, "valueType": "BOOL", "values": values}


def test_attribute_added_changed_and_removed():
    db = FakeQueryDB()
    loc = _location(google_attributes=[_attr("attributes/has_wifi", [True]),
                                       _attr("attributes/pay_upi", [True])])
    new = [_attr("attributes/has_wifi", [False]),          # changed
           _attr("attributes/wheelchair_accessible", [True])]  # added; pay_upi removed
    changes = pcs.detect_attribute_changes(db, loc, new)
    by_id = {c["field"]: c for c in changes}
    assert set(by_id) == {"attributes/has_wifi", "attributes/pay_upi",
                          "attributes/wheelchair_accessible"}
    assert by_id["attributes/pay_upi"]["new"] is None            # removal
    assert by_id["attributes/wheelchair_accessible"]["old"] is None  # addition
    assert by_id["attributes/has_wifi"]["new"] == [False]
    assert all(c["source"] == "attribute" for c in changes)


def test_attribute_reordering_is_not_a_change():
    db = FakeQueryDB()
    a, b = _attr("attributes/has_wifi", [True]), _attr("attributes/pay_upi", [True])
    loc = _location(google_attributes=[a, b])
    assert pcs.detect_attribute_changes(db, loc, [b, a]) == []
    assert db.added == []


def test_first_run_with_no_baseline_reports_nothing():
    """Regression: the first sync after deploy has no stored attributes, so every
    attribute already on the profile would otherwise be announced as newly added."""
    db = FakeQueryDB()
    existing_profile = [_attr("attributes/has_wifi", [True]),
                        _attr("attributes/is_women_owned", [True]),
                        _attr("attributes/pay_upi", [True])]
    # last_google_sync is NOT a baseline signal — three unrelated paths write it, so
    # it is routinely set on locations whose attributes were never stored.
    for empty in ([], None):
        for synced_at in (None, "2026-07-01T00:00:00Z"):
            loc = _location(google_attributes=empty, last_google_sync=synced_at)
            assert pcs.detect_attribute_changes(db, loc, existing_profile) == []
    assert db.added == []


def test_attribute_label_falls_back_to_prettified_id():
    db = FakeQueryDB()
    db.history = []  # no definitions rows -> fallback path
    loc = _location(google_attributes=[_attr("attributes/has_wifi", [True])])
    changes = pcs.detect_attribute_changes(
        db, loc, [_attr("attributes/has_wifi", [True]),
                  _attr("attributes/has_wheelchair_accessible_entrance", [True])])
    assert changes[0]["label"] == "Has wheelchair accessible entrance"


def test_google_field_maps_to_an_editable_column():
    """accept/reject depends on every reported field resolving to a real column."""
    from app.core.listing_fields import GBP_MASK_TO_FIELD, FIELD_MAP
    for mask, column in GBP_MASK_TO_FIELD.items():
        assert column in FIELD_MAP, f"{mask} -> {column} is not an editable field"
    # The ones an owner is most likely to act on must be resolvable.
    for mask in ("phoneNumbers", "regularHours", "websiteUri", "title", "storefrontAddress"):
        assert mask in GBP_MASK_TO_FIELD


def test_accepting_reads_googles_value_through_the_sync_mapper():
    """Accept converts Google's raw sub-object into our column shape."""
    from app.providers.gbp.mapper import GBPLocationMapper
    from app.providers.gbp.schemas import GBPLocationRaw
    mapped = GBPLocationMapper.to_model(
        GBPLocationRaw(name="locations/1", phoneNumbers={"primaryPhone": "+919999999999"}))
    assert mapped.phone == "+919999999999"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
