"""Central role definitions for RBAC.

String values MUST match what is persisted in users.role / invites.role so this is
a drop-in replacement for the bare string literals scattered across the codebase.
Using these constants instead of inline strings prevents typo-class bugs (e.g. the
legacy "Staff" check that silently never matched after the rename to "Store Manager").
"""


class Role:
    OWNER = "Owner"
    ADMIN = "Admin"
    REGIONAL_MANAGER = "Regional Manager"
    STORE_MANAGER = "Store Manager"
    VIEWER = "Viewer"


# Role groups used by RoleChecker dependencies and authorization helpers.
ADMIN_ROLES = frozenset({Role.OWNER, Role.ADMIN})
STAFF_ROLES = frozenset({Role.OWNER, Role.ADMIN, Role.REGIONAL_MANAGER, Role.STORE_MANAGER})
TEAM_VIEWER_ROLES = frozenset({Role.OWNER, Role.ADMIN, Role.REGIONAL_MANAGER})
REGIONAL_MANAGER_PLUS = TEAM_VIEWER_ROLES

# Roles that always have implicit access to every location in their organization
# (i.e. get_user_location_ids returns None for them).
ORG_WIDE_ROLES = ADMIN_ROLES
