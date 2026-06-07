import json
import os
import pytest

def test_google_attribute_payload_snapshot():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "google_attribute_metadata", "sample_real_payload.json")
    with open(fixture_path, "r") as f:
        data = json.load(f)
        
    attributes = data.get("attributeMetadata", [])
    assert len(attributes) == 3
    
    # Simulate the logic from AttributeSyncService
    processed_options = []
    for attr in attributes:
        value_type = attr.get("valueType")
        value_metadata = attr.get("valueMetadata")
        options_json = None
        
        if value_metadata:
            if value_type == "ENUM":
                options_json = {"enumValue": {"supportedOptions": value_metadata}}
            else:
                options_json = {"repeatedEnumValue": {"supportedOptions": value_metadata}}
        
        processed_options.append({
            "name": attr.get("name"),
            "options_json": options_json
        })
        
    # Check the REPEATED_ENUM mapping
    repeated_enum_item = next(item for item in processed_options if item["name"] == "attributes/payment_options")
    assert repeated_enum_item["options_json"]["repeatedEnumValue"]["supportedOptions"][0]["value"] == "CREDIT_CARD"
    
    # Check the ENUM mapping
    enum_item = next(item for item in processed_options if item["name"] == "attributes/dining_options")
    assert enum_item["options_json"]["enumValue"]["supportedOptions"][0]["value"] == "BREAKFAST"
    
    # Check the BOOL mapping
    bool_item = next(item for item in processed_options if item["name"] == "attributes/has_delivery")
    assert bool_item["options_json"] is None
