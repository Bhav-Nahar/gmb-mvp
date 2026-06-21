"""LLM generation of Google-safe GBP business descriptions.

Mirrors ai_reply_service.py: build a structured prompt, call the LLM via the
factory, parse JSON defensively. Differences from the plan, by decision:
  * ONE description, not three variants (regen controls cover tone shifts).
  * The returned JSON is trimmed — NO confidence_score (LLM self-grading is
    noise) and NO policy_flags (those are computed deterministically in
    description_validation, never trusted from the model).
  * The model returns category_mentioned / locality_used so the gate can
    fuzzy-match them against GBP data without a second LLM call.

This service does ONE LLM round. The endpoint orchestrates credit-charging and
the single policy-safe rewrite, so total LLM calls per request are bounded at 2.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING
from xml.sax.saxutils import escape as xml_escape

if TYPE_CHECKING:
    from app.models.location import Location

logger = logging.getLogger(__name__)

MAX_DESC_TOKENS = 700  # ~740-char description + notes/terms JSON wrapper
_TIMEOUT = 20          # per-attempt; tighter than the reply route — this route may also rewrite
_ATTEMPTS = 2          # one retry; the endpoint adds at most one rewrite on top

# §21 industry tone guidance, injected into the system prompt by category.
INDUSTRY_TONE = {
    "clinic": "Conservative, trust-led. No cure or guarantee claims, no exaggerated medical claims. Use care, consultation, support and treatment-guidance language.",
    "jewellery": "Premium, transparent and design-led. Gifting, wedding and daily-wear context.",
    "restaurant": "Cuisine, ambience, dine-in/takeaway/delivery and locality, with a family and friends context.",
    "salon": "Services, hygiene, stylist expertise, location and appointment-friendly language.",
    "coaching": "Courses, student outcomes phrased carefully, faculty and support, and locality.",
    "retail": "Products, shopping experience, store location and customer convenience.",
    "agency": "Service expertise and local business support. No fake ranking guarantees.",
}

# §11 regeneration controls -> a concrete instruction appended AFTER the prior text.
NUDGE_INSTRUCTIONS = {
    "premium": "Make it more premium and sophisticated, but avoid luxury exaggeration unless the brand clearly supports it.",
    "local": "Add locality and service-area context naturally. Do not repeat the city name.",
    "shorter": "Make it shorter — target 350 to 500 characters — while preserving the category, services and location.",
    "warmer": "Make it warmer and more human, without any promotional copy.",
    "clinic_safe": "Make it clinic-safe: no cure or guarantee claims. Use care, consultation, support and treatment-guidance language.",
    "seo": "Tighten the local SEO: include the primary category and top services naturally, with no stuffing.",
}


def _category_tone_key(primary_category: str | None) -> str | None:
    cat = (primary_category or "").lower()
    table = [
        (("jewel",), "jewellery"),
        (("dental", "dentist", "clinic", "doctor", "hospital", "medical", "physio"), "clinic"),
        (("restaurant", "cafe", "food", "dining", "bakery", "kitchen"), "restaurant"),
        (("salon", "spa", "beauty", "barber"), "salon"),
        (("coaching", "school", "tuition", "academy", "institute", "education"), "coaching"),
        (("retail", "store", "shop", "boutique", "market"), "retail"),
        (("agency", "marketing", "consult", "studio"), "agency"),
    ]
    for needles, key in table:
        # Short needles (spa, food, shop) need whole-word match so "spa" doesn't
        # trip on "spaceship"; longer ones match as a prefix (jewel -> jewellery).
        for n in needles:
            pat = rf"\b{re.escape(n)}\b" if len(n) <= 4 else rf"\b{re.escape(n)}"
            if re.search(pat, cat):
                return key
    return None


def _sanitize(value, max_len=300) -> str:
    if not value:
        return "Not specified"
    return xml_escape(" ".join(str(value).split())[:max_len])


def _clean_model_json(raw: str) -> str:
    # ponytail: mirrors ai_reply_service._clean_model_json — strips <think> blocks
    # and ```fences```, then isolates the outermost JSON object. Kept local to
    # decouple the two services; keep in sync if model quirks change.
    text = raw or ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


def _as_str_list(val) -> list[str]:
    # Model output is untrusted: a string or list-of-objects here would otherwise
    # 500 the response (List[str] schema) AFTER the credit was charged.
    if isinstance(val, list):
        return [str(x) for x in val if x is not None]
    return [str(val)] if val else []


def _truncate_to_sentence(text: str, limit: int = 740) -> str:
    """Hard-cap length at a sentence boundary. LLMs (esp. Gemini) ignore the upper
    char bound and run 900-1000+, so we enforce 'never exceed 740' deterministically."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    window = text[:limit]
    end = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if end == -1:
        end = window.rfind(".")
    if end >= 350:
        return window[:end + 1].strip()
    sp = window.rfind(" ")  # no sentence boundary — fall back to the last full word
    return (window[:sp] if sp > 350 else window).strip()


def _parse_description(raw: str) -> dict:
    """Parse the model JSON. On any failure, treat the whole text as the description."""
    try:
        data = json.loads(_clean_model_json(raw))
        desc = str(data.get("recommended_description") or "").strip()
        if not desc:
            raise ValueError("no recommended_description")
        return {
            "description": desc,
            "category_mentioned": str(data.get("category_mentioned") or "").strip(),
            "locality_used": str(data.get("locality_used") or "").strip(),
            "seo_terms": _as_str_list(data.get("seo_terms_included")),
            "aeo_questions": _as_str_list(data.get("aeo_questions_answered")),
            "improvement_notes": _as_str_list(data.get("improvement_notes")),
        }
    except (json.JSONDecodeError, ValueError, AttributeError):
        text = _clean_model_json(raw).strip() or (raw or "").strip()
        return {"description": text, "category_mentioned": "", "locality_used": "",
                "seo_terms": [], "aeo_questions": [], "improvement_notes": []}


def _system_prompt(primary_category: str | None, language: str, tone: str) -> str:
    tone_key = _category_tone_key(primary_category)
    industry_line = f"\nIndustry guidance: {INDUSTRY_TONE[tone_key]}" if tone_key else ""
    return f"""You are Pinzo AI, an expert Google Business Profile optimization assistant.
Generate a Google-safe, natural and human-sounding business description for a Google Business Profile.
Write in {language}. Target tone: {tone}.{industry_line}

Rules:
1. LENGTH IS A HARD REQUIREMENT: the description must be 700-740 characters — fill the available space. Never exceed 740. If you are short of 700, keep elaborating naturally (see below) until you reach it.
2. No URLs, HTML, email addresses, phone numbers, prices, discounts, limited-time offers or sales language.
3. Do not keyword-stuff. Use the category, services and locality naturally.
4. No fake claims like No.1, best, top-rated, guaranteed or leading unless proof is provided.
5. Mention the business category naturally.
6. Mention the city/locality naturally, once or twice at most.
7. Include only the 3-5 most important services or products — do NOT list everything provided.
8. Include what makes the business unique, without exaggerating.
9. Write in a natural, trustworthy, human tone.
10. Avoid robotic phrases: one-stop solution, unparalleled, cutting-edge, world-class, best-in-class, we pride ourselves.
11. It should read like a Google Business Profile description, not an advertisement.
12. If information is missing, do not invent it — write a safe description from the available facts.

To reach the required length WITHOUT inventing facts, elaborate naturally on what is already true: the
specific services or products, who the business serves, the locality or service area, the approach and
care taken, reliability and experience, and the everyday needs or occasions it addresses. Never fabricate
awards, statistics, named clients, prices or guarantees — depth comes from describing the real offering fully.

Put the business type, locality and strongest service clarity in the first 250 characters.

Return ONLY a JSON object, no markdown, with exactly these keys:
{{"recommended_description": "the final description as one clean paragraph",
 "category_mentioned": "the category exactly as you referred to it in the text",
 "locality_used": "the city/locality you used, or empty string if none",
 "seo_terms_included": ["term", "..."],
 "aeo_questions_answered": ["a who/what/where/why question the text answers", "..."],
 "improvement_notes": ["what you focused on or improved", "..."]}}"""


def _user_message(location: Location, *, services, usp, audience, mode,
                  nudge, existing_description, policy_issues, current_chars) -> str:
    facts = (
        f"Business Name: {_sanitize(location.location_name)}\n"
        f"Primary Category: {_sanitize(location.primary_category)}\n"
        f"Secondary Categories: {_sanitize(_secondary_categories(location))}\n"
        f"Address / Service Area: {_sanitize(location.address)}\n"
        f"Services / Products: {_sanitize(', '.join(services) if services else None)}\n"
        f"What makes them special: {_sanitize(usp)}\n"
        f"Who they serve: {_sanitize(audience)}"
    )

    if mode == "rewrite_policy_safe":
        # One corrective pass: fix real policy issues and/or steer length toward 700-740.
        # Over-length is handled here as a SHORTEN directive, not a generic policy flag.
        directives = []
        real_policy = [f for f in (policy_issues or []) if f != "exceeds_750_chars"]
        if real_policy:
            directives.append("remove ALL flagged issues (" + ", ".join(real_policy) +
                              ") — no links, emails, phone numbers, HTML, prices, discounts/offers or unverified claims")
        if current_chars is not None and current_chars < 700:
            directives.append(f"expand it to 700-740 characters (it is currently {current_chars}, too short) by "
                              "elaborating naturally on the services, who is served, the locality/service area, "
                              "and the business's reliability and approach")
        elif current_chars is not None and current_chars > 750:
            directives.append(f"shorten it to 700-740 characters (it is currently {current_chars}, over the limit) "
                              "by trimming repetition and the least essential details")
        directive = "; and ".join(directives) or "improve clarity while keeping it natural and policy-safe"
        return (f"{facts}\n\nPrevious description:\n{_sanitize(existing_description, 1000)}\n\n"
                f"Rewrite it to {directive}. The final text MUST be between 700 and 740 characters and must NEVER "
                "exceed 740. Keep it natural and accurate, and do NOT invent specific facts (awards, numbers, "
                "named clients, prices or guarantees).")

    if mode == "improve_existing":
        instruction = NUDGE_INSTRUCTIONS.get(nudge,
            "Improve clarity, trust and local relevance while keeping it natural and policy-safe.")
        return (f"{facts}\n\nYou previously wrote this description:\n\n"
                f"{_sanitize(existing_description, 1000)}\n\n"
                f"Rewrite this exact description. {instruction} "
                "Preserve all services, category and location, aim for 700-740 characters (elaborate "
                "naturally where it is thin), and do not invent new facts.")

    # generate_new
    return f"{facts}\n\nWrite the business description now, following all the rules above."


def _secondary_categories(location: Location) -> str | None:
    cats = location.additional_categories or []
    names = [c.get("displayName") for c in cats if isinstance(c, dict) and c.get("displayName")]
    return ", ".join(names) if names else None


async def generate_description(
    location: Location,
    *,
    tone: str = "professional",
    language: str = "english",
    usp: str | None = None,
    services: list[str] | None = None,
    audience: str | None = None,
    mode: str = "generate_new",          # generate_new | improve_existing | rewrite_policy_safe
    nudge: str | None = None,            # regen control key (see NUDGE_INSTRUCTIONS)
    existing_description: str | None = None,
    policy_issues: list[str] | None = None,
    current_chars: int | None = None,    # length of the draft being rewritten, to steer expand/shorten
) -> dict:
    """One LLM round → a single description plus structured metadata.

    Returns {description, char_count, category_mentioned, locality_used,
    seo_terms, aeo_questions, improvement_notes}. Policy flags are NOT here —
    the caller computes them with description_validation.
    """
    system_prompt = _system_prompt(location.primary_category, language, tone)
    # Cap services so the model doesn't cram 10+ offerings into an over-length, stuffed
    # paragraph. 6 leaves room for the model to pick the 3-5 most important (rule 7).
    services = (services or [])[:6]
    user_message = _user_message(
        location, services=services, usp=usp, audience=audience, mode=mode,
        nudge=nudge, existing_description=existing_description, policy_issues=policy_issues,
        current_chars=current_chars,
    )
    # generate_new gets a little more spark; rewrites follow instructions tightly.
    temperature = 0.6 if mode == "generate_new" else 0.4

    from app.llm.factory import get_llm_provider  # lazy: keeps module import stdlib-only
    llm = get_llm_provider()
    generated = None
    for attempt in range(_ATTEMPTS):
        try:
            generated = await asyncio.wait_for(
                llm.complete(system_prompt, user_message, max_tokens=MAX_DESC_TOKENS, temperature=temperature),
                timeout=_TIMEOUT,
            )
            break
        except Exception:
            if attempt == _ATTEMPTS - 1:
                raise
            await asyncio.sleep(2 ** attempt)

    parsed = _parse_description(generated)
    parsed["description"] = _truncate_to_sentence(parsed["description"])
    parsed["char_count"] = len(parsed["description"])
    return parsed


if __name__ == "__main__":
    # ponytail: no live LLM — check the parser + mappers, the only logic that
    # breaks silently. The generation itself is exercised end-to-end via the endpoint.
    ok = _parse_description('{"recommended_description":"A clean jewellery store description.",'
                            '"category_mentioned":"jewellery store","locality_used":"Borivali",'
                            '"seo_terms_included":["diamond rings"],"improvement_notes":["added locality"]}')
    assert ok["description"].startswith("A clean") and ok["category_mentioned"] == "jewellery store", ok
    assert ok["locality_used"] == "Borivali" and ok["seo_terms"] == ["diamond rings"], ok

    fenced = _parse_description('```json\n{"recommended_description":"Fenced output works."}\n```')
    assert fenced["description"] == "Fenced output works.", fenced

    garbage = _parse_description("the model forgot to return json at all")
    assert garbage["description"] == "the model forgot to return json at all", garbage
    assert garbage["improvement_notes"] == [], garbage

    assert _category_tone_key("Jewelry store") == "jewellery"
    assert _category_tone_key("Dental clinic") == "clinic"
    assert _category_tone_key("Spaceship factory") is None
    assert "shorter" in NUDGE_INSTRUCTIONS

    # Truncation must hard-cap at <=740 and end on a sentence when possible.
    assert _truncate_to_sentence("Short text.") == "Short text."
    long_prose = "This is a full sentence about the business. " * 40  # ~1760 chars
    t = _truncate_to_sentence(long_prose)
    assert len(t) <= 740 and t.endswith("."), (len(t), t[-30:])
    assert len(_truncate_to_sentence("word " * 400)) <= 740  # no sentence boundary case

    print("description_generator_service self-check passed")
