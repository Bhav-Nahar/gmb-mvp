"""Runtime feature flags: DB override (set from the super-admin panel) wins,
env/config value is the default when no row exists."""
import time

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.app_setting import AppSetting

# Per-process TTL cache: flags are read on hot polled endpoints (/billing/status),
# and each uncached read is a DB round-trip (~100ms on cross-region Supabase).
# Trade-off: another worker sees a toggle up to TTL late — fine for feature flags.
_FLAG_TTL_SECONDS = 60.0
_flag_cache: dict[str, tuple[float, bool]] = {}


def clear_flag_cache() -> None:
    """Test hook / manual reset."""
    _flag_cache.clear()


def get_flag(db: Session, key: str, default: bool) -> bool:
    hit = _flag_cache.get(key)
    if hit and (time.monotonic() - hit[0]) < _FLAG_TTL_SECONDS:
        return hit[1]
    row = db.get(AppSetting, key)
    value = row.value == "true" if row else default
    _flag_cache[key] = (time.monotonic(), value)
    return value


def set_flag(db: Session, key: str, value: bool) -> None:
    """Upsert a flag override. Caller commits. Write-through so this process
    serves the new value immediately."""
    row = db.get(AppSetting, key)
    if row:
        row.value = "true" if value else "false"
    else:
        db.add(AppSetting(key=key, value="true" if value else "false"))
    _flag_cache[key] = (time.monotonic(), value)


def india_phone_trial_enabled(db: Session) -> bool:
    """ON = a +91 phone starts the trial with no card/UPI mandate; OFF = India goes
    through the Razorpay mandate checkout like the rest of the world."""
    return get_flag(db, "india_phone_trial", settings.INDIA_PHONE_TRIAL)


def row_phone_trial_enabled(db: Session) -> bool:
    """Rest-of-world twin: ON = a non-+91 phone starts the trial with no card;
    OFF (default) = a card mandate is required outside India."""
    return get_flag(db, "row_phone_trial", settings.ROW_PHONE_TRIAL)
