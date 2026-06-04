import urllib.parse
from typing import Optional

def _clean_value(value: str) -> str:
    """
    Cleans a string value by stripping spaces, converting to lowercase,
    and replacing spaces with underscores.
    """
    if not value:
        return ""
    return value.strip().lower().replace(" ", "_")

def generate_utm_link(
    base_url: str,
    location_id: str,
    touchpoint: str
) -> Optional[str]:
    """
    Generates a deterministic UTM tracking link for a given base URL, location, and touchpoint.
    Safely parses the URL, preserves existing non-UTM query params, overwrites UTM params,
    and normalizes values to lowercase.
    """
    if not base_url:
        return None

    parsed = urllib.parse.urlparse(base_url)
    
    # parse existing query parameters while preserving order and duplicate keys
    query_params = urllib.parse.parse_qsl(parsed.query)
    
    cleaned_source = "google"
    cleaned_medium = "organic"
    cleaned_campaign = f"gbp_{_clean_value(str(location_id))}"
    cleaned_content = _clean_value(str(touchpoint))
    
    new_params = []
    utm_keys = {"utm_source", "utm_medium", "utm_campaign", "utm_content"}
    
    # Preserve existing non-UTM parameters
    for k, v in query_params:
        if k.lower() not in utm_keys:
            new_params.append((k, v))
            
    # Add standardized UTM parameters
    new_params.append(("utm_source", cleaned_source))
    new_params.append(("utm_medium", cleaned_medium))
    new_params.append(("utm_campaign", cleaned_campaign))
    new_params.append(("utm_content", cleaned_content))
    
    # Rebuild the URL
    new_query = urllib.parse.urlencode(new_params)
    
    parts = list(parsed)
    parts[4] = new_query
    
    return urllib.parse.urlunparse(parts)
