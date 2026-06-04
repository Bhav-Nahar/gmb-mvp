from typing import Any, Dict, Callable
from app.core.listing_fields import FIELD_MAP

def transform_identity(field_name: str, value: Any) -> Dict[str, Any]:
    config = FIELD_MAP.get(field_name)
    return {config.gbp_field_mask: value}

def transform_location_name(field_name: str, value: Any) -> Dict[str, Any]:
    return {"title": str(value)}

def transform_phone(field_name: str, value: Any) -> Dict[str, Any]:
    return {"phoneNumbers": {"primaryPhone": str(value)}}

def transform_url(field_name: str, value: Any) -> Dict[str, Any]:
    return {"websiteUri": str(value)}

def transform_description(field_name: str, value: Any) -> Dict[str, Any]:
    return {"profile": {"description": str(value)}}

def transform_primary_category(field_name: str, value: Any) -> Dict[str, Any]:
    category_name = value
    if isinstance(value, dict) and "name" in value:
        category_name = value["name"]
    return {"categories": {"primaryCategory": {"name": str(category_name)}}}

def transform_address(field_name: str, value: Any) -> Dict[str, Any]:
    return {"storefrontAddress": value}

def transform_business_hours(field_name: str, value: Any) -> Dict[str, Any]:
    formatted_periods = []
    for p in value:
        open_t = p.get("openTime")
        close_t = p.get("closeTime")
        
        if isinstance(open_t, str) and ":" in open_t:
            h, m = map(int, open_t.split(":"))
            open_t = {"hours": h, "minutes": m}
        if isinstance(close_t, str) and ":" in close_t:
            h, m = map(int, close_t.split(":"))
            close_t = {"hours": h, "minutes": m}
            
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
    "address": transform_address,
    "business_hours": transform_business_hours,
}

class PayloadTransformer:
    @staticmethod
    def to_gbp_payload(field_name: str, new_value: Any) -> Dict[str, Any]:
        config = FIELD_MAP.get(field_name)
        if not config or not config.gbp_field_mask:
            raise ValueError(f"No GBP field mask defined for field '{field_name}'")
            
        transformer_key = config.transformer
        transformer_fn = TRANSFORMER_REGISTRY.get(transformer_key, transform_identity)
        return transformer_fn(field_name, new_value)
