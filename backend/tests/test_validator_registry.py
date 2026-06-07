import pytest
from app.utils.validator_registry import ValidatorRegistry

def test_validate_bool():
    assert ValidatorRegistry.validate_bool(True, {}) == True
    assert ValidatorRegistry.validate_bool(False, {}) == False
    assert ValidatorRegistry.validate_bool("true", {}) == True
    assert ValidatorRegistry.validate_bool("false", {}) == False
    with pytest.raises(ValueError):
        ValidatorRegistry.validate_bool("invalid", {})

def test_validate_enum():
    schema = {
        "enumValue": {
            "supportedOptions": [
                {"value": "YES", "displayName": "Yes"},
                {"value": "NO", "displayName": "No"}
            ]
        }
    }
    assert ValidatorRegistry.validate_enum("YES", schema) == "YES"
    with pytest.raises(ValueError):
        ValidatorRegistry.validate_enum("MAYBE", schema)

def test_validate_url():
    assert ValidatorRegistry.validate_url("https://example.com", {}) == "https://example.com"
    assert ValidatorRegistry.validate_url("http://localhost:3000", {}) == "http://localhost:3000"
    with pytest.raises(ValueError):
        ValidatorRegistry.validate_url("not_a_url", {})

def test_validate_repeated_enum():
    schema = {
        "repeatedEnumValue": {
            "supportedOptions": [
                {"value": "WIFI"},
                {"value": "PARKING"}
            ]
        }
    }
    assert ValidatorRegistry.validate_repeated_enum(["WIFI"], schema) == ["WIFI"]
    assert ValidatorRegistry.validate_repeated_enum(["WIFI", "PARKING"], schema) == ["WIFI", "PARKING"]
    with pytest.raises(ValueError):
        ValidatorRegistry.validate_repeated_enum(["WIFI", "POOL"], schema)
    with pytest.raises(ValueError):
        ValidatorRegistry.validate_repeated_enum("WIFI", schema) # not a list

def test_validate_real_google_schema():
    # Test options extraction using valueMetadata (Google API format)
    schema = {
        "name": "attributes/dining_options",
        "valueType": "ENUM",
        "valueMetadata": [
            {"value": "BREAKFAST", "displayName": "Breakfast"},
            {"value": "LUNCH", "displayName": "Lunch"},
            {"value": "DINNER", "displayName": "Dinner"}
        ],
        "repeatable": True
    }
    
    # Verify option extraction works directly
    options = ValidatorRegistry._extract_options(schema)
    assert options == ["BREAKFAST", "LUNCH", "DINNER"]
    
    # Test validation using validate_enum with real schema format
    assert ValidatorRegistry.validate_enum("BREAKFAST", schema) == "BREAKFAST"
    with pytest.raises(ValueError):
        ValidatorRegistry.validate_enum("BRUNCH", schema)
        
    # Test validation of repeatable list using validate_repeated_enum
    assert ValidatorRegistry.validate_repeated_enum(["BREAKFAST", "LUNCH"], schema) == ["BREAKFAST", "LUNCH"]
    with pytest.raises(ValueError):
        ValidatorRegistry.validate_repeated_enum(["BREAKFAST", "BRUNCH"], schema)
