"""Geo-grid local rank scanning via DataForSEO Google Maps SERP.

For each point of an N×N grid around a location we run the keyword as if a searcher
were standing there, then read the business's Maps rank. One vendor (DataForSEO),
one endpoint family (serp/google/maps).

Cost lever: we use the *queued task* endpoints (task_post up to 100 points per POST,
then tasks_ready + task_get), which are markedly cheaper per point than the live
endpoint. The trade is latency — results aren't instant, so we poll until ready.
"""
from __future__ import annotations

import asyncio
import json
import math

# Pricing for the feature, in AI credits, keyed by grid size. Tunable — COGS is
# tiny (~$0.005–0.05/scan), so this is a packaging knob, not a cost pass-through.
CREDITS_BY_GRID = {3: 1, 5: 2, 7: 4, 9: 6}
LOCAL_GRID_SCAN_ACTION = "run_local_grid_scan"  # must be in plan_config.USER_AI_ACTIONS

_ZOOM = 13      # Maps zoom for each point's search
_DEPTH = 20     # how many results to pull per point (rank window: top 20)
_MILES_PER_DEG_LAT = 69.0
_TASK_POLL_INTERVAL = 5.0   # seconds between tasks_ready polls
_TASK_MAX_WAIT = 540.0      # give up waiting on queued tasks (under the 600s scan lock)


def scan_price(grid_size: int) -> int:
    return CREDITS_BY_GRID.get(grid_size, 6)


def build_grid(lat: float, lng: float, grid_size: int, radius_miles: float) -> list[dict]:
    """N×N points around (lat,lng). radius_miles = centre -> outermost ring.

    row 0 = north (top), col 0 = west (left), so the grid renders like a map.
    """
    half = (grid_size - 1) / 2
    step = radius_miles / half if half else 0.0
    cos_lat = math.cos(math.radians(lat)) or 1e-6
    points: list[dict] = []
    for r in range(grid_size):
        for c in range(grid_size):
            i = half - r   # north positive
            j = c - half   # east positive
            plat = lat + (i * step) / _MILES_PER_DEG_LAT
            plng = lng + (j * step) / (_MILES_PER_DEG_LAT * cos_lat)
            points.append({"row": r, "col": c, "lat": round(plat, 6), "lng": round(plng, 6)})
    return points


def parse_cell(items: list[dict], business_name: str, business_place_id: str | None = None,
               top_n: int = 10) -> tuple[int | None, str | None, list[dict], dict | None]:
    """From one point's results return: our rank, the #1 competitor, the top N rows
    (for the popup), and our business's real coordinates (when found).

    Identify our business by Google place_id when we have one (exact), falling back to a
    loose name match. The place_id match removes the false 'not found' that name-only
    matching can cause. Coordinates come from the matched result so future scans can be
    centred exactly on the storefront.
    """
    target = (business_name or "").strip().lower()
    pid = (business_place_id or "").strip()
    rows: list[dict] = []
    for it in items:
        ra = it.get("rank_absolute")
        title = (it.get("title") or "").strip()
        if ra is None or not title:
            continue
        rating_obj = it.get("rating") if isinstance(it.get("rating"), dict) else {}
        rows.append({
            "rank": ra,
            "name": title,
            "rating": rating_obj.get("value"),
            "reviews": rating_obj.get("votes_count"),
            "category": it.get("category"),
            "additional_categories": it.get("additional_categories") or [],
            "total_photos": it.get("total_photos"),
            "price_level": it.get("price_level"),
            "is_claimed": it.get("is_claimed"),
            "domain": it.get("domain"),
            "address": it.get("address"),
            "image": it.get("main_image"),
            "place_id": it.get("place_id"),
            "lat": it.get("latitude"),
            "lng": it.get("longitude"),
        })
    rows.sort(key=lambda r: r["rank"])

    # Find "us": exact by place_id first, else loose by name.
    me = None
    if pid:
        me = next((r for r in rows if r.get("place_id") and r["place_id"] == pid), None)
    if me is None and target:
        me = next((r for r in rows if target in r["name"].lower() or r["name"].lower() in target), None)

    rank = me["rank"] if me else None
    business_coords = None
    if me and me.get("lat") is not None and me.get("lng") is not None:
        business_coords = {"latitude": me["lat"], "longitude": me["lng"]}

    top_competitor = next((r["name"] for r in rows if r is not me), None)
    top_results = [{k: v for k, v in r.items() if not k.startswith("_")} for r in rows[:top_n]]
    return rank, top_competitor, top_results, business_coords


async def _post_tasks(client, base: str, keyword: str, points: list[dict],
                      language_code: str) -> dict[str, dict]:
    """Submit every grid point as a queued task (cheaper than live). Up to 100
    points per POST. Returns a mapping of DataForSEO task id -> grid point."""
    tag_to_point = {f"{p['row']}_{p['col']}": p for p in points}
    id_to_point: dict[str, dict] = {}
    for i in range(0, len(points), 100):
        chunk = points[i:i + 100]
        payload = [{
            "keyword": keyword,
            "location_coordinate": f"{p['lat']},{p['lng']},{_ZOOM}",
            "language_code": language_code,
            "device": "mobile",
            "os": "android",
            "depth": _DEPTH,
            "tag": f"{p['row']}_{p['col']}",
        } for p in chunk]
        resp = await client.post(f"{base}/v3/serp/google/maps/task_post", json=payload)
        resp.raise_for_status()
        for task in (resp.json().get("tasks") or []):
            # 20100 = "Task Created", 20000 = OK. Anything else is a hard failure.
            if task.get("status_code") not in (20000, 20100):
                raise RuntimeError(f"DataForSEO task_post error {task.get('status_code')}: {task.get('status_message')}")
            tag = (task.get("data") or {}).get("tag")
            point = tag_to_point.get(tag)
            if task.get("id") and point is not None:
                id_to_point[task["id"]] = point
    return id_to_point


async def _get_task_items(client, base: str, task_id: str) -> list[dict]:
    """Fetch one completed task's result rows."""
    resp = await client.get(f"{base}/v3/serp/google/maps/task_get/advanced/{task_id}")
    resp.raise_for_status()
    tasks = resp.json().get("tasks") or []
    task = tasks[0] if tasks else {}
    if task.get("status_code") != 20000:
        return []
    result = task.get("result") or []
    return (result[0].get("items") if result and result[0] else None) or []


async def _collect_tasks(client, base: str, id_to_point: dict[str, dict]) -> list[tuple[dict, list[dict]]]:
    """Poll tasks_ready until all our queued tasks complete, pulling each result as
    it becomes ready. If any task is still pending at the deadline we raise, so the
    scan fails cleanly (and is not charged) rather than silently returning a grid
    full of false 'not found' cells."""
    pending = dict(id_to_point)
    out: list[tuple[dict, list[dict]]] = []
    waited = 0.0
    while pending and waited < _TASK_MAX_WAIT:
        await asyncio.sleep(_TASK_POLL_INTERVAL)
        waited += _TASK_POLL_INTERVAL
        resp = await client.get(f"{base}/v3/serp/google/maps/tasks_ready")
        resp.raise_for_status()
        ready_ids = {
            r.get("id")
            for t in (resp.json().get("tasks") or [])
            for r in (t.get("result") or [])
            if r.get("id")
        }
        for tid in [t for t in pending if t in ready_ids]:
            items = await _get_task_items(client, base, tid)
            out.append((pending.pop(tid), items))
    if pending:
        raise RuntimeError(f"DataForSEO: {len(pending)}/{len(id_to_point)} grid tasks "
                           f"did not complete within {_TASK_MAX_WAIT:.0f}s")
    return out


async def run_scan(*, lat: float, lng: float, keyword: str, grid_size: int,
                   radius_miles: float, business_name: str, business_place_id: str | None = None,
                   language_code: str = "en") -> dict:
    import httpx
    from app.core.config import settings  # lazy: module import stays stdlib-only so the self-check needs no deps/env
    login, password = settings.DATAFORSEO_LOGIN, settings.DATAFORSEO_PASSWORD
    if not login or not password:
        raise RuntimeError("DataForSEO credentials are not configured (DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD).")

    points = build_grid(lat, lng, grid_size, radius_miles)
    base = settings.DATAFORSEO_BASE_URL.rstrip("/")

    async with httpx.AsyncClient(timeout=90.0, auth=(login, password)) as client:
        id_to_point = await _post_tasks(client, base, keyword, points, language_code)
        collected = await _collect_tasks(client, base, id_to_point)

    results = []
    for p, items in collected:
        rank, top, top_results, bcoords = parse_cell(items, business_name, business_place_id)
        results.append(({**p, "rank": rank, "top_competitor": top, "top_results": top_results}, bcoords))

    # restore row-major order (collection order follows task readiness, not the grid)
    results.sort(key=lambda r: (r[0]["row"], r[0]["col"]))
    cells = [cell for cell, _ in results]
    business_coords = next((bc for _, bc in results if bc), None)
    ranks = [c["rank"] for c in cells if c["rank"]]
    avg_rank = round(sum(ranks) / len(ranks), 1) if ranks else None
    solv = round(100 * sum(1 for c in cells if c["rank"] and c["rank"] <= 3) / len(cells), 1) if cells else 0.0
    return {"cells": cells, "avg_rank": avg_rank, "solv": solv,
            "found_count": len(ranks), "total_cells": len(cells), "business_coords": business_coords}


async def geocode(query: str) -> tuple[float, float] | None:
    """Address/text -> (lat, lng) via the free OpenStreetMap Nominatim geocoder.

    ponytail: free, no API key; Nominatim asks for <=1 req/sec + a real User-Agent,
    which a single scan-centre lookup easily respects. Swap to a paid geocoder if volume grows.
    """
    import httpx
    q = (query or "").strip()
    if not q:
        return None
    headers = {"User-Agent": "pinzo-localrank/1.0 (local rank grid geocoding)"}
    async with httpx.AsyncClient(timeout=20.0, headers=headers) as c:
        r = await c.get("https://nominatim.openstreetmap.org/search",
                        params={"q": q, "format": "json", "limit": 1})
        r.raise_for_status()
        arr = r.json()
    if arr:
        return float(arr[0]["lat"]), float(arr[0]["lon"])
    return None


def _address_query(addr: dict | None) -> str:
    """Build a geocodable string from a GBP PostalAddress dict."""
    if not isinstance(addr, dict):
        return ""
    parts = list(addr.get("addressLines") or [])
    for k in ("locality", "administrativeArea", "postalCode", "regionCode"):
        v = addr.get(k)
        if v:
            parts.append(str(v))
    return ", ".join(p for p in parts if p)


def _address_candidates(addr: dict | None) -> list[str]:
    """Ordered geocoding queries, reliable -> coarse. A full street address often
    fails on Nominatim (floor/office noise), so fall back to postal, road, then city."""
    if not isinstance(addr, dict):
        return []
    lines = [str(x) for x in (addr.get("addressLines") or []) if x]
    locality, admin = addr.get("locality"), addr.get("administrativeArea")
    postal, region = addr.get("postalCode"), addr.get("regionCode")
    def j(*p):
        return ", ".join(str(x) for x in p if x)
    cands = [
        j(postal, locality, admin, region),                        # postal area: precise + reliable
        j(lines[-1] if lines else None, locality, admin, region),  # road + city
        _address_query(addr),                                      # full street address
        j(locality, admin, region),                                # city centre (last resort)
    ]
    seen, out = set(), []
    for c in (x.strip() for x in cands):
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


async def resolve_center(latlng, gbp_raw, address) -> tuple[float, float] | None:
    """Pick a grid centre: the stored latlng if present, else geocode the address.

    GBP frequently omits latlng, so geocoding the storefront address is the fallback
    that keeps the feature usable. Tries precise->coarse queries until one resolves.
    """
    if isinstance(latlng, dict):
        lat, lng = latlng.get("latitude"), latlng.get("longitude")
        if lat is not None and lng is not None:
            return float(lat), float(lng)
    addr = gbp_raw.get("storefrontAddress") if isinstance(gbp_raw, dict) else None
    if not isinstance(addr, dict) and address:
        try:
            addr = json.loads(address)
        except (ValueError, TypeError):
            addr = None
    for i, q in enumerate(_address_candidates(addr)):
        if i:
            await asyncio.sleep(1.0)  # Nominatim politeness between fallback attempts
        hit = await geocode(q)
        if hit:
            return hit
    return None


async def scan_for_location(*, latlng, gbp_raw, address, keyword, grid_size,
                            radius_miles, business_name, business_place_id=None,
                            language_code: str = "en") -> dict:
    """Resolve the centre (stored latlng or geocoded address), then run the grid scan."""
    center = await resolve_center(latlng, gbp_raw, address)
    if center is None:
        raise RuntimeError("Could not determine map coordinates for this location "
                           "(no latlng, and address geocoding failed).")
    lat, lng = center
    return await run_scan(lat=lat, lng=lng, keyword=keyword, grid_size=grid_size,
                          radius_miles=radius_miles, business_name=business_name,
                          business_place_id=business_place_id, language_code=language_code)


if __name__ == "__main__":
    # ponytail: network-free check of the only logic that breaks silently —
    # grid geometry and rank parsing.
    g = build_grid(19.2307, 72.8567, 3, 1.0)   # Borivali-ish
    assert len(g) == 9, len(g)
    centre = g[4]  # row1,col1
    assert abs(centre["lat"] - 19.2307) < 1e-6 and abs(centre["lng"] - 72.8567) < 1e-6, centre
    north, south = g[1], g[7]  # same col, top vs bottom row
    assert north["lat"] > south["lat"], (north, south)          # row 0 is north
    assert abs((north["lat"] - centre["lat"]) - 1.0 / 69.0) < 1e-4  # 1 mile ring
    west, east = g[3], g[5]
    assert west["lng"] < east["lng"], (west, east)              # col 0 is west

    items = [
        {"rank_absolute": 1, "title": "Other Jeweller", "rating": {"value": 4.6, "votes_count": 88}, "place_id": "OTHER"},
        {"rank_absolute": 4, "title": "My Diamond Shop", "place_id": "MINE", "latitude": 19.1, "longitude": 72.8},
        {"rank_absolute": 2, "title": "Random Cafe", "place_id": "CAFE"},
    ]
    # exact place_id match wins (even with a mismatched name) and captures our coords
    rank, top, results, coords = parse_cell(items, "totally different name", business_place_id="MINE")
    assert rank == 4 and top == "Other Jeweller", (rank, top)
    assert coords == {"latitude": 19.1, "longitude": 72.8}, coords
    assert [r["rank"] for r in results] == [1, 2, 4], results
    assert "_place_id" not in results[0] and "place_id" not in results[0], results[0]
    assert results[0]["name"] == "Other Jeweller" and results[0]["rating"] == 4.6, results
    # name fallback when no place_id is supplied
    r2, t2, _, _ = parse_cell(items, "My Diamond Shop")
    assert r2 == 4, r2
    # not present at all -> not found, no coords
    r3, t3, _, c3 = parse_cell(items, "Nope", business_place_id="NOPID")
    assert r3 is None and t3 == "Other Jeweller" and c3 is None, (r3, t3, c3)
    assert scan_price(7) == 4 and scan_price(99) == 6

    assert _address_query({"addressLines": ["12 Main Rd"], "locality": "Mumbai",
                           "administrativeArea": "Maharashtra", "regionCode": "IN"}) == \
        "12 Main Rd, Mumbai, Maharashtra, IN"
    assert _address_query(None) == "" and _address_query({}) == ""

    _c = _address_candidates({"addressLines": ["Flr 2", "SV Road"], "locality": "Mumbai",
                              "administrativeArea": "Maharashtra", "postalCode": "400062", "regionCode": "IN"})
    assert _c[0] == "400062, Mumbai, Maharashtra, IN", _c
    assert any("SV Road" in c for c in _c) and _address_candidates(None) == []

    print("local_rank_service self-check passed")
