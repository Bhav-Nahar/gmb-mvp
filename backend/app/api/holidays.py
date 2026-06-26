from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, Query, UploadFile, File, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import staff_required, superadmin_required
from app.models.user import User
from app.models.holiday import Holiday
from app.schemas.holidays import (
    HolidayOut, HolidayListResponse, HolidayCreate, HolidaySeedRequest, HolidayImportResult,
)
from app.services import holiday_service

router = APIRouter()


@router.get("", response_model=HolidayListResponse)
def list_holidays(
    start: Optional[date_type] = Query(None, description="Inclusive range start (YYYY-MM-DD)"),
    end: Optional[date_type] = Query(None, description="Inclusive range end (YYYY-MM-DD)"),
    region: Optional[str] = Query(None, description="Filter to a region/subdivision (e.g. TN)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    """Holidays in a date range, for the calendar overlay. Readable by any staff."""
    query = db.query(Holiday)
    if start:
        query = query.filter(Holiday.date >= start)
    if end:
        query = query.filter(Holiday.date <= end)
    if region:
        # National (null region) is always relevant; add the requested state on top.
        query = query.filter((Holiday.region == region.upper()) | (Holiday.region.is_(None)))
    rows = query.order_by(Holiday.date.asc()).all()
    return HolidayListResponse(holidays=rows, total=len(rows))


@router.post("", response_model=HolidayOut)
def create_holiday(
    payload: HolidayCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(superadmin_required),
):
    h = Holiday(
        date=payload.date, name=payload.name, category=payload.category,
        region=(payload.region or None), country=payload.country,
        source="manual", created_by_user_id=current_user.id,
    )
    db.add(h)
    db.commit()
    db.refresh(h)
    return h


@router.post("/seed", response_model=HolidayImportResult)
def seed_holidays(
    payload: HolidaySeedRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(superadmin_required),
):
    """Auto-populate from the open-source `holidays` package — no manual entry."""
    return holiday_service.seed_from_library(
        db, payload.year, payload.subdivisions, current_user.id
    )


@router.post("/import", response_model=HolidayImportResult)
async def import_holidays_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(superadmin_required),
):
    """CSV override. Headers: date,name,[category],[region]. Idempotent on re-upload."""
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")
    content = await file.read()
    if len(content) > 2 * 1024 * 1024:  # 2MB — holidays files are tiny
        raise HTTPException(status_code=400, detail="File too large (max 2MB)")
    return holiday_service.import_csv(db, content, current_user.id)


@router.delete("/{holiday_id}", status_code=204)
def delete_holiday(
    holiday_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(superadmin_required),
):
    h = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if not h:
        raise HTTPException(status_code=404, detail="Holiday not found")
    db.delete(h)
    db.commit()
