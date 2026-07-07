from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import datetime
import logging
import re
import hashlib
import json

from app.api.posts import get_redis

from app.api.deps import get_db, get_current_user, staff_required, require_location_access
from app.models.user import User
from app.models.location import Location
from app.models.gbp_attribute_definition import GbpAttributeDefinition
from app.utils.validator_registry import ValidatorRegistry
from app.providers.factory import ProviderFactory
from app.providers.gbp.client import GBPAsyncClient
from app.providers.gbp.auth import GBPAuthManager
from app.models.oauth_account import OAuthAccount
from app.core.security import decrypt_token
from app.providers.base.auth import AuthContext
from app.models.gbp_location_attribute_rejection import GbpLocationAttributeRejection
from app.providers.base.exceptions import ProviderError
from app.services.attribute_sync_service import AttributeSyncService
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()

def get_category_id(category_name: str) -> str:
    if not category_name:
        return "gcid:business"
        
    # Standard mapping for common categories
    # Use US spelling 'jewelry_store' as it has 50+ attributes vs 2 for 'jeweller'
    cat_id_map = {
        "Coffee Shop": "gcid:coffee_shop",
        "Gym": "gcid:gym",
        "Pizza restaurant": "gcid:pizza_restaurant",
        "Jeweller": "gcid:jewelry_store",
        "Jewellery Store": "gcid:jewelry_store",
        "Jewelry Store": "gcid:jewelry_store"
    }
    
    if category_name in cat_id_map:
        return cat_id_map[category_name]
        
    # Dynamic fallback
    cat_id = category_name.lower().replace(" ", "_")
    if not cat_id.startswith("gcid:"):
        return f"gcid:{cat_id}"
    return cat_id

@router.get("/{location_id}/form-schema")
async def get_form_schema(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    # require_location_access already fetched and org-scoped this row.
    location_id = location.id

    cache_key = f"location:attributes_schema:{location_id}"
    redis_client = None
    try:
        redis_client = get_redis()
        cached_data = redis_client.get(cache_key)
        if cached_data:
            logger.info(f"Serving cached form schema for location {location_id}")
            return json.loads(cached_data)
    except Exception as e:
        logger.error(f"Redis cache lookup failed for form schema: {e}")
        
    if not location.primary_category and not location.google_category_resource_name:
        return {"schema": []}
        
    if location.google_category_resource_name:
        category_id = location.google_category_resource_name.replace("categories/", "")
    else:
        category_id = get_category_id(location.primary_category)

    if not re.match(r"^gcid:[a-z0-9_]+$", category_id):
        raise HTTPException(status_code=400, detail=f"Invalid category ID: {category_id}")

    # Query definitions
    definitions = db.query(GbpAttributeDefinition).filter(
        GbpAttributeDefinition.category_id == category_id,
        GbpAttributeDefinition.is_active == True
    ).all()
    
    # Auto-seed: if no definitions exist, run sync now (first time for this category)
    if not definitions:
        try:
            from app.worker import celery as celery_app
            celery_app.send_task(
                "app.tasks.sync_gbp_attributes_metadata_task",
                kwargs={
                    "organization_id": current_user.organization_id,
                    "category_id": category_id,
                    "region_code": "IN",
                    "language_code": "en"
                }
            )
            return {"schema": [], "is_seeding": True}
        except Exception as celery_err:
            logger.warning(f"Auto-seed attributes failed for {category_id}: {celery_err}")
            # Fallback: return empty schema instead of 500 error
            return {"schema": [], "is_seeding": False, "error": "Metadata sync temporarily unavailable"}
    
    # Query rejections for capability memory (sliding 30-day window to allow for Google feature rollouts)
    expiry_limit = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)
    rejections = db.query(GbpLocationAttributeRejection).filter(
        GbpLocationAttributeRejection.location_id == location_id,
        GbpLocationAttributeRejection.last_seen >= expiry_limit,
        GbpLocationAttributeRejection.suppressed == False
    ).all()
    rejected_ids = {r.attribute_id for r in rejections}
    
    # Process current and draft values
    google_attrs = {a.get("name"): a for a in (location.google_attributes or [])}
    draft_attrs = {a.get("name"): a for a in (location.draft_attributes or [])}
    rejection_map = {r.attribute_id: r.rejection_reason for r in rejections}
    rejected_val_map = {r.attribute_id: r.rejected_value for r in rejections}
    
    def extract_val(val_obj):
        if not val_obj:
            return None
        if not isinstance(val_obj, dict):
            return val_obj
        if "values" in val_obj:
            return val_obj["values"]
        if "repeatedEnumValue" in val_obj:
            return val_obj["repeatedEnumValue"].get("setValues", [])
        if "uriValues" in val_obj:
            return [u.get("uri") for u in val_obj["uriValues"] if u.get("uri")]
        return None

    # Google reports per-location applicability only at write time. An attribute
    # rejected with INVALID_ATTRIBUTE_NAME genuinely does not apply to THIS location,
    # so it is hidden from the main form (surfaced separately as "not supported")
    # rather than shown as an editable field with a warning. Value-level rejections
    # (bad URL, bad social handle) stay in-form so the user can correct them.
    NOT_APPLICABLE_REASONS = {"INVALID_ATTRIBUTE_NAME"}

    schema = []
    not_applicable = []
    for df in definitions:
        attr_id = df.attribute_id

        current_val_obj = google_attrs.get(attr_id, {})
        draft_val_obj = draft_attrs.get(attr_id, {})
        
        current_val = extract_val(current_val_obj)
        draft_val = extract_val(draft_val_obj)
        
        # If value is bool but stored as [True]
        if df.value_type == "BOOL":
            if current_val and isinstance(current_val, list):
                current_val = current_val[0]
            if draft_val and isinstance(draft_val, list):
                draft_val = draft_val[0]
                
        # If value is ENUM but stored as ["SOMETHING"] (and is not repeatable)
        if df.value_type == "ENUM" and not df.is_repeatable:
            if current_val and isinstance(current_val, list):
                current_val = current_val[0]
            if draft_val and isinstance(draft_val, list):
                draft_val = draft_val[0]
                
        # If value is URL but stored as ["https://..."]
        if df.value_type == "URL":
            if current_val and isinstance(current_val, list):
                current_val = current_val[0]
            if draft_val and isinstance(draft_val, list):
                draft_val = draft_val[0]
                
        is_rejected = attr_id in rejected_ids
        reason = rejection_map.get(attr_id) if is_rejected else None

        item = {
            "attribute_id": attr_id,
            "display_name": df.display_name,
            "group_display_name": df.group_display_name,
            "value_type": df.value_type,
            "is_repeatable": df.is_repeatable,
            "options": df.options_json,
            "current_value": current_val,
            "draft_value": draft_val,
            "is_rejected": is_rejected,
            "rejection_reason": reason,
            "rejected_value": extract_val(rejected_val_map.get(attr_id)) if is_rejected else None
        }

        if is_rejected and reason in NOT_APPLICABLE_REASONS:
            not_applicable.append(item)
        else:
            schema.append(item)

    res = {"schema": schema, "not_applicable": not_applicable}
    if redis_client:
        try:
            redis_client.setex(
                cache_key,
                86400, # 24h
                json.dumps(res)
            )
        except Exception as e:
            logger.error(f"Redis cache write failed for form schema: {e}")
            
    return res

@router.post("/{location_id}/draft-attributes")
def save_draft_attributes(
    payload: Dict[str, Any],
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    location_id = location.id
    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id
    ).with_for_update().first()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    if not location.primary_category:
        raise HTTPException(status_code=400, detail="Location has no primary category")

    if location.google_category_resource_name:
        category_id = location.google_category_resource_name.replace("categories/", "")
    else:
        category_id = get_category_id(location.primary_category)

    if not re.match(r"^gcid:[a-z0-9_]+$", category_id):
        raise HTTPException(status_code=400, detail=f"Invalid category ID: {category_id}")

    # Query definitions for validation
    definitions = {
        d.attribute_id: d for d in db.query(GbpAttributeDefinition).filter(
            GbpAttributeDefinition.category_id == category_id,
            GbpAttributeDefinition.is_active == True
        ).all()
    }
    
    draft_array = location.draft_attributes or []
    # Convert list of dicts to a dict by attribute name for easier updating
    draft_dict = {a.get("name"): a for a in draft_array}
    
    for attr_id, raw_val in payload.items():
        if attr_id not in definitions:
            logger.error(f"Unknown attribute: {attr_id} for location {location_id}")
            raise HTTPException(status_code=400, detail=f"Unknown attribute: {attr_id}")
            
        df = definitions[attr_id]
        
        try:
            val_type_to_validate = "REPEATED_ENUM" if (df.is_repeatable and df.value_type == "ENUM") else df.value_type
            raw_val = ValidatorRegistry.validate(raw_val, val_type_to_validate, df.raw_schema)
        except ValueError as e:
            logger.error(f"Validation failed for {attr_id}: {str(e)}", extra={
                "location_id": location_id,
                "attribute_id": attr_id,
                "value": raw_val,
                "value_type": type(raw_val).__name__,
                "expected_type": df.value_type
            })
            raise HTTPException(status_code=400, detail=f"Validation failed for {attr_id}: {str(e)}")

        if raw_val is not None and raw_val != "" and raw_val != []:
            if df.value_type == "BOOL":
                if not isinstance(raw_val, bool):
                    # Should already be handled by ValidatorRegistry, but double check and cast
                    if str(raw_val).lower() in ("true", "1", "yes", "on"):
                        raw_val = True
                    elif str(raw_val).lower() in ("false", "0", "no", "off"):
                        raw_val = False
                    else:
                        raise HTTPException(status_code=400, detail=f"Attribute {attr_id} expects a boolean value")
            if df.value_type == "URL":
                url_vals = raw_val if isinstance(raw_val, list) else [raw_val]
                for url_val in url_vals:
                    if url_val and not str(url_val).startswith(("http://", "https://")):
                        raise HTTPException(status_code=400, detail=f"URL attribute {attr_id} must start with http:// or https://")

        # Format the value for Google API
        formatted_attr = {"name": attr_id, "valueType": df.value_type}

        is_repeatable = df.is_repeatable or df.value_type == "REPEATED_ENUM"

        if raw_val is None or raw_val == "" or raw_val == []:
            # If they are clearing it, we should omit it or send empty array
            if is_repeatable:
                formatted_attr["repeatedEnumValue"] = {"setValues": []}
            elif df.value_type == "URL":
                formatted_attr["uriValues"] = []
            else:
                formatted_attr["values"] = []
        elif is_repeatable:
            if df.value_type == "URL":
                # Ensure it's a list for repeatability
                vals = raw_val if isinstance(raw_val, list) else [raw_val]
                formatted_attr["uriValues"] = [{"uri": v} for v in vals if v]
            else:
                formatted_attr["repeatedEnumValue"] = {"setValues": raw_val if isinstance(raw_val, list) else [raw_val]}
        elif df.value_type == "URL":
            formatted_attr["uriValues"] = [{"uri": raw_val}]
        else:
            # For BOOL, ENUM (non-repeatable)
            formatted_attr["values"] = [raw_val]

        draft_dict[attr_id] = formatted_attr
    try:
        location.draft_attributes = list(draft_dict.values())
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("draft_save_failed", extra={"location_id": location_id, "error_type": type(e).__name__, "error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to save draft attributes")
    
    # Invalidate cached form schema
    try:
        r = get_redis()
        r.delete(f"location:attributes_schema:{location_id}")
        logger.info(f"Invalidated form schema cache for location {location_id} on draft save")
    except Exception as cache_err:
        logger.error(f"Failed to invalidate cache on draft save for location {location_id}: {cache_err}")

    return {"status": "success", "message": "Draft saved"}

@router.post("/{location_id}/publish-attributes")
async def publish_attributes(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    location_id = location.id
    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id
    ).first()
    
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    if not location.google_location_id:
        raise HTTPException(status_code=400, detail="Location is not linked to Google")
        
    draft_attrs = location.draft_attributes or []

    if not draft_attrs:
        # If there are no drafts, we check if they were just published successfully (idempotency check)
        return {
            "success": True, 
            "status": "success", 
            "message": "Attributes are up to date",
            "warnings": [],
            "removed_attributes": []
        }
        
    location.sync_status = "Publishing"
    db.commit()
    
    from app.worker import celery as celery_app
    celery_app.send_task(
        "app.tasks.publish_location_attributes_task",
        kwargs={"location_id": location_id}
    )
    
    return {
        "success": True, 
        "status": "queued", 
        "message": "Publish queued",
        "warnings": [],
        "removed_attributes": []
    }

@router.get("/{location_id}/publish-status")
def get_publish_status(
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    location_id = location.id
    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id
    ).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    return {
        "status": location.sync_status,
        "attention_needed": location.attention_needed,
        "attention_reason": location.attention_reason
    }

class SuppressRejectionRequest(BaseModel):
    attribute_id: str

@router.post("/{location_id}/suppress-rejection")
def suppress_rejection(
    payload: SuppressRejectionRequest,
    location: Location = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required)
):
    location_id = location.id
    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id
    ).first()
    
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    rejection = db.query(GbpLocationAttributeRejection).filter(
        GbpLocationAttributeRejection.location_id == location_id,
        GbpLocationAttributeRejection.attribute_id == payload.attribute_id
    ).first()
    
    if not rejection:
        raise HTTPException(status_code=404, detail="Rejection not found")
        
    try:
        rejection.suppressed = True
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("suppression_failed", extra={"location_id": location_id, "error": str(e)})
        raise HTTPException(status_code=500, detail="Failed to suppress warning")

    # Invalidate cached form schema so the dismissed attribute re-appears in the form
    try:
        get_redis().delete(f"location:attributes_schema:{location_id}")
    except Exception as cache_err:
        logger.error(f"Failed to invalidate cache on suppress for location {location_id}: {cache_err}")

    return {"status": "success"}
