"""Convert between Google's payload shape and the listing-editor's value shape.

Accepting or rejecting a Google update means publishing a value through the normal
LocationEdit pipeline. That pipeline validates against the *editor* shape, which is
not the shape the sync stores or the shape Google returns:

    field            Google / stored                     editor expects
    ---------------  ----------------------------------  ------------------------
    storefrontAddress dict / JSON-encoded string          dict
    regularHours     {"hours":9,"minutes":30} TimeOfDay   "09:30" strings
    categories       {"primaryCategory":{name,display}}   {name, displayName}
    phoneNumbers     {"primaryPhone": "..."}              "..."

Getting this wrong is silent: the edit is either refused (409) or published to Google
in a shape it rejects. Everything here is explicit per field for that reason.
"""
import json
from typing import Any, Optional

from app.models.location import Location


class Unresolvable(Exception):
    """Carries a message safe to show the user when a value can't be published."""


def _hhmm(value: Any) -> Optional[str]:
    """Google TimeOfDay ({"hours":9,"minutes":30}) -> "09:30"."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return f"{int(value.get('hours') or 0):02d}:{int(value.get('minutes') or 0):02d}"
    return None


def _periods(periods: Any) -> list:
    out = []
    for period in periods or []:
        if not isinstance(period, dict):
            raise Unresolvable("Google sent opening hours in a format we can't publish yet.")
        open_time, close_time = _hhmm(period.get("openTime")), _hhmm(period.get("closeTime"))
        if not open_time or not close_time:
            # 24-hour and closed-all-day periods omit the times; the editor has no
            # representation for them, so publishing would silently drop the day.
            raise Unresolvable(
                "These hours include an all-day or 24-hour entry, which we can't publish "
                "automatically yet. Edit the hours directly instead."
            )
        out.append({**period, "openTime": open_time, "closeTime": close_time})
    return out


def from_google(mask: str, value: Any) -> Any:
    """Google's sub-object for `mask` -> a value the edit pipeline will accept."""
    if value is None:
        raise Unresolvable(
            "Google removed this value. Clearing a field isn't supported here — "
            "edit the field directly instead."
        )
    if mask == "title":
        return value
    if mask == "websiteUri":
        return value
    if mask == "phoneNumbers":
        phone = value.get("primaryPhone") if isinstance(value, dict) else value
        if not phone:
            raise Unresolvable("Google's phone number is empty.")
        return phone
    if mask == "profile":
        description = value.get("description") if isinstance(value, dict) else value
        if not description:
            raise Unresolvable("Google's description is empty.")
        return description
    if mask == "categories":
        primary = (value or {}).get("primaryCategory") if isinstance(value, dict) else None
        if not isinstance(primary, dict) or not primary.get("name"):
            raise Unresolvable("Google's category is missing its identifier.")
        return {"name": primary["name"], "displayName": primary.get("displayName") or primary["name"]}
    if mask == "storefrontAddress":
        if not isinstance(value, dict):
            raise Unresolvable("Google's address is not in a format we can publish.")
        return value
    if mask == "regularHours":
        return _periods(value.get("periods") if isinstance(value, dict) else value)
    if mask in ("openInfo", "specialHours", "serviceItems"):
        return value
    raise Unresolvable(f"'{mask}' can't be published from here.")


def from_stored(field_name: str, location: Location) -> Any:
    """Our stored column value -> a value the edit pipeline will accept.

    Used by "reject", which re-asserts what we already have over Google's version.
    """
    value = getattr(location, field_name, None)
    if value is None or value == "" or value == []:
        raise Unresolvable(
            "You have no value of your own for this field, so there's nothing to restore. "
            "Set it directly instead."
        )
    if field_name == "address":
        # Stored JSON-encoded (gbp/mapper.py); the editor wants the object back.
        if isinstance(value, str):
            try:
                return json.loads(value)
            except ValueError:
                raise Unresolvable("Your stored address can't be read back for publishing.")
        return value
    if field_name == "business_hours":
        return _periods(value)
    if field_name == "primary_category":
        # Stored as a display name; publishing needs Google's resource name too.
        # gbp_raw holds the merchant's own version of the listing — the exact thing
        # a reject restores — so it's the right fallback when the dedicated column
        # was never populated.
        resource = location.google_category_resource_name
        if not resource:
            raw = location.gbp_raw if isinstance(location.gbp_raw, dict) else {}
            primary = (raw.get("categories") or {}).get("primaryCategory") or {}
            resource = primary.get("name")
        if not resource:
            raise Unresolvable(
                "We don't have Google's identifier for your category, so it can't be "
                "republished. Set the category directly instead."
            )
        return {"name": resource, "displayName": value}
    return value
