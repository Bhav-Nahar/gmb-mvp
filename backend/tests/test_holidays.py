"""Smoke check for holiday CSV import: parsing, bad rows, and idempotent re-upload.

Run: pytest backend/tests/test_holidays.py
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Holiday
from app.services import holiday_service


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Holiday.__table__])
    return sessionmaker(bind=engine)()


def test_import_csv_parses_and_is_idempotent():
    db = _session()
    csv = (
        b"date,name,category,region\n"
        b"2026-10-21,Diwali,festival,\n"
        b"2026-01-14,Pongal,festival,TN\n"
        b"bad,Broken,,\n"          # bad date -> error
        b",,,\n"                    # blank -> skipped silently
    )
    r1 = holiday_service.import_csv(db, csv, created_by_user_id=None)
    assert r1.created == 2, r1
    assert any("Broken" in e or "bad" in e for e in r1.errors)

    # Re-uploading the same file creates nothing new (unique date+name+region).
    r2 = holiday_service.import_csv(db, csv, created_by_user_id=None)
    assert r2.created == 0
    assert r2.skipped >= 2

    assert db.query(Holiday).count() == 2


if __name__ == "__main__":
    test_import_csv_parses_and_is_idempotent()
    print("ok")
