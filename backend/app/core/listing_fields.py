from dataclasses import dataclass, field
from typing import Optional

@dataclass(frozen=True)
class ListingFieldConfig:
    name: str                        # matches the column name in the locations table
    label: str                       # human-readable label for UI
    is_staff_editable: bool          # staff can submit a draft for this field
    is_admin_editable: bool          # admin can edit directly (always True for editable fields)
    is_critical: bool                # triggers warning modal before editing
    is_read_only: bool               # never editable, synced from GBP only
    warning_title: Optional[str] = None   # modal title shown when is_critical=True
    warning_body: Optional[str] = None    # modal body text shown when is_critical=True
    gbp_field_mask: Optional[str] = None  # GBP API PATCH field mask value for this field
    field_type: str = "text"                      # semantic data type (validation & UI)
    transformer: str = "identity_transform"       # registry lookup key for payload transform
    ui_component: str = "input"                   # frontend editor key
    supports_bulk_edit: bool = True               # whether this field supports bulk editing

LISTING_FIELDS: list[ListingFieldConfig] = [
    # ── Critical fields (admin only, warning modal required) ──────────────────
    ListingFieldConfig(
        name="location_name",
        label="Business name",
        is_staff_editable=False,
        is_admin_editable=True,
        is_critical=True,
        is_read_only=False,
        warning_title="Changing your business name",
        warning_body=(
            "Changing your business name may trigger a Google re-verification process. "
            "Your listing could appear unverified on Maps for several days while Google "
            "reviews the change. Only proceed if this is a legal or permanent name change."
        ),
        gbp_field_mask="title",
        field_type="text",
        transformer="location_name",
        ui_component="input",
    ),
    ListingFieldConfig(
        name="primary_category",
        label="Primary category",
        is_staff_editable=False,
        is_admin_editable=True,
        is_critical=True,
        is_read_only=False,
        warning_title="Changing your primary category",
        warning_body=(
            "Changing your primary category will affect how your listing ranks in local "
            "search. Google may take 24–48 hours to reindex. Make sure the new category "
            "accurately reflects your core business. Additionally, all current dynamic attributes "
            "will be wiped and you will need to fill them out again for the new category."
        ),
        gbp_field_mask="categories",
        field_type="select",
        transformer="primary_category",
        ui_component="category_autocomplete",
    ),
    ListingFieldConfig(
        name="address",
        label="Address",
        is_staff_editable=False,
        is_admin_editable=True,
        is_critical=True,
        is_read_only=False,
        warning_title="Changing your address",
        warning_body=(
            "Changing your address may require Google to re-verify your listing by sending "
            "a postcard to the new address. Your listing may show reduced visibility until "
            "verification is complete. Confirm this is a real, permanent address change."
        ),
        gbp_field_mask="storefrontAddress",
        field_type="json",
        transformer="address",
        ui_component="textarea",
    ),
    # ── Standard fields (no warning) ─────────────────────────────────────────
    ListingFieldConfig(
        name="additional_categories",
        label="Additional categories",
        is_staff_editable=False,
        is_admin_editable=True,
        is_critical=False,
        is_read_only=False,
        gbp_field_mask="categories",
        field_type="json",
        transformer="additional_categories",
        ui_component="multi_category_autocomplete",
        supports_bulk_edit=False,
    ),
    ListingFieldConfig(
        name="phone",
        label="Phone number",
        is_staff_editable=True,
        is_admin_editable=True,
        is_critical=False,
        is_read_only=False,
        gbp_field_mask="phoneNumbers",
        field_type="text",
        transformer="phone",
        ui_component="input",
    ),
    ListingFieldConfig(
        name="business_hours",
        label="Business hours",
        is_staff_editable=True,
        is_admin_editable=True,
        is_critical=False,
        is_read_only=False,
        gbp_field_mask="regularHours",
        field_type="hours",
        transformer="business_hours",
        ui_component="business_hours_editor",
    ),
    ListingFieldConfig(
        name="website",
        label="Website URL",
        is_staff_editable=False,
        is_admin_editable=True,
        is_critical=False,
        is_read_only=False,
        gbp_field_mask="websiteUri",
        field_type="url",
        transformer="url",
        ui_component="input",
    ),
    ListingFieldConfig(
        name="description",
        label="Business description",
        is_staff_editable=False,
        is_admin_editable=True,
        is_critical=False,
        is_read_only=False,
        gbp_field_mask="profile.description",
        field_type="textarea",
        transformer="description",
        ui_component="textarea",
    ),
    # ── Read-only fields (synced from GBP, never editable) ───────────────────
    ListingFieldConfig(
        name="average_rating",
        label="Average rating",
        is_staff_editable=False,
        is_admin_editable=False,
        is_critical=False,
        is_read_only=True,
    ),
    ListingFieldConfig(
        name="total_reviews",
        label="Total reviews",
        is_staff_editable=False,
        is_admin_editable=False,
        is_critical=False,
        is_read_only=True,
    ),
    ListingFieldConfig(
        name="sync_status",
        label="Sync status",
        is_staff_editable=False,
        is_admin_editable=False,
        is_critical=False,
        is_read_only=True,
    ),
    ListingFieldConfig(
        name="google_location_id",
        label="Google location ID",
        is_staff_editable=False,
        is_admin_editable=False,
        is_critical=False,
        is_read_only=True,
    ),
]

# Convenience lookups — use these instead of filtering the list manually
FIELD_MAP: dict[str, ListingFieldConfig] = {f.name: f for f in LISTING_FIELDS}
STAFF_EDITABLE_FIELDS: set[str] = {f.name for f in LISTING_FIELDS if f.is_staff_editable}
ADMIN_EDITABLE_FIELDS: set[str] = {f.name for f in LISTING_FIELDS if f.is_admin_editable}
CRITICAL_FIELDS: set[str] = {f.name for f in LISTING_FIELDS if f.is_critical}
READ_ONLY_FIELDS: set[str] = {f.name for f in LISTING_FIELDS if f.is_read_only}
