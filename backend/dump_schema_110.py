
from app.db.session import SessionLocal
from app.api.dynamic_attributes import get_form_schema
from app.models.user import User
import asyncio
import json

async def run():
    db = SessionLocal()
    try:
        # Mock staff user
        staff = db.query(User).filter(User.organization_id == 226).first()
        res = await get_form_schema(110, db, staff)
        print(f"Total Schema items: {len(res['schema'])}")
        groups = {}
        for f in res['schema']:
            g = f['group_display_name'] or "General"
            if g not in groups: groups[g] = []
            groups[g].append(f['display_name'])
        
        for g, items in sorted(groups.items()):
            print(f"Group: {g}")
            for item in sorted(items):
                print(f"  - {item}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    asyncio.run(run())
