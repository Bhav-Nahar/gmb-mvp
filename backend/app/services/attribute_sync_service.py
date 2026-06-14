import datetime
from sqlalchemy.orm import Session
import httpx
from typing import Dict, Any, List

from app.providers.gbp.client import GBPAsyncClient
from app.providers.gbp.auth import GBPAuthManager
from app.providers.base.auth import AuthContext
from app.models.oauth_account import OAuthAccount
from app.models.user import User
from app.core.roles import ADMIN_ROLES
from app.models.location import Location
from app.models.gbp_attribute_metadata import GbpAttributeMetadata
from app.models.gbp_attribute_definition import GbpAttributeDefinition
from app.core.security import decrypt_token
import logging
import asyncio
import random

logger = logging.getLogger(__name__)

class AttributeSyncService:
    def __init__(self, db: Session):
        self.db = db

    async def _get_access_token(self, organization_id: int) -> str:
        # Get OAuth account for org
        oauth_account = self.db.query(OAuthAccount).join(User).filter(
            User.organization_id == organization_id,
            User.role.in_(ADMIN_ROLES),
            OAuthAccount.provider.in_(["gbp", "google"])
        ).first()

        if not oauth_account:
            raise Exception(f"No valid Google credentials found for organization {organization_id}")

        auth_context = AuthContext(
            organization_id=organization_id,
            access_token=decrypt_token(oauth_account.access_token),
            refresh_token=decrypt_token(oauth_account.refresh_token) if oauth_account.refresh_token else None,
            expires_at=oauth_account.expires_at
        )
        auth_manager = GBPAuthManager(auth_context, self.db)
        return await auth_manager.get_valid_token()

    async def sync_category_metadata(self, organization_id: int, category_id: str, region_code: str, language_code: str) -> None:
        access_token = await self._get_access_token(organization_id)
        
        # Sandbox mode handler
        if "mock_access_token" in access_token:
            mock_metadata = {
                "name": f"categories/{category_id}",
                # Google real API returns key "attributeMetadata" - use the same key in mock
                "attributeMetadata": [
                    {
                        "parent": "attributes/mock_wifi",
                        "displayName": "Has Wi-Fi",
                        "groupDisplayName": "Amenities",
                        "valueType": "BOOL"
                    },
                    {
                        "parent": "attributes/mock_payment",
                        "displayName": "Payment Methods Accepted",
                        "groupDisplayName": "Payments",
                        "valueType": "REPEATED_ENUM",
                        "repeatedEnumValue": {
                            "supportedOptions": [
                                {"value": "CREDIT_CARD", "displayName": "Credit Card"},
                                {"value": "DEBIT_CARD", "displayName": "Debit Card"},
                                {"value": "CASH", "displayName": "Cash"},
                                {"value": "UPI", "displayName": "UPI"}
                            ]
                        }
                    },
                    {
                        "parent": "attributes/mock_wheelchair",
                        "displayName": "Wheelchair Accessible Entrance",
                        "groupDisplayName": "Accessibility",
                        "valueType": "BOOL"
                    },
                    {
                        "parent": "attributes/mock_parking",
                        "displayName": "Parking Options",
                        "groupDisplayName": "Parking",
                        "valueType": "REPEATED_ENUM",
                        "repeatedEnumValue": {
                            "supportedOptions": [
                                {"value": "FREE_PARKING_LOT", "displayName": "Free Parking Lot"},
                                {"value": "PAID_PARKING_LOT", "displayName": "Paid Parking Lot"},
                                {"value": "STREET_PARKING", "displayName": "Street Parking"},
                                {"value": "VALET_PARKING", "displayName": "Valet Parking"}
                            ]
                        }
                    }
                ]
            }
            self._process_and_save_metadata(category_id, region_code, language_code, mock_metadata, "mock_etag")
            return

        url = "https://mybusinessbusinessinformation.googleapis.com/v1/attributes"
        
        existing_meta = self.db.query(GbpAttributeMetadata).filter(
            GbpAttributeMetadata.category_id == category_id,
            GbpAttributeMetadata.region_code == region_code,
            GbpAttributeMetadata.language_code == language_code
        ).first()
        
        if existing_meta and existing_meta.last_fetched_at:
            last_fetched = existing_meta.last_fetched_at
            if last_fetched.tzinfo is None:
                last_fetched = last_fetched.replace(tzinfo=datetime.timezone.utc)
            else:
                last_fetched = last_fetched.astimezone(datetime.timezone.utc)
            time_diff = datetime.datetime.now(datetime.timezone.utc) - last_fetched
            if time_diff.total_seconds() < 86400: # 24 hours TTL
                return

        headers = {"Authorization": f"Bearer {access_token}"}
        
        all_attributes = []
        next_page_token = None
        
        async with GBPAsyncClient(organization_id) as client:
            while True:
                params = {
                    "categoryName": f"categories/{category_id}",
                    "regionCode": region_code,
                    "languageCode": language_code,
                    "pageSize": 100
                }
                if next_page_token:
                    params["pageToken"] = next_page_token

                # Exponential backoff with jitter for 429 Rate Limits
                max_retries = 3
                retry_count = 0
                resp = None
                
                while retry_count <= max_retries:
                    resp = await client.request("GET", url, headers=headers, params=params)
                    if resp.status_code == 429 or resp.status_code >= 500:
                        retry_count += 1
                        if retry_count > max_retries:
                            raise Exception(f"Failed to fetch metadata after {max_retries} retries due to rate limiting or server errors.")
                        sleep_time = (2 ** retry_count) + random.uniform(0, 1)
                        logger.warning(f"API Error {resp.status_code}. Retrying in {sleep_time:.2f}s...")
                        await asyncio.sleep(sleep_time)
                    else:
                        break
                
                if resp.status_code != 200:
                    raise Exception(f"Failed to fetch metadata: {resp.text}")
                    
                data = resp.json()
                all_attributes.extend(data.get("attributeMetadata", []))
                
                next_page_token = data.get("nextPageToken")
                if not next_page_token:
                    break
        
        # Merge all paginated attributes into the final data structure
        final_data = {"name": f"categories/{category_id}", "attributeMetadata": all_attributes}
        
        if existing_meta and existing_meta.metadata_json == final_data:
            existing_meta.last_fetched_at = datetime.datetime.now(datetime.timezone.utc)
            self.db.commit()
            return

        self._process_and_save_metadata(category_id, region_code, language_code, final_data, None)

    def _process_and_save_metadata(self, category_id: str, region_code: str, language_code: str, data: dict, etag: str = None):
        meta = self.db.query(GbpAttributeMetadata).filter(
            GbpAttributeMetadata.category_id == category_id,
            GbpAttributeMetadata.region_code == region_code,
            GbpAttributeMetadata.language_code == language_code
        ).first()

        if meta:
            meta.metadata_json = data
            meta.etag = etag
            meta.last_fetched_at = datetime.datetime.now(datetime.timezone.utc)
        else:
            meta = GbpAttributeMetadata(
                category_id=category_id,
                region_code=region_code,
                language_code=language_code,
                metadata_json=data,
                etag=etag,
                last_fetched_at=datetime.datetime.now(datetime.timezone.utc)
            )
            self.db.add(meta)

        attributes = data.get("attributeMetadata", [])
        
        received_attr_ids = []
        
        for idx, attr in enumerate(attributes):
            attr_id = attr.get("parent")
            if not attr_id:
                attr_id = attr.get("name")
                if attr_id:
                    logger.debug(f"Attribute missing 'parent' key; falling back to 'name' as attribute ID: {attr_id}")
            if not attr_id:
                continue
            
            received_attr_ids.append(attr_id)
            
            value_type = attr.get("valueType")
            is_repeatable = attr.get("repeatable", False) or value_type == "REPEATED_ENUM"
            options_json = None
            
            value_metadata = attr.get("valueMetadata")
            if value_metadata:
                if value_type == "ENUM":
                    options_json = {"enumValue": {"supportedOptions": value_metadata}}
                else:
                    options_json = {"repeatedEnumValue": {"supportedOptions": value_metadata}}
            elif value_type == "ENUM":
                enum_meta = attr.get("enumValue")
                if enum_meta and "supportedOptions" in enum_meta:
                    options_json = {"enumValue": enum_meta}
            elif value_type == "REPEATED_ENUM":
                enum_meta = attr.get("repeatedEnumValue")
                if enum_meta and "supportedOptions" in enum_meta:
                    options_json = {"repeatedEnumValue": enum_meta}
                    
            definition = self.db.query(GbpAttributeDefinition).filter(
                GbpAttributeDefinition.attribute_id == attr_id,
                GbpAttributeDefinition.category_id == category_id,
                GbpAttributeDefinition.region_code == region_code,
                GbpAttributeDefinition.language_code == language_code
            ).first()

            if definition:
                definition.display_name = attr.get("displayName")
                definition.group_display_name = attr.get("groupDisplayName")
                definition.value_type = value_type
                definition.is_repeatable = is_repeatable
                definition.options_json = options_json
                definition.raw_schema = attr
                definition.is_active = True
            else:
                definition = GbpAttributeDefinition(
                    attribute_id=attr_id,
                    category_id=category_id,
                    region_code=region_code,
                    language_code=language_code,
                    display_name=attr.get("displayName"),
                    group_display_name=attr.get("groupDisplayName"),
                    value_type=value_type,
                    is_repeatable=is_repeatable,
                    options_json=options_json,
                    raw_schema=attr,
                    is_active=True
                )
                self.db.add(definition)

        # Deactivate attributes that are no longer returned
        if received_attr_ids:
            self.db.query(GbpAttributeDefinition).filter(
                GbpAttributeDefinition.category_id == category_id,
                GbpAttributeDefinition.region_code == region_code,
                GbpAttributeDefinition.language_code == language_code,
                ~GbpAttributeDefinition.attribute_id.in_(received_attr_ids)
            ).update({"is_active": False}, synchronize_session=False)

        self.db.commit()

    async def fetch_location_attributes(self, location_id: int) -> None:
        location = self.db.query(Location).filter(Location.id == location_id).first()
        if not location:
            logger.info(f"fetch_location_attributes: location {location_id} not found, skipping")
            return
        if not location.google_location_id:
            logger.info(f"fetch_location_attributes: location {location_id} has no google_location_id, skipping")
            return

        access_token = await self._get_access_token(location.organization_id)

        if "mock_access_token" in access_token:
            mock_attrs = {
                "name": f"{location.google_location_id}/attributes",
                "attributes": [
                    {
                        "name": "attributes/mock_wifi",
                        "valueType": "BOOL",
                        "values": [True]
                    }
                ]
            }
            location.google_attributes = mock_attrs.get("attributes", [])
            location.last_google_sync = datetime.datetime.now(datetime.timezone.utc)
            self.db.commit()
            return

        headers = {"Authorization": f"Bearer {access_token}"}
        url = f"https://mybusinessbusinessinformation.googleapis.com/v1/{location.google_location_id}/attributes"

        # M1: Retry backoff mirrors sync_category_metadata.
        # M3: Pagination loop — attributes endpoint may paginate large results.
        all_attributes = []
        next_page_token = None
        max_retries = 3

        async with GBPAsyncClient(location.organization_id) as client:
            retry_count = 0
            resp = None
            while retry_count <= max_retries:
                try:
                    resp = await client.request("GET", url, headers=headers)
                except Exception as e:
                    logger.error(f"Failed to fetch attributes for location {location.id}: {e}", exc_info=True)
                    raise

                if resp.status_code == 429:
                    retry_count += 1
                    if retry_count > max_retries:
                        raise Exception(
                            f"Rate limited (429) fetching attributes for location {location.id} "
                            f"after {max_retries} retries."
                        )
                    sleep_time = (2 ** retry_count) + random.uniform(0, 1)
                    logger.warning(
                        f"Rate limited (429) fetching attributes for location {location.id}. "
                        f"Retrying in {sleep_time:.2f}s..."
                    )
                    await asyncio.sleep(sleep_time)
                else:
                    break

            if resp is None or resp.status_code not in [200, 404]:
                status = resp.status_code if resp else "unknown"
                body = resp.text if resp else ""
                logger.error(f"Failed to fetch attributes for location {location.id}: HTTP {status} — {body}")
                return

            if resp.status_code == 404:
                # No attributes set on this location yet; that's fine.
                all_attributes = []
            else:
                data = resp.json()
                all_attributes = data.get("attributes", [])

        location.google_attributes = all_attributes
        location.last_google_sync = datetime.datetime.now(datetime.timezone.utc)
        location.google_attributes_stale = False
        self.db.commit()

        # Invalidate cached form schema: current_value is derived from google_attributes,
        # so a stale cache would show outdated values for up to 24h after a sync.
        try:
            from app.core.redis_client import get_redis
            get_redis().delete(f"location:attributes_schema:{location_id}")
        except Exception as cache_err:
            logger.warning(f"Failed to invalidate form schema cache for location {location_id}: {cache_err}")

