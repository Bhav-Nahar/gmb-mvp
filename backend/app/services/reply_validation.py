"""Deterministic, no-LLM validation for generated review replies.

Safety flags (risk, manual-review) are computed HERE, never trusted from the model.
This is the brand-safety boundary.
"""
import re

# SEO superlatives that must never appear unless a business opts in.
BANNED_PHRASES = [
    "best", "no.1", "no. 1", "number one", "top-rated", "top rated",
    "leading", "world-class", "world class", "guaranteed", "most trusted",
]

# Substrings that force a human to approve before posting, whatever the rating.
MANUAL_REVIEW_KEYWORDS = [
    "fraud", "scam", "lawyer", "legal", "lawsuit", "sue", "court", "police",
    "refund", "consumer complaint", "consumer forum", "abuse", "harassment",
    "harass", "medical", "health", "doctor", "hospital", "infection", "allergic",
]

MIN_WORDS = 20
MAX_WORDS = 60


def _words(text: str) -> int:
    return len(text.split())


def manual_review_required(rating, comment: str) -> bool:
    if rating is not None and rating <= 1:
        return True
    low = (comment or "").lower()
    return any(kw in low for kw in MANUAL_REVIEW_KEYWORDS)


def validate(reply_text: str, sentiment: str, rating, comment: str,
             min_words: int = MIN_WORDS, max_words: int = MAX_WORDS) -> dict:
    """Return {risk_level, manual_review_required, violations}. Pure, deterministic.

    Word bounds are per-variant: the 'short' variant is 15-25 words by design, so the
    caller passes a lower floor for it than for the 35-55 word recommended variant."""
    violations = []
    text = (reply_text or "").strip()
    wc = _words(text)
    if wc < min_words or wc > max_words:
        violations.append(f"length {wc} words outside {min_words}-{max_words}")

    low = text.lower()
    for phrase in BANNED_PHRASES:
        # word-boundary match so "best" doesn't trip on "bestseller"
        if re.search(rf"\b{re.escape(phrase)}\b", low):
            violations.append(f"banned phrase: {phrase}")

    flagged = manual_review_required(rating, comment)
    if flagged:
        risk = "high"
    elif violations:
        risk = "medium"
    else:
        risk = "low"

    return {
        "risk_level": risk,
        "manual_review_required": flagged,
        "violations": violations,
    }


if __name__ == "__main__":
    # ponytail: smallest check that fails if the safety logic breaks.
    ok = validate("We loved having you visit our showroom and we truly hope to welcome "
                  "you again very soon for another wonderful jewellery experience with our whole "
                  "team, who genuinely enjoyed helping you find something special today.",
                  "positive", 5, "Great staff")
    assert ok["risk_level"] == "low" and not ok["violations"], ok

    banned = validate("We are the best jewellery store you will ever find anywhere nearby today.",
                      "positive", 5, "nice")
    assert any("banned" in v for v in banned["violations"]), banned
    assert banned["risk_level"] == "medium", banned

    short = validate("Thanks!", "positive", 5, "good")
    assert any("length" in v for v in short["violations"]), short

    legal = validate("We are sorry to hear about your experience and want to make this right for you somehow.",
                     "negative", 1, "I will sue you")
    assert legal["manual_review_required"] and legal["risk_level"] == "high", legal

    print("reply_validation self-check passed")
