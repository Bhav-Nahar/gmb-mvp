"""Phase 2 — real AI-visibility data via DataForSEO's AI endpoints.

Maps Google AI Mode / AI Overview and the LLM Responses APIs into the SAME
contract the mock produces, so nothing downstream changes. Parsing is deliberately
schema-tolerant (we walk the whole result blob for text and check for the brand),
because DataForSEO's exact AI response paths can drift — the first live run should
be watched via the logged `money_spent` and any per-surface warnings.

Presence detection is intentionally simple for v1: the business is "present" on a
surface if its name appears anywhere in that surface's answer text. Rank is left
None (AI answers rarely have a clean ordinal); the UI shows a ✓ for a mention.
"""
import logging
import re

import httpx

from app.core.config import settings
from app.services import aeo_service  # reuse _SURFACES, _recommendations, _loc_bits

logger = logging.getLogger(__name__)

_URL_RE = re.compile(r'https?://([^/\s"\'<>)\]]+)')
_WS_RE = re.compile(r"\s+")

_LLM = {
    "chatgpt": ("chat_gpt", "gpt-4.1-mini"),
    "gemini": ("gemini", "gemini-2.5-flash"),
    "perplexity": ("perplexity", "sonar"),
}


def _brand(location) -> str:
    """The core business name to look for in AI answers. GBP titles often carry a
    location suffix ('Rupesh Jewellers in Malad, Mumbai'); we match on the name only
    ('Rupesh Jewellers'), since no answer repeats the full listing title verbatim."""
    name = str(getattr(location, "location_name", "") or "").strip()
    for sep in (" in ", " - ", " | ", ",", " – "):
        if sep in name:
            head = name.split(sep)[0].strip()
            if len(head) >= 3:
                name = head
            break
    return name


def _walk_text(obj) -> str:
    """Collect every string value from a nested dict/list. Robust to schema drift —
    we don't depend on exact field paths, we just need the answer text to search."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return " ".join(_walk_text(v) for v in obj.values())
    if isinstance(obj, list):
        return " ".join(_walk_text(v) for v in obj)
    return ""


def _domains(obj) -> list[str]:
    """Cited domains from a response — walk all URLs, strip to bare host, dedupe."""
    out: list[str] = []
    for host in _URL_RE.findall(_walk_text(obj)):
        d = host.lower().split(":")[0]
        if d.startswith("www."):
            d = d[4:]
        if d and "." in d and d not in out:
            out.append(d)
    return out


def _snippet(obj, limit: int = 220) -> str:
    """A short, human-readable excerpt of the answer — URLs stripped, whitespace
    collapsed. Display-only, so a rough excerpt is fine if the schema shifts."""
    text = _URL_RE.sub("", _walk_text(obj))
    text = _WS_RE.sub(" ", text).strip()
    return (text[:limit].rstrip() + "…") if len(text) > limit else text


def _payload_for(key: str, query: str, loc_code: int):
    """(path, request-body) for a surface. Google surfaces target a numeric
    location_code; the LLM endpoints take no location. Fields per DataForSEO docs."""
    if key == "google_ai_overview":
        return ("/v3/serp/google/organic/live/advanced",
                {"keyword": query, "location_code": loc_code, "language_code": "en",
                 "load_async_ai_overview": True})
    if key == "google_ai_mode":
        return ("/v3/serp/google/ai_mode/live/advanced",
                {"keyword": query, "location_code": loc_code, "language_code": "en"})
    path, model = _LLM[key]
    return (f"/v3/ai_optimization/{path}/llm_responses/live",
            {"user_prompt": query, "model_name": model, "web_search": True})


async def _fetch(client, base: str, key: str, query: str, loc_code: int, brand: str):
    """One surface call. Returns ({present, rank}, cost). Never raises — a failed
    surface is treated as 'absent' and logged, so one bad call can't sink the scan."""
    path, payload = _payload_for(key, query, loc_code)
    try:
        r = await client.post(f"{base}{path}", json=[payload])
        r.raise_for_status()
        body = r.json()
    except Exception as e:  # noqa: BLE001
        logger.warning("AEO %s failed for %r: %s", key, query, e)
        return {"present": False, "rank": None}, 0.0, False

    task = (body.get("tasks") or [{}])[0]
    cost = float(task.get("cost") or body.get("cost") or 0.0)
    if task.get("status_code") not in (20000, 20100):
        logger.warning("AEO %s status %s: %s", key, task.get("status_code"), task.get("status_message"))
        return {"present": False, "rank": None, "sources": [], "snippet": ""}, cost, False
    result = task.get("result")
    text = _walk_text(result)
    present = brand.lower() in text.lower() if brand else False
    return ({"present": present, "rank": None,
             "sources": _domains(result), "snippet": _snippet(result)}, cost, True)


def _location_code(location) -> int:
    # City-level codes would need a lookup table; country-level (India) is fine for v1.
    return settings.AEO_LOCATION_CODE


async def scan(location, tier: str, queries: list[str]) -> dict:
    """Run `queries` against the tier's AI surfaces and return the result contract."""
    login, password = settings.DATAFORSEO_LOGIN, settings.DATAFORSEO_PASSWORD
    if not (login and password):
        raise RuntimeError("DataForSEO credentials are not configured.")
    if "sandbox" in settings.DATAFORSEO_BASE_URL:
        logger.warning("AEO is running against the DataForSEO SANDBOX — results are simulated and nothing is charged. "
                       "Set DATAFORSEO_BASE_URL=https://api.dataforseo.com for real data.")

    base = settings.DATAFORSEO_BASE_URL.rstrip("/")
    brand = _brand(location)
    loc_code = _location_code(location)
    surfaces = aeo_service._SURFACES.get(tier, aeo_service._SURFACES["google"])
    keys = [k for k, _ in surfaces]

    present_counts = {k: 0 for k in keys}
    query_rows: list[dict] = []
    total_cost = 0.0
    calls = ok_calls = 0

    async with httpx.AsyncClient(timeout=120.0, auth=(login, password)) as client:
        for q in queries:
            surf = {}
            q_sources: list[str] = []
            q_snippet = ""
            snippet_from_present = False
            for k in keys:
                res, cost, ok = await _fetch(client, base, k, q, loc_code, brand)
                surf[k] = {"present": res["present"], "rank": res["rank"]}
                total_cost += cost
                calls += 1
                if ok:
                    ok_calls += 1
                if res["present"]:
                    present_counts[k] += 1
                for d in res.get("sources", []):
                    if d not in q_sources:
                        q_sources.append(d)
                # Prefer the excerpt from a surface where the business actually appears.
                snip = res.get("snippet") or ""
                if snip and (not q_snippet or (res["present"] and not snippet_from_present)):
                    q_snippet, snippet_from_present = snip, res["present"]
            query_rows.append({"query": q, "surfaces": surf, "competitors": [],
                               "sources": q_sources[:6], "snippet": q_snippet})

    # If NOTHING succeeded (e.g. every call 403'd on an unfunded account), this isn't a
    # real "score 0" — fail the scan so it's flagged and the monthly quota is refunded.
    if calls and ok_calls == 0:
        raise RuntimeError(
            "Every AI query was rejected by DataForSEO (e.g. 403 Forbidden). This is usually an "
            "account issue — check your DataForSEO balance and API access. Nothing was charged.")

    n = len(queries)
    surf_out = [
        {"key": k, "label": label,
         "present_pct": round(100 * present_counts[k] / n) if n else 0,
         "mentions": present_counts[k]}
        for k, label in surfaces
    ]
    score = round(sum(s["present_pct"] for s in surf_out) / len(surf_out)) if surf_out else 0

    result = {
        "ai_visibility_score": score,
        "score_delta": 0,  # real deltas need a previous scan; wired later
        "queries_tracked": n,
        "surfaces": surf_out,
        "queries": query_rows,
        "recommendations": aeo_service._recommendations(surf_out, query_rows, aeo_service._loc_bits(location)[0]),
        "money_spent": round(total_cost, 4),
    }
    if tier == "full":
        # v1: simple "how often you're mentioned" until the LLM Mentions API (true
        # competitor share-of-voice) is wired.
        result["share_of_voice"] = [
            {"name": "You", "pct": score, "self": True},
            {"name": "Not mentioned", "pct": 100 - score, "self": False},
        ]

    logger.info("AEO scan done: money_spent=$%.4f | %d queries x %d surfaces | score=%d | loc_code=%s",
                total_cost, n, len(keys), score, loc_code)
    return result
