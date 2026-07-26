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

# Categories where naming the reviewer or implying they were a patient/client is a
# privacy problem (and against Google's health-provider guidance), and where "visit
# again!" reads as tone-deaf. ponytail: a keyword regex on the GBP primary category —
# swap for the Google category-id taxonomy if false positives show up.
SENSITIVE_CATEGORY_RE = re.compile(
    r"doctor|physician|dentist|dental|orthodont|clinic|hospital|medical|medicine|surgeon"
    r"|surgery|psychiatr|psycholog|therapist|therapy|counsel|rehab|addiction|deaddiction"
    r"|fertility|ivf|gynec|gynaec|obstetric|pediatric|paediatric|dermatolog|oncolog"
    r"|cardiolog|neurolog|orthoped|orthopaed|physiotherap|chiropract|diagnostic|pathology"
    r"|radiolog|optometr|ophthalmolog|eye care|hearing|audiolog|nursing home|hospice"
    r"|veterinar|\bvet\b|lawyer|attorney|advocate|law firm|legal service",
    re.IGNORECASE,
)

# Phrases a reply in a sensitive category must not contain.
REVISIT_PHRASES = [
    "visit again", "visit us again", "see you again", "see you soon", "come back",
    "come again", "serving you again", "serve you again", "welcome you back",
    "welcome you again", "look forward to your next", "next visit", "again soon",
]
PATIENT_PHRASES = [
    "your visit", "your treatment", "your procedure", "your appointment",
    "your consultation", "your surgery", "your diagnosis", "as our patient",
    "as a patient", "your recovery", "your case",
    # Implies they received care without saying it outright.
    "your care", "your results", "your smile", "your teeth", "your medication",
    "your prescription", "trusting us with your", "your health",
]
# ponytail: "your experience" is deliberately NOT here — it is the standard
# HIPAA-safe phrasing ("glad you had a positive experience"), not a disclosure.

MIN_WORDS = 20
MAX_WORDS = 60


def is_sensitive_category(primary_category: str, location_name: str = "") -> bool:
    """True for health/legal-type businesses that need the privacy guardrails."""
    return bool(SENSITIVE_CATEGORY_RE.search(f"{primary_category or ''} {location_name or ''}"))


def _words(text: str) -> int:
    return len(text.split())


def manual_review_required(rating, comment: str) -> bool:
    if rating is not None and rating <= 1:
        return True
    low = (comment or "").lower()
    return any(kw in low for kw in MANUAL_REVIEW_KEYWORDS)


def validate(reply_text: str, sentiment: str, rating, comment: str,
             min_words: int = MIN_WORDS, max_words: int = MAX_WORDS,
             sensitive: bool = False, reviewer_name: str = "") -> dict:
    """Return {risk_level, manual_review_required, violations}. Pure, deterministic.

    Word bounds are per-variant: the 'short' variant is 15-25 words by design, so the
    caller passes a lower floor for it than for the 35-55 word recommended variant.

    `sensitive` (health/legal categories) adds the privacy checks: no reviewer name, no
    wording that confirms they were a patient/client, no "visit again" invitation."""
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

    name_leak = False
    if sensitive:
        for phrase in REVISIT_PHRASES + PATIENT_PHRASES:
            if phrase in low:
                violations.append(f"sensitive category phrase: {phrase}")
        # Any name part of 3+ chars appearing in the reply identifies the reviewer as a
        # patient/client, which is the thing we are not allowed to confirm.
        for part in (reviewer_name or "").split():
            part = part.strip(".,'\"").lower()
            if len(part) >= 3 and re.search(rf"\b{re.escape(part)}\b", low):
                name_leak = True
                violations.append(f"sensitive category: reviewer name in reply ({part})")

    flagged = manual_review_required(rating, comment) or name_leak
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

    assert is_sensitive_category("Dental clinic") and is_sensitive_category("", "Dr Mehta Dentistry")
    assert not is_sensitive_category("Jewelry store", "Lucira Jewelry")

    safe = validate("Thank you so much for taking the time to share this with us. Our whole team "
                    "appreciates your kind words, and we are always here if there is anything at all "
                    "you need from us.", "positive", 5, "great", sensitive=True, reviewer_name="Sapna Rao")
    assert safe["risk_level"] == "low" and not safe["violations"], safe

    leak = validate("Thank you, Sapna! We are so glad your root canal treatment went well and we "
                    "look forward to serving you again at the clinic very soon indeed.",
                    "positive", 5, "great", sensitive=True, reviewer_name="Sapna Rao")
    assert leak["manual_review_required"] and leak["risk_level"] == "high", leak
    assert any("reviewer name" in v for v in leak["violations"]), leak
    assert any("serving you again" in v for v in leak["violations"]), leak

    # Same reply is fine for a non-sensitive business.
    assert not validate("Thank you, Sapna! We are so glad your visit went well and we look forward "
                        "to serving you again at the store very soon indeed today.",
                        "positive", 5, "great", reviewer_name="Sapna Rao")["violations"]

    print("reply_validation self-check passed")
