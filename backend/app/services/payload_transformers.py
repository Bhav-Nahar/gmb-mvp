from typing import Any, Dict, Callable, List, Optional
from app.core.listing_fields import FIELD_MAP

# NOTE: every transformer accepts an optional `location` argument so that
# transformers whose GBP field mask is *atomic* (e.g. "categories", which
# replaces primaryCategory AND additionalCategories in a single PATCH) can
# merge the edited value with the location's current persisted state. Most
# transformers ignore it.

def transform_identity(field_name: str, value: Any, location: Any = None) -> Dict[str, Any]:
    config = FIELD_MAP.get(field_name)
    if config is None:
        raise ValueError(f"Unknown field '{field_name}': not found in FIELD_MAP")
    if config.gbp_field_mask is None:
        raise ValueError(f"Field '{field_name}' has no gbp_field_mask defined")
    return {config.gbp_field_mask: value}

def transform_location_name(field_name: str, value: Any, location: Any = None) -> Dict[str, Any]:
    return {"title": str(value)}

def _existing_additional_phones(location: Any) -> List[str]:
    raw = getattr(location, "additional_phones", None) or [] if location is not None else []
    return [str(p) for p in raw if p]

def transform_phone(field_name: str, value: Any, location: Any = None) -> Dict[str, Any]:
    # "phoneNumbers" mask is atomic — preserve additionalPhones so editing the
    # primary number doesn't wipe the secondaries.
    phones: Dict[str, Any] = {"primaryPhone": str(value)}
    extra = _existing_additional_phones(location)
    if extra:
        phones["additionalPhones"] = extra
    return {"phoneNumbers": phones}

def transform_additional_phones(field_name: str, value: Any, location: Any = None) -> Dict[str, Any]:
    if value is None:
        value = []
    if not isinstance(value, list):
        raise ValueError(f"additional_phones expects a list, got {type(value).__name__}")
    phones: Dict[str, Any] = {"additionalPhones": [str(p) for p in value if p]}
    # Preserve the primary so the atomic "phoneNumbers" PATCH doesn't clear it.
    primary = getattr(location, "phone", None) if location else None
    if primary:
        phones["primaryPhone"] = str(primary)
    return {"phoneNumbers": phones}

def transform_special_hours(field_name: str, value: Any, location: Any = None) -> Dict[str, Any]:
    # value is already in GBP shape: {"specialHourPeriods": [...]}
    if not value:
        return {"specialHours": {"specialHourPeriods": []}}
    if isinstance(value, list):
        value = {"specialHourPeriods": value}
    return {"specialHours": value}

def transform_service_items(field_name: str, value: Any, location: Any = None) -> Dict[str, Any]:
    if value is None:
        value = []
    if not isinstance(value, list):
        raise ValueError(f"service_items expects a list, got {type(value).__name__}")
    return {"serviceItems": value}

def transform_open_info(field_name: str, value: Any, location: Any = None) -> Dict[str, Any]:
    if isinstance(value, dict):
        out: Dict[str, Any] = {"status": value.get("status")}
        if value.get("openingDate"):
            out["openingDate"] = value["openingDate"]
    else:
        out = {"status": str(value)}
    return {"openInfo": out}

def transform_url(field_name: str, value: Any, location: Any = None) -> Dict[str, Any]:
    return {"websiteUri": str(value)}

def transform_description(field_name: str, value: Any, location: Any = None) -> Dict[str, Any]:
    return {"profile": {"description": str(value)}}

def _category_name(value: Any) -> str:
    """Extract a 'categories/gcid:...' resource name from a string or {name,...} dict."""
    name = value.get("name") if isinstance(value, dict) else value
    if not isinstance(name, str) or not name:
        raise ValueError(f"Expected a category resource name string, got: {value!r}")
    return name

def _existing_additional_payload(location: Any) -> List[Dict[str, str]]:
    """Build additionalCategories payload from the location's currently stored secondaries."""
    raw = getattr(location, "additional_categories", None) or [] if location is not None else []
    out: List[Dict[str, str]] = []
    for c in raw:
        name = c.get("name") if isinstance(c, dict) else c
        if isinstance(name, str) and name:
            out.append({"name": name})
    return out

def transform_primary_category(field_name: str, value: Any, location: Any = None) -> Dict[str, Any]:
    # The "categories" mask is atomic — preserve existing additionalCategories so
    # changing the primary doesn't wipe the secondaries on Google.
    categories: Dict[str, Any] = {"primaryCategory": {"name": _category_name(value)}}
    additional = _existing_additional_payload(location)
    if additional:
        categories["additionalCategories"] = additional
    return {"categories": categories}

def transform_additional_categories(field_name: str, value: Any, location: Any = None) -> Dict[str, Any]:
    # value is the new full set of secondaries: list of strings or {name, displayName} dicts.
    if value is None:
        value = []
    if not isinstance(value, list):
        raise ValueError(
            f"additional_categories expects a list, got {type(value).__name__}: {value!r}"
        )
    additional = [{"name": _category_name(c)} for c in value]
    categories: Dict[str, Any] = {"additionalCategories": additional}
    # Preserve the primary so the atomic "categories" PATCH doesn't clear it.
    primary_name = getattr(location, "google_category_resource_name", None) if location else None
    if primary_name:
        categories["primaryCategory"] = {"name": primary_name}
    return {"categories": categories}

def transform_address(field_name: str, value: Any, location: Any = None) -> Dict[str, Any]:
    return {"storefrontAddress": value}

def _parse_time_string(time_str: str) -> Dict[str, int]:
    """Parse a time string of the form HH:MM or HH:MM:SS into {hours, minutes}."""
    parts = time_str.split(":")
    if len(parts) < 2:
        raise ValueError(f"Invalid time string (expected HH:MM or HH:MM:SS): {time_str!r}")
    try:
        h = int(parts[0])
        m = int(parts[1])
    except ValueError:
        raise ValueError(f"Invalid time string (non-integer components): {time_str!r}")
    if not (0 <= h <= 23):
        raise ValueError(f"Hour out of range [0-23] in time string: {time_str!r}")
    if not (0 <= m <= 59):
        raise ValueError(f"Minute out of range [0-59] in time string: {time_str!r}")
    return {"hours": h, "minutes": m}

def transform_business_hours(field_name: str, value: Any, location: Any = None) -> Dict[str, Any]:
    if value is None:
        return {"regularHours": {"periods": []}}
    if not hasattr(value, "__iter__"):
        raise ValueError(
            f"transform_business_hours expects an iterable of period dicts, got {type(value).__name__}"
        )
    formatted_periods = []
    for p in value:
        open_t = p.get("openTime")
        close_t = p.get("closeTime")

        if isinstance(open_t, str) and ":" in open_t:
            open_t = _parse_time_string(open_t)
        if isinstance(close_t, str) and ":" in close_t:
            close_t = _parse_time_string(close_t)

        formatted_periods.append({
            "openDay": p.get("openDay"),
            "openTime": open_t,
            "closeDay": p.get("closeDay"),
            "closeTime": close_t
        })
    return {"regularHours": {"periods": formatted_periods}}

# Registry mapping
TRANSFORMER_REGISTRY: Dict[str, Callable[[str, Any], Dict[str, Any]]] = {
    "identity_transform": transform_identity,
    "location_name": transform_location_name,
    "phone": transform_phone,
    "url": transform_url,
    "description": transform_description,
    "primary_category": transform_primary_category,
    "additional_categories": transform_additional_categories,
    "additional_phones": transform_additional_phones,
    "special_hours": transform_special_hours,
    "service_items": transform_service_items,
    "open_info": transform_open_info,
    "address": transform_address,
    "business_hours": transform_business_hours,
}

class PayloadTransformer:
    @staticmethod
    def to_gbp_payload(field_name: str, new_value: Any, location: Any = None) -> Dict[str, Any]:
        config = FIELD_MAP.get(field_name)
        if not config or not config.gbp_field_mask:
            raise ValueError(f"No GBP field mask defined for field '{field_name}'")

        transformer_key = config.transformer
        transformer_fn = TRANSFORMER_REGISTRY.get(transformer_key, transform_identity)
        return transformer_fn(field_name, new_value, location)
