"""Competitor tracking harvested for free from local-rank geo-grid scans.

Every completed scan already contains the local pack per grid cell (name, place_id,
rating, review count, photos). We aggregate that per tracked competitor into one
snapshot row per scan — no extra API spend. A paid Business Data refresh can later
write the same snapshot rows for scan-independent freshness.
"""
import logging
import math

from sqlalchemy.orm import Session

from app.models.competitor import TrackedCompetitor, CompetitorSnapshot
from app.models.local_rank_scan import LocalRankScan

logger = logging.getLogger(__name__)


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Haversine great-circle distance in km."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 2)


def _iter_cell_results(scan: LocalRankScan):
    for cell in (scan.cells or []):
        for row in (cell.get("top_results") or []):
            yield row


def _aggregate(scan: LocalRankScan, place_id: str, name: str) -> dict | None:
    """Aggregate one business's presence across a scan's cells."""
    ranks, rating, reviews, photos = [], None, None, None
    name_l = (name or "").strip().lower()
    for row in _iter_cell_results(scan):
        match = (row.get("place_id") == place_id) if row.get("place_id") else (
            name_l and (row.get("name") or "").strip().lower() == name_l)
        if not match:
            continue
        if row.get("rank") is not None:
            ranks.append(row["rank"])
        rating = row.get("rating") or rating
        reviews = max(reviews or 0, row.get("reviews") or 0) or reviews
        photos = row.get("total_photos") or photos
    if not ranks:
        return None
    return {
        "rating": rating,
        "review_count": reviews,
        "photo_count": photos,
        "best_rank": min(ranks),
        "avg_rank": round(sum(ranks) / len(ranks), 2),
        "appearances": len(ranks),
        "total_cells": scan.total_cells,
    }


def latest_profile_facts(db: Session, location_id: int) -> dict[str, dict]:
    """Per place_id: is_claimed / domain / price_level from the most recent scans."""
    scans = (db.query(LocalRankScan)
             .filter(LocalRankScan.location_id == location_id,
                     LocalRankScan.status == "Completed")
             .order_by(LocalRankScan.created_at.desc()).limit(5).all())
    facts: dict[str, dict] = {}
    for scan in scans:
        for row in _iter_cell_results(scan):
            pid = row.get("place_id")
            if not pid or pid in facts:
                continue
            facts[pid] = {"is_claimed": row.get("is_claimed"),
                          "domain": row.get("domain"),
                          "price_level": row.get("price_level")}
    return facts


def competitor_heatmap(db: Session, location_id: int, competitor: TrackedCompetitor) -> dict | None:
    """The competitor's rank per grid cell from the latest completed scan —
    same cell shape the own-rank heatmap renders."""
    scan = (db.query(LocalRankScan)
            .filter(LocalRankScan.location_id == location_id,
                    LocalRankScan.status == "Completed")
            .order_by(LocalRankScan.created_at.desc()).first())
    if not scan:
        return None
    name_l = (competitor.name or "").strip().lower()
    cells = []
    for cell in (scan.cells or []):
        rank = None
        for row in (cell.get("top_results") or []):
            match = (row.get("place_id") == competitor.place_id) if row.get("place_id") else (
                (row.get("name") or "").strip().lower() == name_l)
            if match:
                rank = row.get("rank")
                break
        cells.append({"row": cell.get("row"), "col": cell.get("col"),
                      "lat": cell.get("lat"), "lng": cell.get("lng"),
                      "rank": rank, "top_competitor": None, "top_results": []})
    return {"keyword": scan.keyword, "scanned_at": scan.created_at,
            "your_cells": scan.cells, "competitor_cells": cells}


def _overtake_alerts(db: Session, scan: LocalRankScan, comp: TrackedCompetitor,
                     prev: CompetitorSnapshot | None, agg: dict) -> list[str]:
    """Human-readable crossings: things that flipped against us since the last snapshot."""
    if prev is None:
        return []
    from app.models.location import Location
    loc = db.query(Location).filter(Location.id == scan.location_id).first()
    if not loc:
        return []
    alerts = []
    # Rank: they now outrank us on the grid, and didn't before.
    if (scan.avg_rank is not None and agg.get("avg_rank") is not None and prev.avg_rank is not None):
        if agg["avg_rank"] < scan.avg_rank and not (prev.avg_rank < scan.avg_rank):
            alerts.append(f"{comp.name} now outranks you for '{scan.keyword}' (their avg #{agg['avg_rank']} vs your #{scan.avg_rank}).")
    # Reviews: they crossed your review count.
    own_reviews = loc.total_reviews or 0
    if (agg.get("review_count") or 0) > own_reviews >= (prev.review_count or 0):
        alerts.append(f"{comp.name} passed you in review count ({agg['review_count']} vs your {own_reviews}).")
    # Rating: they crossed your rating.
    own_rating = loc.average_rating or 0
    if (agg.get("rating") or 0) > own_rating >= (prev.rating or 0):
        alerts.append(f"{comp.name}'s rating ({agg['rating']}) is now above yours ({round(own_rating, 1)}).")
    return alerts


def _send_overtake_email(db: Session, scan: LocalRankScan, alerts: list[str]) -> None:
    from app.models.user import User
    from app.models.location import Location
    from app.services.email_service import send_email
    loc = db.query(Location).filter(Location.id == scan.location_id).first()
    owners = (db.query(User.email)
              .filter(User.organization_id == scan.organization_id,
                      User.role == "Owner", User.is_active == True).all())
    to = [e for (e,) in owners]
    items = "".join(f"<li style='margin:6px 0'>{a}</li>" for a in alerts)
    send_email(to, f"Competitor alert — {loc.location_name if loc else 'your location'}",
               f"<p>Your latest rank scan found competitor movement:</p><ul>{items}</ul>"
               f"<p>Open Local Rank &rsaquo; Competition in your dashboard for details.</p>")


def harvest_from_scan(db: Session, scan: LocalRankScan) -> int:
    """Write one snapshot per tracked competitor visible in this completed scan.
    Flushes only; the caller owns the transaction. Returns snapshots written."""
    competitors = (db.query(TrackedCompetitor)
                   .filter(TrackedCompetitor.location_id == scan.location_id).all())
    written = 0
    alerts: list[str] = []
    for comp in competitors:
        agg = _aggregate(scan, comp.place_id, comp.name)
        if not agg:
            continue
        prev = (db.query(CompetitorSnapshot)
                .filter(CompetitorSnapshot.competitor_id == comp.id)
                .order_by(CompetitorSnapshot.captured_at.desc()).first())
        alerts.extend(_overtake_alerts(db, scan, comp, prev, agg))
        db.add(CompetitorSnapshot(competitor_id=comp.id, scan_id=scan.id,
                                  keyword=scan.keyword, **agg))
        written += 1
    if written:
        db.flush()
    if alerts:
        try:
            _send_overtake_email(db, scan, alerts)
        except Exception:
            logger.exception("Overtake alert email failed for scan %s", scan.id)
    return written


def market_scatter(db: Session, location_id: int, own_place_id: str | None, own_name: str | None) -> list[dict]:
    """Every business in the latest scan with its avg rank, reviews, photos and rating —
    feeds the 'what correlates with ranking' scatter charts."""
    scan = (db.query(LocalRankScan)
            .filter(LocalRankScan.location_id == location_id,
                    LocalRankScan.status == "Completed")
            .order_by(LocalRankScan.created_at.desc()).first())
    if not scan:
        return []
    own_name_l = (own_name or "").strip().lower()
    agg: dict[str, dict] = {}
    for row in _iter_cell_results(scan):
        key = row.get("place_id") or (row.get("name") or "").strip().lower()
        if not key or row.get("rank") is None:
            continue
        e = agg.setdefault(key, {"name": row.get("name"), "ranks": [], "reviews": None,
                                 "photos": None, "rating": None, "is_you": False})
        e["ranks"].append(row["rank"])
        e["reviews"] = max(e["reviews"] or 0, row.get("reviews") or 0) or e["reviews"]
        e["photos"] = row.get("total_photos") or e["photos"]
        e["rating"] = row.get("rating") or e["rating"]
        row_name_l = (row.get("name") or "").strip().lower()
        if (own_place_id and row.get("place_id") == own_place_id) or (
                own_name_l and row_name_l and (own_name_l in row_name_l or row_name_l in own_name_l)):
            e["is_you"] = True
    out = [{"name": e["name"], "avg_rank": round(sum(e["ranks"]) / len(e["ranks"]), 1),
            "reviews": e["reviews"], "photos": e["photos"], "rating": e["rating"],
            "is_you": e["is_you"]} for e in agg.values() if e["ranks"]]
    out.sort(key=lambda e: e["avg_rank"])
    return out[:20]


def keyword_winners(db: Session, location_id: int) -> list[dict]:
    """Per scanned keyword: who most often holds #1 in the latest scan, and our rank."""
    from collections import Counter
    # Two-step so we only load the heavy cells JSONB for the one scan per keyword we use.
    id_rows = (db.query(LocalRankScan.id, LocalRankScan.keyword)
               .filter(LocalRankScan.location_id == location_id,
                       LocalRankScan.status == "Completed")
               .order_by(LocalRankScan.created_at.desc()).limit(20).all())
    latest_ids: dict[str, int] = {}
    for sid, kw in id_rows:
        latest_ids.setdefault(kw, sid)  # first seen = newest (desc order)
    scans = (db.query(LocalRankScan)
             .filter(LocalRankScan.id.in_(latest_ids.values())).all()) if latest_ids else []
    latest_per_kw = {s.keyword: s for s in scans}
    out = []
    for kw, scan in latest_per_kw.items():
        leaders = Counter()
        for row in _iter_cell_results(scan):
            if row.get("rank") == 1 and row.get("name"):
                leaders[row["name"]] += 1
        leader = leaders.most_common(1)[0][0] if leaders else None
        out.append({"keyword": kw, "leader": leader, "your_avg_rank": scan.avg_rank,
                    "your_solv": scan.solv, "scanned_at": scan.created_at})
    return out


def suggestions(db: Session, location_id: int, own_place_id: str | None,
                own_name: str | None = None, limit: int = 12) -> list[dict]:
    """Businesses seen most often across this location's recent completed scans."""
    own_name_l = (own_name or "").strip().lower()
    scans = (db.query(LocalRankScan)
             .filter(LocalRankScan.location_id == location_id,
                     LocalRankScan.status == "Completed")
             .order_by(LocalRankScan.created_at.desc()).limit(10).all())
    tracked = {pid for (pid,) in db.query(TrackedCompetitor.place_id)
               .filter(TrackedCompetitor.location_id == location_id).all()}
    seen: dict[str, dict] = {}
    for scan in scans:
        for row in _iter_cell_results(scan):
            pid = row.get("place_id")
            if not pid or pid == own_place_id or pid in tracked:
                continue
            # Safety net when the location has no placeId metadata: match by name.
            row_name = (row.get("name") or "").strip().lower()
            if own_name_l and (own_name_l in row_name or row_name in own_name_l):
                continue
            entry = seen.setdefault(pid, {
                "place_id": pid, "name": row.get("name"), "category": row.get("category"),
                "address": row.get("address"), "rating": None, "reviews": None,
                "appearances": 0, "best_rank": None, "lat": None, "lng": None,
            })
            entry["appearances"] += 1
            entry["lat"] = row.get("lat") if row.get("lat") is not None else entry["lat"]
            entry["lng"] = row.get("lng") if row.get("lng") is not None else entry["lng"]
            entry["rating"] = row.get("rating") or entry["rating"]
            entry["reviews"] = max(entry["reviews"] or 0, row.get("reviews") or 0) or entry["reviews"]
            if row.get("rank") is not None:
                entry["best_rank"] = min(entry["best_rank"] or 999, row["rank"])
    ranked = sorted(seen.values(), key=lambda e: (-e["appearances"], e["best_rank"] or 999))
    return ranked[:limit]
