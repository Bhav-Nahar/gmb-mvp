import sys; sys.path.insert(0,'/app')
from app.db.session import SessionLocal
from app.core.redis_client import get_redis
from app.services.revalidation_service import trigger_bulk_pseo_revalidation
from app.models.pseo_page import PseoPage
MOVED = ('th','id','ph','my','sa','qa','bh','kw','om')   # markets created by the migration
db, r = SessionLocal(), get_redis()
rows = db.query(PseoPage.slug, PseoPage.country, PseoPage.industry_slug).filter(PseoPage.country.in_(MOVED)).all()
print('rows to purge:', len(rows))
keys = ['public_pseo:%s' % s for s, _, _ in rows]
for i in range(0, len(keys), 500):
    r.delete(*keys[i:i+500])
for country_of in (lambda row: 'in', lambda row: row[1]):     # OLD path, then NEW path
    entries = [{'slug': s, 'country': country_of((s,c,i)), 'industry_slug': i} for s, c, i in rows]
    for i in range(0, len(entries), 200):
        trigger_bulk_pseo_revalidation(entries[i:i+200])
print('purged %d cache keys and revalidated both old and new paths' % len(keys))
