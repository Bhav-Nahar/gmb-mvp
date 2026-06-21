"""Deterministic, no-LLM validation + quality scoring for GBP business descriptions.

Policy flags are computed HERE, never trusted from the model — this is the
Google-policy safety boundary (mirrors reply_validation.py). The same module
scores description quality so the health score and the pre-generation
"is it already good?" gate share ONE source of truth: no LLM, no credits.

Two flag tiers:
  * hard_flags  -> Google may reject. Block publish; trigger one auto-rewrite.
  * soft_flags  -> quality/style nits. Surface to the user; never block.
"""
import re
from collections import Counter

HARD_MAX = 750          # Google's hard ceiling
SAFE_MAX = 740          # Pinzo safe ceiling
IDEAL_MIN, IDEAL_MAX = 550, 740  # full length score across 550-740; generation now targets the top
THIN_MIN = 350          # below this = "thin description"

# --- Hard policy patterns (block + rewrite) ---------------------------------
_URL = re.compile(r"(https?://|www\.)\S+", re.I)
# Bare 2-letter TLDs (in, co) are dropped — too word-like ("comfortable.in every",
# "work.co"); real domains are still caught by _URL (www./http) and _EMAIL.
_DOMAIN = re.compile(r"\b[a-z0-9][a-z0-9-]*\.(?:com|net|org|biz|shop|store)\b", re.I)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b", re.I)
_HTML = re.compile(r"<[^>]+>")
# Phone-ish runs of digits with separators.
_PHONE_RUN = re.compile(r"\+?\d[\d -]{8,}\d")


def _has_phone(text: str) -> bool:
    # A real number has 10-13 digits and a 5+ consecutive run — that separates
    # "98765 43210" from prose like "1990 - 2020 - 2024" (4-digit year groups).
    for m in _PHONE_RUN.finditer(text):
        s = m.group()
        if 10 <= len(re.sub(r"\D", "", s)) <= 13 and re.search(r"\d{5,}", s):
            return True
    return False
_PROMO = re.compile(r"\b(sale|discount|coupon|buy now|limited[- ]?time|flat\s?\d+|\d+\s?%\s?off)\b", re.I)
# Currency AMOUNTS, not the bare word "price" — "transparent pricing/guidance" is legit.
_PRICE = re.compile(r"(₹\s?\d|(?<!\w)\$\s?\d|\brs\.?\s?\d|\bstarting at\b|\d+\s?(?:rupees|inr)\b)", re.I)
_HARD_CLAIM = re.compile(r"\b(no\.?\s?1|#\s?1|number one|top[- ]?rated|guaranteed|best[- ]in[- ]class|world[- ]?class)\b", re.I)

# --- Soft style/quality patterns (warn only) --------------------------------
# Demoted on purpose: "we offer", "free parking", "best suited", "leading provider"
# are legitimate prose, not sales hooks. Word boundaries keep them from over-firing.
_SOFT_CLAIM = re.compile(r"\b(best|leading|free|offers?|most trusted|premier)\b", re.I)
_ROBOTIC = re.compile(r"\b(one[- ]stop (?:shop|solution)|unparalleled|cutting[- ]edge|we pride ourselves|state[- ]of[- ]the[- ]art)\b", re.I)

# Generic category words that shouldn't count as "mentions your category".
_GENERIC_CAT = {"store", "shop", "services", "service", "center", "centre", "and", "the"}
# 5+ letter stopwords excluded from keyword-stuffing detection.
_STOP = {"their", "there", "which", "where", "while", "about", "across", "every",
         "other", "these", "those", "being", "based", "around", "looking"}


def _hard_flags(text: str) -> list[str]:
    flags = []
    if len(text) > HARD_MAX:
        flags.append("exceeds_750_chars")
    if _URL.search(text) or _DOMAIN.search(text):
        flags.append("contains_link")
    if _EMAIL.search(text):
        flags.append("contains_email")
    if _HTML.search(text):
        flags.append("contains_html")
    if _has_phone(text):
        flags.append("contains_phone")
    if _PROMO.search(text):
        flags.append("promotion_language")
    if _PRICE.search(text):
        flags.append("price_language")
    if _HARD_CLAIM.search(text):
        flags.append("unverified_claim")
    if _stuffed(text):
        flags.append("keyword_stuffing")
    return flags


def _soft_flags(text: str, category_ok: bool) -> list[str]:
    flags = []
    if 0 < len(text) < THIN_MIN:
        flags.append("thin_description")
    if _SOFT_CLAIM.search(text):
        flags.append("soft_superlative")
    if _ROBOTIC.search(text):
        flags.append("robotic_phrase")
    if text and not category_ok:
        flags.append("no_category_mention")
    return flags


def _stuffed(text: str) -> list[str]:
    # ponytail: a 5+ letter non-stopword repeated 4+ times reads as stuffing.
    # Threshold is 4 (not Google's stricter "3+") to avoid tripping on a core
    # service word used naturally 2-3 times; lower to 3 if Google flags listings.
    counts = Counter(t for t in re.findall(r"[a-z]{5,}", text.lower()) if t not in _STOP)
    return [w for w, c in counts.items() if c >= 4]


def _mentions_category(text: str, primary_category: str | None) -> bool:
    if not primary_category:
        return False
    low = text.lower()
    # ponytail: 4-char prefix match handles spelling variants (jewelry/jewellery,
    # dentist/dental, restaurant/resto). Upgrade to a synonym map or the LLM's
    # category_mentioned field if false-negatives matter.
    for tok in re.findall(r"[a-z]{4,}", primary_category.lower()):
        if tok in _GENERIC_CAT:
            continue
        if re.search(rf"\b{re.escape(tok[:4])}", low):
            return True
    return False


def _quality_score(text: str, category_ok: bool, hard_flags: list[str]) -> int:
    """0-5 sub-score folded into the health score's Profile Completeness budget."""
    if not text:
        return 0
    n = len(text)
    if n < THIN_MIN or n > HARD_MAX:
        length_pts = 1
    elif IDEAL_MIN <= n <= IDEAL_MAX:
        length_pts = 3
    else:
        length_pts = 2
    cat_pts = 1 if category_ok else 0
    policy_pts = 1 if not hard_flags else 0
    return length_pts + cat_pts + policy_pts  # max 3 + 1 + 1 = 5


def _status(text: str, category_ok: bool, hard_flags: list[str]) -> str:
    if not text:
        return "Missing"
    if len(text) < THIN_MIN:
        return "Thin"
    if hard_flags or not category_ok:
        return "Weak"
    return "Good"  # deterministic ceiling; "Optimized" needs confirmed locality+service


def analyze(text: str | None, primary_category: str | None = None) -> dict:
    """Full deterministic picture: char count, flags, category, 0-5 score, status."""
    text = (text or "").strip()
    category_known = bool(primary_category and primary_category.strip())
    has_category = _mentions_category(text, primary_category)
    # If the location has no category configured, don't penalize the description for
    # "not mentioning it" — that's a missing location field, not a description flaw.
    category_ok = has_category or not category_known
    hard = _hard_flags(text)
    soft = _soft_flags(text, category_ok)
    return {
        "char_count": len(text),
        "hard_flags": hard,
        "soft_flags": soft,
        "has_category": has_category,
        "quality_score": _quality_score(text, category_ok, hard),
        "status": _status(text, category_ok, hard),
        "is_valid": len(hard) == 0,
    }


def validate(text: str | None, primary_category: str | None = None) -> dict:
    """Thin wrapper for the live-edit /validate endpoint."""
    a = analyze(text, primary_category)
    return {"is_valid": a["is_valid"], "hard_flags": a["hard_flags"],
            "soft_flags": a["soft_flags"], "char_count": a["char_count"]}


if __name__ == "__main__":
    # ponytail: smallest check that fails if the policy/scoring logic breaks.
    good = ("Lucira Jewelry is a lab-grown diamond jewellery store in Borivali, Mumbai, "
            "offering certified diamond rings, earrings, pendants, bracelets, solitaires and "
            "everyday jewellery. The store focuses on modern designs, transparent guidance and a "
            "comfortable in-store buying experience for customers looking for jewellery for gifting, "
            "daily wear, weddings and special occasions.")
    a = analyze(good, "Jewelry store")
    assert a["is_valid"] and not a["hard_flags"], a
    assert a["has_category"] and a["status"] in ("Good",), a
    assert a["quality_score"] >= 4, a

    # Soft words must NOT hard-block legitimate prose.
    soft = analyze("We offer free parking and our team is best suited for families seeking "
                   "thoughtful, everyday jewellery designs across the city of Pune nearby.", "Jewelry store")
    assert soft["is_valid"], soft
    assert "soft_superlative" in soft["soft_flags"], soft

    # Real policy violations must hard-block.
    bad = analyze("Visit www.lucira.com or email shop@lucira.com for 20% off! "
                  "Rings starting at ₹999. Call 9876543210. We are the No.1 store. <br>", "Jewelry store")
    for f in ("contains_link", "contains_email", "promotion_language", "price_language",
              "contains_phone", "unverified_claim", "contains_html"):
        assert f in bad["hard_flags"], (f, bad)
    assert not bad["is_valid"]

    assert analyze("Too short.", "Jewelry store")["status"] == "Thin"
    assert analyze("", None)["status"] == "Missing"

    stuffed = analyze("diamond diamond diamond diamond rings for diamond lovers", "Jewelry store")
    assert "keyword_stuffing" in stuffed["hard_flags"], stuffed

    # A clean, well-formed description must NOT be marked Weak just because the
    # location has no primary_category configured (the gap is the location's, not the text's).
    nocat = analyze(good, None)
    assert nocat["status"] == "Good" and "no_category_mention" not in nocat["soft_flags"], nocat

    # Phone false-positive guard: year ranges / counts must not trip "contains_phone",
    # but a real 10-digit number must.
    assert not analyze("Serving the area since 1990 - 2020 - 2024 with great care.", "Jewelry store")["hard_flags"]
    assert "contains_phone" in analyze("Reach us at 98765 43210 anytime.", "Jewelry store")["hard_flags"]
    # Domain false-positive guard: "word.in" prose must not trip "contains_link".
    assert "contains_link" not in analyze("We keep you comfortable.in your own home every day.", "Jewelry store")["hard_flags"]

    print("description_validation self-check passed")
