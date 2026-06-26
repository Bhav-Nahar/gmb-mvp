"""Holiday seeding (open-source library) + CSV import.

The heavy lifting is done by the `holidays` package, which already knows Indian
national and per-state holidays/festivals for any year — so the super-admin gets
the calendar populated with zero manual data entry. CSV import is the override
for the handful the library misses or business-specific dates.
"""
import csv
import io
import logging
from datetime import date as date_type
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.holiday import Holiday
from app.schemas.holidays import HolidayImportResult

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"festival", "holiday", "observance"}


def _existing_keys(db: Session) -> set:
    """All (date, name, region) keys already stored — for idempotent inserts."""
    rows = db.query(Holiday.date, Holiday.name, Holiday.region).all()
    return {(d, n, r or "") for d, n, r in rows}


def _add_rows(
    db: Session,
    rows: List[Tuple[date_type, str, str, Optional[str], str]],  # (date, name, category, region, source)
    created_by_user_id: Optional[int],
) -> Tuple[int, int]:
    """Insert rows, skipping any that collide with existing keys. Returns (created, skipped)."""
    seen = _existing_keys(db)
    created = 0
    skipped = 0
    for d, name, category, region, source in rows:
        key = (d, name, region or "")
        if key in seen:
            skipped += 1
            continue
        seen.add(key)
        db.add(Holiday(
            date=d, name=name, category=category, region=region,
            country="IN", source=source, created_by_user_id=created_by_user_id,
        ))
        created += 1
    db.commit()
    return created, skipped


def seed_from_library(
    db: Session, year: int, subdivisions: List[str], created_by_user_id: Optional[int]
) -> HolidayImportResult:
    try:
        import holidays as holidays_lib
    except ImportError:
        return HolidayImportResult(created=0, skipped=0, errors=[
            "The 'holidays' package is not installed. Run: pip install holidays"
        ])

    rows: List[Tuple] = []
    errors: List[str] = []

    # National holidays come back inside every state's list too, so seed national
    # once (region=None) and, for each state, store ONLY the festivals that aren't
    # already national — otherwise Independence Day etc. gets duplicated per state.
    try:
        national = holidays_lib.country_holidays("IN", years=year)
    except Exception as e:
        return HolidayImportResult(created=0, skipped=0, errors=[f"national: {e}"])
    # The library joins multiple same-day holidays into one "A; B" string — split
    # them so each festival is its own clean row and dedup works name-by-name.
    def _names(raw: str) -> List[str]:
        return [p.strip() for p in raw.split(";") if p.strip()]

    national_keys = set()
    for d, raw in national.items():
        for name in _names(raw):
            national_keys.add((d, name))
            rows.append((d, name, "festival", None, "library"))

    for subdiv in [s.strip().upper() for s in subdivisions if s.strip()]:
        try:
            cal = holidays_lib.country_holidays("IN", years=year, subdiv=subdiv)
        except Exception as e:  # bad subdiv code, etc.
            errors.append(f"subdiv {subdiv}: {e}")
            continue
        for d, raw in cal.items():
            for name in _names(raw):
                if (d, name) in national_keys:
                    continue  # national holiday repeated inside the state list — skip
                rows.append((d, name, "festival", subdiv, "library"))

    created, skipped = _add_rows(db, rows, created_by_user_id)
    return HolidayImportResult(created=created, skipped=skipped, errors=errors)


def import_csv(db: Session, content: bytes, created_by_user_id: Optional[int]) -> HolidayImportResult:
    """Parse a CSV with headers: date, name, [category], [region].

    date must be ISO (YYYY-MM-DD). Unknown categories fall back to 'festival'.
    """
    errors: List[str] = []
    rows: List[Tuple] = []
    try:
        text = content.decode("utf-8-sig")  # tolerate Excel BOM
    except UnicodeDecodeError:
        return HolidayImportResult(created=0, skipped=0, errors=["File must be UTF-8 encoded CSV."])

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "date" not in reader.fieldnames or "name" not in reader.fieldnames:
        return HolidayImportResult(created=0, skipped=0, errors=["CSV must have 'date' and 'name' columns."])

    skipped_blank = 0
    for i, row in enumerate(reader, start=2):  # row 1 is the header
        raw_date = (row.get("date") or "").strip()
        name = (row.get("name") or "").strip()
        if not raw_date and not name:
            skipped_blank += 1
            continue
        if not raw_date or not name:
            errors.append(f"row {i}: missing date or name")
            continue
        try:
            d = date_type.fromisoformat(raw_date)
        except ValueError:
            errors.append(f"row {i}: bad date '{raw_date}' (expected YYYY-MM-DD)")
            continue
        category = (row.get("category") or "festival").strip().lower()
        if category not in VALID_CATEGORIES:
            category = "festival"
        region = (row.get("region") or "").strip().upper() or None
        rows.append((d, name, category, region, "csv"))

    created, skipped = _add_rows(db, rows, created_by_user_id)
    return HolidayImportResult(created=created, skipped=skipped + skipped_blank, errors=errors)
