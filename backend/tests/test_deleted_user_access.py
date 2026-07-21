"""A soft-deleted user must stop being usable everywhere, not just at the API.

Deleting a user is a revocation. The API blocked them immediately (deps.py), but
several background paths picked users by `is_active` alone — so a revoked account's
Google token kept driving syncs, and they kept receiving the weekly report by email,
until the purge task removed the row days later.
"""
import ast
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent

# Every place that selects a User (or their OAuth token) to act on the org's behalf.
GUARDED_SITES = [
    ("app/tasks.py", "sync_all_organizations_task"),          # picks the sync driver
    ("app/providers/factory.py", "get_provider"),             # picks the token for ALL Google calls
    ("app/api/users.py", None),
    ("app/api/locations.py", None),
    ("app/tasks_reports.py", "send_weekly_reports_task"),     # emails org data to the user
]


def _user_filters(path: pathlib.Path):
    """Every filter() call in the file that constrains User.is_active."""
    tree = ast.parse(path.read_text())
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "filter"):
            continue
        src = ast.unparse(node)
        if "User.is_active" in src:
            found.append(src)
    return found


def test_every_user_picker_also_excludes_deleted_users():
    missing = []
    for rel, _ in GUARDED_SITES:
        for src in _user_filters(BACKEND / rel):
            if "User.deleted_at" not in src:
                missing.append(f"{rel}: {src[:120]}")
    assert not missing, (
        "these select an active user without excluding soft-deleted ones, so a revoked "
        "account keeps acting for the org:\n  " + "\n  ".join(missing)
    )


def test_the_guard_is_actually_present_somewhere_in_each_file():
    """Guards against the filter above being refactored into a shape ast misses."""
    for rel, _ in GUARDED_SITES:
        text = (BACKEND / rel).read_text()
        assert "User.deleted_at.is_(None)" in text, f"{rel} lost its deleted_at guard"
