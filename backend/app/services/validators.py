import re
from typing import Any, Callable, Dict

def validate_text(value: Any) -> bool:
    return isinstance(value, str) and len(value.strip()) > 0

def validate_textarea(value: Any) -> bool:
    return isinstance(value, str)

def validate_boolean(value: Any) -> bool:
    return isinstance(value, bool)

def validate_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    pattern = re.compile(
        r'^(https?:\/\/)?'
        r'([\da-z\.-]+)\.([a-z\.]{2,6})'
        r'([\/\w \.-]*)*\/?$'
    )
    return bool(pattern.match(value))

def validate_business_hours(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    valid_days = {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"}
    for period in value:
        if not isinstance(period, dict):
            return False
        day = period.get("openDay")
        if not day or day.upper() not in valid_days:
            return False
        
        open_time = period.get("openTime")
        close_time = period.get("closeTime")
        if not isinstance(open_time, str) or not isinstance(close_time, str):
            return False
            
        time_pattern = re.compile(r'^\d{2}:\d{2}$')
        if not time_pattern.match(open_time) or not time_pattern.match(close_time):
            return False
    return True

def validate_structured_object(value: Any) -> bool:
    return isinstance(value, (dict, list))

def validate_select(value: Any) -> bool:
    # Basic check that the select value is a scalar representing the selection
    # or a structured select option containing name/displayName (for categories)
    if isinstance(value, dict):
        return "name" in value and "displayName" in value
    return isinstance(value, (str, int, float))

def validate_multiselect(value: Any) -> bool:
    # Multiselect values are represented as a list of options/keys
    if not isinstance(value, list):
        return False
    return all(isinstance(x, (str, int, float)) for x in value)

VALIDATOR_REGISTRY: Dict[str, Callable[[Any], bool]] = {
    "text": validate_text,
    "textarea": validate_textarea,
    "boolean": validate_boolean,
    "url": validate_url,
    "hours": validate_business_hours,
    "json": validate_structured_object,
    "select": validate_select,
    "multiselect": validate_multiselect,
}

def validate_field_value(field_type: str, value: Any) -> bool:
    validator = VALIDATOR_REGISTRY.get(field_type)
    if not validator:
        return True # Default to true if no validator is specified
    return validator(value)
