# Backend Operational Notes

## Migration Gate (Required Before API/Workers)

Before starting `uvicorn`, `celery worker`, or `celery beat`, ensure the database is at Alembic head.

```powershell
alembic current
alembic heads
alembic upgrade head
```

If `alembic current` does not match the single revision returned by `alembic heads`, do not start workers yet.

This is required for sync stability because runtime paths depend on newer schema fields, including `locations.google_account_id` and RBAC-related columns.
