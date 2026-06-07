from typing import Any, Dict, List
import re

class ValidatorRegistry:
    @staticmethod
    def validate_bool(value: Any, schema: dict) -> bool | None:
        if value is None:
            return None # Not providing a value is usually fine unless required
            
        # Handle list-wrapped values (e.g., [True] or ["true"])
        if isinstance(value, list):
            if not value:
                return None
            value = value[0]

        if isinstance(value, bool):
            return value
        
        # Handle numeric types (0, 1) often sent by frontend
        if isinstance(value, (int, float)):
            if value == 1:
                return True
            if value == 0:
                return False

        str_val = str(value).lower()
        if str_val in ("true", "1", "yes", "on"):
            return True
        if str_val in ("false", "0", "no", "off"):
            return False
        raise ValueError(f"Value '{value}' (type: {type(value).__name__}) must be a boolean.")

    @staticmethod
    def _extract_options(schema: dict) -> list:
        if not schema:
            return []
        # Support real Google API response where options are in valueMetadata
        if "valueMetadata" in schema:
            return [opt.get("value") for opt in schema["valueMetadata"] if opt and opt.get("value")]
        # Support sandbox/mock responses
        for key in ["enumValue", "repeatedEnumValue"]:
            if key in schema:
                meta = schema[key] or {}
                if "supportedOptions" in meta:
                    return [opt.get("value") for opt in meta.get("supportedOptions", []) if opt and opt.get("value")]
        return []

    @staticmethod
    def validate_enum(value: Any, schema: dict) -> Any:
        if value is None:
            return None
            
        options = ValidatorRegistry._extract_options(schema)
        
        if options and value not in options:
            raise ValueError(f"Value '{value}' must be one of {options}")
        return value

    @staticmethod
    def validate_repeated_enum(values: Any, schema: dict) -> Any:
        if values is None:
            return None
            
        if not isinstance(values, list):
            raise ValueError("Value must be a list for REPEATED_ENUM.")
            
        options = ValidatorRegistry._extract_options(schema)
        
        if options:
            for val in values:
                if val not in options:
                    raise ValueError(f"Value '{val}' must be one of {options}")
        return values

    @staticmethod
    def validate_url(value: Any, schema: dict) -> Any:
        if not value:
            return value
            
        if not isinstance(value, str):
            raise ValueError("URL value must be a string.")
            
        url_pattern = re.compile(
            r'^(?:http|ftp)s?://' # http:// or https://
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
            r'localhost|' #localhost...
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
            r'(?::\d+)?' # optional port
            r'(?:/?|[/?]\S+)$', re.IGNORECASE)
            
        if not url_pattern.match(value):
            raise ValueError("Invalid URL format.")
        return value

    @classmethod
    def validate(cls, value: Any, value_type: str, raw_schema: dict) -> Any:
        validators = {
            "BOOL": cls.validate_bool,
            "ENUM": cls.validate_enum,
            "REPEATED_ENUM": cls.validate_repeated_enum,
            "URL": cls.validate_url
        }
        
        validator = validators.get(value_type)
        if validator:
            return validator(value, raw_schema)
            
        # Fallback for unknown types - accept as is
        return value
