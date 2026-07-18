"""AEO (AI-search visibility) scanning.

Provider-dispatched, mirroring the storage/provider seam: `AEO_PROVIDER="mock"`
returns realistic sample data with zero external calls (sandbox-first — explore
the whole UI before spending), `AEO_PROVIDER="dataforseo"` (Phase 2) maps the
DataForSEO AI Optimization + AI Mode endpoints into the same contract.

Contract returned by every provider (stored on AEOScan.result):
    {
      "ai_visibility_score": int, "score_delta": int, "queries_tracked": int,
      "surfaces": [{"key","label","present_pct","mentions"}],
      "queries":  [{"query", "surfaces":{key:{"present","rank"}},
                    "competitors":[...], "sources":[...]}],
      "share_of_voice": [{"name","pct","self"}],   # "full" (Pro) tier only
      "recommendations": [str],
    }
"""
import hashlib
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core import plan_config
from app.models.aeo_scan import AEOScan


# key -> label, ordered as shown in the UI. "google" tier is a subset of "full".
_SURFACES = {
    "full": [
        ("chatgpt", "ChatGPT"),
        ("google_ai_overview", "Google AI Overview"),
        ("gemini", "Gemini"),
        ("google_ai_mode", "Google AI Mode"),
        ("perplexity", "Perplexity"),
    ],
    "google": [
        ("google_ai_overview", "Google AI Overview"),
        ("google_ai_mode", "Google AI Mode"),
    ],
}

# All city-anchored — "near me" / "open now" give the AI no location context, so they
# never surface a specific local business (they scored 0/5 in testing) and only waste calls.
_QUERY_TEMPLATES = [
    "best {cat} in {city}",
    "top rated {cat} in {city}",
    "affordable {cat} in {city}",
    "{cat} with good reviews in {city}",
    "recommended {cat} in {city}",
    "trusted {cat} in {city}",
    "popular {cat} in {city}",
    "well reviewed {cat} in {city}",
    "reliable {cat} in {city}",
    "top {cat} in {city}",
]
_COMPETITOR_POOL = ["Smile Studio", "Dr. Mehta Dental", "CityCare Clinic",
                    "PrimeLocal Co.", "Metro Services", "Apex Care"]
_SOURCE_POOL = ["your GBP", "justdial.com", "practo.com", "sulekha.com", "your website"]


# --------------------------------------------------------------------------- #
# Monthly quota — one manual scan per location per calendar month (both plans) #
# --------------------------------------------------------------------------- #
def _month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def next_reset(now: datetime | None = None) -> datetime:
    """First instant of next month — when the location's sync quota refills."""
    m = _month_start(now)
    return m.replace(year=m.year + 1, month=1) if m.month == 12 else m.replace(month=m.month + 1)


def used_this_month(db: Session, location_id: int) -> bool:
    """Has this location already used its included sync this calendar month?
    Failed scans don't count (the quota is refunded), matching the credit-refund
    behaviour of the geo-grid scans."""
    used = (
        db.query(AEOScan)
        .filter(
            AEOScan.location_id == location_id,
            AEOScan.created_at >= _month_start(),
            AEOScan.status != "Failed",
        )
        .count()
    )
    return used >= plan_config.AEO_SYNCS_PER_MONTH


# --------------------------------------------------------------------------- #
# Mock provider (deterministic — same location+month => same result)          #
# --------------------------------------------------------------------------- #
def _seed(*parts) -> int:
    return int(hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest(), 16)


def _pretty_category(raw: str | None) -> str:
    """Turn a raw Google category (e.g. 'categories/gcid:jewelry_store' or
    'jewelry_store') into readable text ('jewelry store') for natural-reading queries."""
    if not raw:
        return "business"
    s = str(raw).split(":")[-1].replace("_", " ").strip()
    return s or "business"


def _loc_bits(location) -> tuple[str, str]:
    city = getattr(location, "city", None) or "your area"
    cat = _pretty_category(getattr(location, "primary_category", None) or getattr(location, "category", None))
    return cat, str(city)


def auto_queries(location) -> list[str]:
    """The system-generated queries for a location — category + city dropped into
    templates. Capped at AEO_QUERIES_PER_SCAN."""
    cat, city = _loc_bits(location)
    out = [t.format(cat=cat, city=city) for t in _QUERY_TEMPLATES]
    return out[: settings.AEO_QUERIES_PER_SCAN]


def clean_custom_queries(raw: list[str], max_n: int) -> list[str]:
    """Validate + normalise an Owner/Admin's custom query list: trim, drop blanks,
    dedupe, enforce 3–120 chars each and at most `max_n` total. Raises ValueError
    (mapped to HTTP 400 by the endpoint) so the cap can never be exceeded."""
    cleaned: list[str] = []
    for q in raw or []:
        q = (q or "").strip()
        if not q:
            continue
        if not (3 <= len(q) <= 120):
            raise ValueError("Each query must be 3–120 characters.")
        if q not in cleaned:
            cleaned.append(q)
    if len(cleaned) > max_n:
        raise ValueError(f"At most {max_n} custom queries per location.")
    return cleaned


def build_queries(location) -> list[str]:
    """The effective query set a scan runs: the Owner/Admin's custom queries first,
    then the auto-generated ones (unless auto is switched off for this location),
    de-duplicated and capped at AEO_MAX_QUERIES."""
    custom = [q.strip() for q in (getattr(location, "aeo_queries", None) or []) if q and q.strip()]
    autos = auto_queries(location) if getattr(location, "aeo_auto_enabled", True) else []
    merged = list(dict.fromkeys(custom + autos))
    return merged[: settings.AEO_MAX_QUERIES]


def _mock_result(location, tier: str, queries: list[str]) -> dict:
    _, city = _loc_bits(location)
    surfaces = _SURFACES.get(tier, _SURFACES["google"])
    keys = [k for k, _ in surfaces]
    n_queries = len(queries)

    query_rows, present_counts = [], {k: 0 for k in keys}
    for text in queries:
        surf = {}
        for k in keys:
            s = _seed(location.id, text, k)
            present = (s % 100) < 55  # ~55% base presence
            surf[k] = {"present": present, "rank": (s % 4) + 1 if present else None}
            if present:
                present_counts[k] += 1
        comps = [_COMPETITOR_POOL[_seed(text, "c", j) % len(_COMPETITOR_POOL)] for j in range(2)]
        srcs = [_SOURCE_POOL[_seed(text, "s", j) % len(_SOURCE_POOL)] for j in range(2)]
        any_present = any(v["present"] for v in surf.values())
        snippet = (f"AI answers for “{text}” name several options in {city}; "
                   + ("your business is among them." if any_present else "your business is not mentioned.")) if n_queries else ""
        query_rows.append({
            "query": text,
            "surfaces": surf,
            "competitors": list(dict.fromkeys(comps)),
            "sources": list(dict.fromkeys(srcs)),
            "snippet": snippet,
        })

    surf_out = [
        {"key": k, "label": label,
         "present_pct": round(100 * present_counts[k] / n_queries) if n_queries else 0,
         "mentions": present_counts[k]}
        for k, label in surfaces
    ]
    score = round(sum(s["present_pct"] for s in surf_out) / len(surf_out)) if surf_out else 0
    delta = (_seed(location.id, "delta", _month_start().month) % 14) - 3  # -3..+10, positive bias

    result = {
        "ai_visibility_score": score,
        "score_delta": delta,
        "queries_tracked": n_queries,
        "surfaces": surf_out,
        "queries": query_rows,
        "recommendations": _recommendations(surf_out, query_rows, _loc_bits(location)[0]),
    }
    if tier == "full":
        result["share_of_voice"] = _share_of_voice(location, score)
    return result


def _recommendations(surfaces: list[dict], queries: list[dict], cat: str) -> list[dict]:
    """Data-driven actions as {title, detail}, from the actual scan — weakest surface,
    the queries you're absent for, and a reviews nudge."""
    recs: list[dict] = []
    if surfaces:
        weakest = min(surfaces, key=lambda s: s["present_pct"])
        if weakest["present_pct"] < 60:
            recs.append({
                "title": f"You're weak on {weakest['label']} ({weakest['present_pct']}%).",
                "detail": f"Publish a services or FAQ page on your website — {weakest['label']} leans on "
                          f"structured on-site content it can cite.",
            })
    absent = [q["query"] for q in queries if not any(v.get("present") for v in q["surfaces"].values())]
    if absent:
        shown = ", ".join(f'“{a}”' for a in absent[:2])
        more = f" and {len(absent) - 2} more" if len(absent) > 2 else ""
        recs.append({
            "title": f"Invisible for {len(absent)} of {len(queries)} queries.",
            "detail": f"No AI named you for {shown}{more}. Add these {cat} services to your GBP and "
                      f"gather reviews that mention them.",
        })
    recs.append({
        "title": "Get more keyword-rich Google reviews.",
        "detail": f"AI answers cite review text — reviews that name your specific {cat} services lift "
                  f"how often you’re included.",
    })
    return recs[:3]


def _share_of_voice(location, score: int) -> list[dict]:
    """You + two competitors, pcts summing to 100, seeded off the score."""
    you = max(15, min(70, score - 5))
    a = (_seed(location.id, "sov") % (100 - you - 10)) + 5
    b = 100 - you - a
    rows = [
        {"name": "You", "pct": you, "self": True},
        {"name": _COMPETITOR_POOL[_seed(location.id, "sov1") % len(_COMPETITOR_POOL)], "pct": a, "self": False},
        {"name": _COMPETITOR_POOL[_seed(location.id, "sov2") % len(_COMPETITOR_POOL)], "pct": b, "self": False},
    ]
    return sorted(rows, key=lambda r: r["pct"], reverse=True)


# --------------------------------------------------------------------------- #
def run_scan(db: Session, scan: AEOScan, location) -> AEOScan:
    """Fill a Pending scan with provider results. Never raises — on provider
    failure the scan is marked Failed (which refunds the monthly quota)."""
    try:
        queries = build_queries(location)   # custom (Owner/Admin) + auto (category+city)
        if settings.AEO_PROVIDER == "mock":
            data = _mock_result(location, scan.tier, queries)
        elif settings.AEO_PROVIDER == "dataforseo":
            import asyncio
            from app.services import aeo_dataforseo
            data = asyncio.run(aeo_dataforseo.scan(location, scan.tier, queries))
        else:
            raise ValueError(f"Unknown AEO_PROVIDER: {settings.AEO_PROVIDER!r}")
        scan.result = data
        scan.ai_visibility_score = data["ai_visibility_score"]
        scan.score_delta = data["score_delta"]
        scan.queries_tracked = data["queries_tracked"]
        scan.status = "Completed"
        scan.error = None
    except Exception as e:  # noqa: BLE001 — any provider failure => Failed, quota refunded
        scan.status = "Failed"
        scan.error = str(e)[:500]
    db.commit()
    db.refresh(scan)
    return scan
