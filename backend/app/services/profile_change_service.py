"""Detect third-party changes to a Google Business Profile.

Anyone with access to the listing — a staff member in the GBP app, a Google
"suggested edit", Maps user feedback — can change a live profile without going
through us. We already refetch every location on each sync, so the cheapest
possible detector is: compare what Google just returned against what we stored
last time, and log the differences to the activity feed.
"""
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.location import Location
from app.services.activity_log_service import ActivityLogService

logger = logging.getLogger(__name__)

ENTITY_TYPE = "ProfileChange"

# Location attribute -> label shown in the activity feed. Only fields a business
# owner would actually care about seeing changed; internal/derived columns
# (ratings, sync bookkeeping, labels, store_code) are deliberately excluded.
WATCHED_FIELDS: dict[str, str] = {
    "location_name": "Business name",
    "phone": "Phone number",
    "additional_phones": "Additional phones",
    "website": "Website",
    "address": "Address",
    "primary_category": "Primary category",
    "additional_categories": "Additional categories",
    "description": "Description",
    "business_hours": "Opening hours",
    "special_hours": "Special hours",
    "open_info": "Open/closed status",
    "service_area": "Service area",
    "is_verified": "Verified status",
    "is_suspended": "Suspended status",
}


# GBP API field name (as it appears in getGoogleUpdated's diffMask) -> label.
GOOGLE_FIELD_LABELS: dict[str, str] = {
    "title": "Business name",
    "phoneNumbers": "Phone number",
    "websiteUri": "Website",
    "storefrontAddress": "Address",
    "categories": "Categories",
    "regularHours": "Opening hours",
    "specialHours": "Special hours",
    "moreHours": "More hours",
    "openInfo": "Open/closed status",
    "serviceArea": "Service area",
    "serviceItems": "Services",
    "profile": "Description",
    "latlng": "Map pin",
}


def _normalize(value: Any) -> Any:
    """Make values comparable: empty string/list/dict and None are all "unset"."""
    if value is None or value == "" or value == [] or value == {}:
        return None
    if isinstance(value, list):
        # Google reorders list payloads (categories, phones) without meaning it.
        # ponytail: sort by repr — fine for these small, flat-ish lists.
        return sorted(value, key=repr)
    return value


def detect(db: Session, location: Location, new_values: dict[str, Any]) -> list[dict]:
    """Log one activity entry per watched field that Google now reports differently.

    Call this BEFORE writing `new_values` onto `location`. Returns the changes
    found (mostly for tests/logging). Staged only — the caller commits.
    """
    changes = []
    for field, label in WATCHED_FIELDS.items():
        if field not in new_values:
            continue
        old = _normalize(getattr(location, field, None))
        new = _normalize(new_values[field])
        if old == new:
            continue
        changes.append({"field": field, "label": label, "old": old, "new": new})

    for change in changes:
        # ponytail: we can't tell WHO changed it — the GBP API doesn't say. If a
        # change we published ourselves shows up here it's still true, just
        # redundant; suppress via LocationEdit correlation only if users complain.
        ActivityLogService.log(
            db,
            organization_id=location.organization_id,
            location_id=location.id,
            entity_type=ENTITY_TYPE,
            entity_id=location.id,
            action=f"{change['label']} changed on Google",
            payload=change,
        )
    if changes:
        logger.info(
            "profile_change: location=%s fields=%s",
            location.id,
            [c["field"] for c in changes],
        )
    return changes


def _attr_map(attributes: Any) -> dict[str, Any]:
    """[{name, values}, ...] -> {attribute_id: values}. Order-independent."""
    out: dict[str, Any] = {}
    for attr in attributes or []:
        if isinstance(attr, dict) and attr.get("name"):
            out[attr["name"]] = _normalize(attr.get("values"))
    return out


def _attr_labels(db: Session, attribute_ids: list[str]) -> dict[str, str]:
    """Real display names for attribute ids, falling back to a prettified id."""
    labels = {}
    try:
        from app.models.gbp_attribute_definition import GbpAttributeDefinition
        rows = (
            db.query(GbpAttributeDefinition.attribute_id, GbpAttributeDefinition.display_name)
            .filter(GbpAttributeDefinition.attribute_id.in_(attribute_ids))
            .all()
        )
        labels = {aid: name for aid, name in rows if name}
    except Exception:
        logger.warning("could not load attribute display names", exc_info=True)
    # "attributes/has_wheelchair_accessible_entrance" -> "Has wheelchair accessible entrance"
    return {aid: labels.get(aid) or aid.split("/")[-1].replace("_", " ").capitalize()
            for aid in attribute_ids}


def detect_attribute_changes(db: Session, location: Location, new_attributes: Any) -> list[dict]:
    """Log third-party changes to the listing's attributes (wifi, wheelchair access,
    payment methods...).

    Attributes sync on their own path, not with the location record, so they need
    their own diff. Compared per attribute rather than as one list — a whole-list
    diff would report "50 objects changed to 50 objects" every time Google reorders
    them. Call BEFORE writing `new_attributes` onto the location.
    """
    old = _attr_map(location.google_attributes)
    new = _attr_map(new_attributes)

    # No stored attributes means no baseline, and you cannot detect a change against
    # nothing — reporting the difference announces every attribute already on the
    # profile as newly "added", which is what the first run after deploy does.
    # This run only establishes the baseline.
    #
    # ponytail: deliberately does NOT try to tell "never fetched" from "genuinely had
    # none" — `last_google_sync` looked like that signal but three unrelated paths
    # write it, so it was set on locations whose attributes had never been stored.
    # Nothing else in the schema distinguishes the two cases. Cost of the simple rule:
    # the very first attribute an empty profile ever gains goes unreported. Cheap,
    # versus 30 false rows per location.
    if not old:
        logger.info("attribute_change: location=%s baseline established (%s attrs)", location.id, len(new))
        return []

    changed_ids = [aid for aid in set(old) | set(new) if old.get(aid) != new.get(aid)]
    if not changed_ids:
        return []

    labels = _attr_labels(db, changed_ids)
    changes = [{"field": aid, "label": labels[aid], "old": old.get(aid),
                "new": new.get(aid), "source": "attribute"}
               for aid in sorted(changed_ids)]

    for change in changes:
        if change["new"] is None:
            action = f"{change['label']} removed from your profile"
        elif change["old"] is None:
            action = f"{change['label']} added to your profile"
        else:
            action = f"{change['label']} changed on your profile"
        ActivityLogService.log(
            db,
            organization_id=location.organization_id,
            location_id=location.id,
            entity_type=ENTITY_TYPE,
            entity_id=location.id,
            action=action,
            payload=change,
        )
    logger.info("attribute_change: location=%s attrs=%s", location.id, changed_ids)
    return changes


def google_updated_fields(blob: Optional[dict]) -> dict[str, Any]:
    """{top-level field -> Google's live value} from a getGoogleUpdated response."""
    blob = blob or {}
    live = blob.get("location") or {}
    fields = {}
    for path in (blob.get("diffMask") or "").split(","):
        # diffMask paths can be nested ("phoneNumbers.primaryPhone"); we report at
        # the top level, which is the granularity the labels and the UI use.
        root = path.strip().split(".")[0]
        if root:
            fields[root] = live.get(root)
    return fields


def _already_reported(db: Session, location_id: int) -> dict[str, Any]:
    """{field -> last value we reported} for Google-sourced entries on this location."""
    rows = (
        db.query(ActivityLog)
        .filter(
            ActivityLog.location_id == location_id,
            ActivityLog.entity_type == ENTITY_TYPE,
            # Filter in SQL, not after the limit. All three detection paths write
            # ProfileChange rows for the same location, so a burst of attribute rows
            # would otherwise fill the window and push every google row out of it —
            # silently re-reporting divergences the user has already seen.
            ActivityLog.payload["source"].astext == "google",
        )
        # created_at is the transaction timestamp, so every row from one sync ties.
        # id breaks the tie deterministically.
        .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
        .limit(50)
        .all()
    )
    seen: dict[str, Any] = {}
    for row in rows:  # newest first — first value wins
        payload = row.payload or {}
        if payload.get("field") not in seen:
            seen[payload["field"]] = payload.get("new")
    return seen


def detect_google_updates(db: Session, location: Location, blob: Optional[dict]) -> list[dict]:
    """Log when Google's live listing diverges from the merchant's version.

    `locations.list` only ever returns the merchant's version, so a Google-applied
    change (a Maps user's suggested edit, Google's own crawl) is invisible to
    `detect()` above. Only `getGoogleUpdated` reports it.

    That divergence is a *state*, not an event — it persists until the owner accepts
    or rejects it, so re-logging on every check would spam the feed. We skip fields
    already reported at the same value. Dedup reads back from the activity log rather
    than a new column, which costs one indexed query per location per check.
    """
    previous = _already_reported(db, location.id)

    changes = []
    for field, live_value in google_updated_fields(blob).items():
        normalized = _normalize(live_value)
        if field in previous and _normalize(previous[field]) == normalized:
            continue  # already reported, still unresolved
        changes.append({"field": field, "label": GOOGLE_FIELD_LABELS.get(field, field),
                        "old": None, "new": normalized, "source": "google"})

    for change in changes:
        ActivityLogService.log(
            db,
            organization_id=location.organization_id,
            location_id=location.id,
            entity_type=ENTITY_TYPE,
            entity_id=location.id,
            action=f"Google changed {change['label']} on your live listing",
            payload=change,
        )
    if changes:
        logger.info(
            "google_update: location=%s fields=%s",
            location.id,
            [c["field"] for c in changes],
        )
    return changes
