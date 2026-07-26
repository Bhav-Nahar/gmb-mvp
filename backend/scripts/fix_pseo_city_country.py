#!/usr/bin/env python3
"""Re-file pSEO pages whose city is not in their declared country.

1,034 of the 1,809 pages under /en-in/gbp-management/ are for cities in nine other
countries (Bangkok, Jakarta, Manila, Riyadh, Doha...). They were generated with
country="in", so they serve under India's locale prefix and India's hreflang.

`country` is the only field that needs to change: it derives the locale, the URL
prefix and the hreflang. `slug` is globally unique and stays the same, so there is
no collision risk and no content edit.

    /en-in/gbp-management/cafes-in-bangkok  ->  /en-th/gbp-management/cafes-in-bangkok

USAGE
    python scripts/fix_pseo_city_country.py                  # dry run (default)
    python scripts/fix_pseo_city_country.py --report         # per-city breakdown
    python scripts/fix_pseo_city_country.py --apply          # write, then revalidate

Point DATABASE_URL at the target database. Against Supabase, take a snapshot first:
this rewrites 1,034 live rows.

CAVEAT: the mapping below is hand-checked geography, not a gazetteer. Review it with
--report before applying. Two slugs arrived mangled from the generator
(`las-pi-as` = Las Piñas, `para-aque` = Parañaque, both Philippines) — they are
mapped correctly here but the slugifier that produced them still drops "ñ".
"""
import argparse
import collections
import sys

sys.path.insert(0, "/app" if __import__("os").path.isdir("/app/app") else ".")

from app.db.session import SessionLocal            # noqa: E402
from app.models.pseo_page import PseoPage          # noqa: E402

# city_slug -> ISO-3166 alpha-2 the page should carry.
CITY_COUNTRY: dict[str, str] = {}
for _cc, _cities in {
    "th": "bangkok chiang-mai chiang-rai hat-yai hua-hin khon-kaen koh-samui "
          "nonthaburi pattaya phuket",
    "id": "bandung batam bekasi bogor denpasar depok jakarta makassar malang medan "
          "palembang semarang surabaya tangerang yogyakarta",
    "ph": "angeles bacolod baguio cagayan-de-oro cebu-city davao-city iloilo-city "
          "las-pi-as makati mandaue manila para-aque pasig quezon-city taguig",
    "my": "cyberjaya george-town ipoh johor-bahru kota-kinabalu kuala-lumpur kuching "
          "malacca petaling-jaya putrajaya shah-alam subang-jaya",
    "sa": "abha al-ahsa dammam dhahran jeddah jubail khobar mecca medina riyadh "
          "tabuk taif",
    "qa": "al-khor al-rayyan al-wakrah doha lusail",
    "bh": "budaiya isa-town manama muharraq riffa",
    "kw": "fahaheel farwaniya hawalli kuwait-city mangaf salmiya",
    "om": "muscat nizwa salalah seeb sohar sur",
}.items():
    for _c in _cities.split():
        CITY_COUNTRY[_c] = _cc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    ap.add_argument("--report", action="store_true", help="per-city breakdown")
    ap.add_argument("--no-revalidate", action="store_true", help="skip the ISR/cache purge")
    ap.add_argument("--revalidate-only", action="store_true",
                    help="rows already moved (e.g. by SQL): just purge caches for the OLD and NEW paths")
    args = ap.parse_args()

    db = SessionLocal()
    rows = (db.query(PseoPage)
            .filter(PseoPage.city_slug.in_(list(CITY_COUNTRY)))
            .order_by(PseoPage.city_slug, PseoPage.slug)
            .all())
    # Only rows whose country is actually wrong; re-running must be a no-op.
    wrong = [p for p in rows if p.country != CITY_COUNTRY[p.city_slug]]

    by_target = collections.Counter(CITY_COUNTRY[p.city_slug] for p in wrong)
    by_source = collections.Counter(p.country for p in wrong)
    print(f"matched {len(rows)} pages in the mapping; {len(wrong)} have the wrong country\n")
    print("  currently filed as:", dict(by_source))
    print("  should move to    :", dict(sorted(by_target.items(), key=lambda kv: -kv[1])))

    if args.report:
        print("\n  per city:")
        per = collections.Counter((p.city_slug, p.country, CITY_COUNTRY[p.city_slug]) for p in wrong)
        for (city, was, now), n in sorted(per.items()):
            print(f"    {city:18} {was} -> {now}   {n:>3} pages")

    if not wrong and not args.revalidate_only:
        print("\nnothing to do.")
        return 0

    print("\n  examples:")
    for p in wrong[:5]:
        now = CITY_COUNTRY[p.city_slug]
        print(f"    /en-{p.country}/gbp-management/{p.slug}  ->  /en-{now}/gbp-management/{p.slug}")

    if not args.apply and not args.revalidate_only:
        print(f"\nDRY RUN. {len(wrong)} rows would change. Re-run with --apply to write.")
        return 0

    if args.revalidate_only:
        # The UPDATE already ran (SQL path). Every matched row is now correct, so the
        # OLD locale is whatever it was before: for this migration, always "in".
        touched = [{"slug": p.slug, "old": "in", "new": p.country,
                    "industry_slug": p.industry_slug} for p in rows]
        print(f"\nrevalidate-only: purging {len(touched)} slugs on both old and new paths.")
    else:
        # Capture the OLD locale before mutating, so both URLs can be revalidated.
        touched = [{"slug": p.slug, "old": p.country, "new": CITY_COUNTRY[p.city_slug],
                    "industry_slug": p.industry_slug} for p in wrong]
        for p in wrong:
            p.country = CITY_COUNTRY[p.city_slug]
        db.commit()
        print(f"\nupdated {len(wrong)} rows.")

    if args.no_revalidate:
        print("skipped revalidation (--no-revalidate); the old URLs will serve stale until TTL.")
        return 0

    # Purge both the backend cache and the frontend ISR entry for the OLD and NEW
    # paths. Without the old one, the vacated URL keeps serving a 200 from cache.
    try:
        from app.core.redis_client import get_redis
        from app.services.revalidation_service import trigger_bulk_pseo_revalidation
        r = get_redis()
        keys = [f"public_pseo:{t['slug']}" for t in touched]
        for i in range(0, len(keys), 500):
            r.delete(*keys[i:i + 500])
        for side in ("old", "new"):
            entries = [{"slug": t["slug"], "country": t[side], "industry_slug": t["industry_slug"]}
                       for t in touched]
            for i in range(0, len(entries), 200):
                trigger_bulk_pseo_revalidation(entries[i:i + 200])
        print("purged caches and revalidated old + new paths.")
    except Exception as e:                                    # noqa: BLE001
        print(f"WARNING: revalidation failed ({e}). Rows are updated; flush caches manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
