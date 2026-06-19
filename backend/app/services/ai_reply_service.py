import asyncio
import json
import logging
import random
import re
from xml.sax.saxutils import escape as xml_escape

from sqlalchemy.orm import Session

from app.models.review import Review
from app.models.location import Location
from app.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)

MAX_REPLY_TOKENS = 600  # three variants in one JSON response

# Rotating templates for rating-only reviews (no text) — skips the LLM entirely.
EMPTY_REVIEW_TEMPLATES = [
    "Thank you for your support. We appreciate you taking the time to leave a rating.",
    "Thank you for the {rating} stars. It means a lot to our team.",
    "We truly appreciate your support and look forward to serving you again.",
]


def empty_review_reply(rating: int) -> str:
    """Rotating canned reply for rating-only reviews. No LLM call, no credit."""
    return random.choice(EMPTY_REVIEW_TEMPLATES).replace("{rating}", str(rating))


def _sanitize_prompt_input(value, max_len=200):
    if not value:
        return "Not specified"
    return " ".join(str(value).split())[:max_len]


def _recent_replies(db: Session, location_id: int, limit: int = 5) -> list[str]:
    # ponytail: a LIMIT 5 query, not a "memory engine". Bump limit if dedup needs more history.
    rows = (
        db.query(Review.reply_text)
        .filter(Review.location_id == location_id, Review.is_replied == True, Review.reply_text.isnot(None))
        .order_by(Review.reply_created_at.desc())
        .limit(limit)
        .all()
    )
    return [r[0] for r in rows if r[0]]


def _clean_model_json(raw: str) -> str:
    """Strip wrappers some models add: <think> reasoning blocks and ```code fences```,
    then isolate the outermost JSON object. Makes us robust to scout/qwen/gpt-oss-style output."""
    text = raw or ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start:end + 1] if start != -1 and end > start else text


def _parse_variants(raw: str, fallback_tone: str) -> dict:
    """Parse the model's JSON. On any failure, treat the whole text as the one reply."""
    try:
        data = json.loads(_clean_model_json(raw))
        recommended = (data.get("recommended") or "").strip()
        if not recommended:
            raise ValueError("no recommended reply")
        return {
            "recommended": recommended,
            "short": (data.get("short") or recommended).strip(),
            "warm_or_professional": (data.get("warm_or_professional") or recommended).strip(),
            "topics": data.get("topics") or [],
        }
    except (json.JSONDecodeError, ValueError, AttributeError):
        text = _clean_model_json(raw).strip() or (raw or "").strip()
        return {"recommended": text, "short": text, "warm_or_professional": text, "topics": []}


async def generate_reply(review: Review, location: Location, db: Session = None) -> dict:
    if review.rating is None:
        logger.warning("review.rating is None for review id=%s; defaulting to 3", getattr(review, "id", "unknown"))
    rating = review.rating if review.rating is not None else 3
    if rating in (4, 5):
        tone = "grateful"
    elif rating == 3:
        tone = "neutral"
    else:
        tone = "empathetic"

    safe_comment = xml_escape((review.comment or "")[:2000])
    review_text_xml = f"<review>{safe_comment}</review>" if safe_comment else "No written review provided."

    location_name = _sanitize_prompt_input(location.location_name)
    primary_category = _sanitize_prompt_input(location.primary_category)
    address = _sanitize_prompt_input(location.address)
    reviewer_name = _sanitize_prompt_input(review.reviewer_name)

    recent = _recent_replies(db, review.location_id) if db is not None else []
    recent_block = (
        "Recent replies we already posted (vary the opening, closing, and structure from these):\n"
        + "\n".join(f"- {xml_escape(_sanitize_prompt_input(r))}" for r in recent)
        if recent else "No recent replies on record."
    )

    system_prompt = """You are an expert Google Business Profile review reply specialist for local businesses.
Write replies to a customer review on behalf of the business owner.

LENGTH (most important — keep replies tight, do not pad):
- "recommended" and "warm_or_professional" must each be 35 to 55 words. Warm but concise — a few crisp sentences, not a long paragraph.
- "short" must be 15 to 25 words — one or two crisp sentences, never under 15.

VOICE & STRUCTURE (write a reply to a person, NOT a summary):
- Speak directly to the reviewer as "you". NEVER refer to them in the third person — never "she", "he", "the customer", or "Sapna's review/description".
- You may greet them by first name ONCE (e.g. "Thank you, Sapna!") ONLY if the reviewer name is clearly a personal name. If it looks like a business, a YouTube channel, a handle, or multiple people (e.g. contains "Vlogs", "Official", "Studio", "&"/"and", or reads like a brand), do NOT use the name at all — just address them as "you".
- This is the heart of the reply: express genuine, warm appreciation. The thanks must feel personal, not "We appreciate your feedback".
- Do NOT summarize or list back what they wrote. If the review names something specific (a product, the service, the staff, the experience), reference EXACTLY ONE of those things and react to it naturally — never zero (don't go fully generic), never the whole list. If the review is vague with nothing specific, a warm general thank-you is fine.
- Never use the word "best" anywhere — not about the business, not about the customer (no "you deserve the best").
- Be grounded and sincere, NOT flowery. Avoid empty flattery and salesy clichés: "the finest", "pampered", "you deserve", "special moments", "found a special place", "drives us". Warmth comes from specifics and a genuine tone, not superlatives.
- Follow this flow: (1) thank them warmly and personally, (2) react to their experience like a real owner would, (3) optionally one natural product or location touch, (4) close by warmly inviting them back.
- Sound like a real owner talking to a happy customer, not a press release or a recap.

LOCAL SEO (at most ONE signal, only if it reads naturally):
- You may include EITHER one product/service the reviewer actually mentioned, OR one location/area reference — never both, and never more than one.
- Use it only if the review itself supports it. If nothing fits naturally, include none. Never force it.
- For negative reviews and rating-only reviews: include NO SEO signal at all.
- Never use these words: "best", "no.1", "top-rated", "leading", "world-class", "guaranteed", "most trusted".

GENERAL:
- Never mention competitor names.
- Never make promises you cannot keep (e.g., "we will fix this immediately").
- Never invent services, staff, policies, or facts not provided in the context.
- Never open with generic filler like "Thank you for your feedback".
- Write in first-person plural (we/our) as the business owner. No hashtags or emojis.

Tone rules based on star rating:
- 5 stars: Warm, enthusiastic, grateful. Make them feel genuinely appreciated, not recapped.
- 4 stars: Positive and appreciative. Acknowledge any minor concern if mentioned.
- 3 stars: Professional, balanced. Acknowledge the experience, show commitment to improvement.
- 2 stars: Empathetic and apologetic. Take responsibility without being defensive. Invite direct outreach.
- 1 star: Deeply empathetic, apologetic, calm, and resolution-oriented. Offer to resolve offline.

Return ONLY a JSON object, no markdown, with exactly these keys:
{"recommended": "35-55 words, grounded sincere warmth, names the specific thing they praised, no flowery filler — this is the default reply", "short": "15-25 word reply, same grounded tone", "warm_or_professional": "35-55 words, a noticeably different wording/angle from recommended so the owner has a real choice", "topics": ["topic mentioned in the review", ...]}"""

    user_message = f"""Business Name: {location_name}
Business Type: {primary_category}
Business Address: {address}
Star Rating: {rating} out of 5
Reviewer Name: {reviewer_name}
Customer Review:

{review_text_xml}

{recent_block}

Write the three reply variants for a {rating}-star rating. Speak directly to the reviewer as "you", lead with warm personal appreciation, and do not summarize their review back to them."""

    llm = get_llm_provider()
    generated = None
    for attempt in range(3):
        try:
            generated = await asyncio.wait_for(
                # ponytail: 0.4 (not the 0.7 default) — lower variance = more consistent
                # instruction-following on tone/length. Raise if replies feel samey.
                llm.complete(system_prompt, user_message, max_tokens=MAX_REPLY_TOKENS, temperature=0.4),
                timeout=30,
            )
            break
        except Exception:
            if attempt == 2:
                raise
            await asyncio.sleep(2 ** attempt)

    variants = _parse_variants(generated, tone)
    return {
        "generated_reply": variants["recommended"],  # back-compat: recommended is the default
        "variants": variants,
        "topics": variants["topics"],
        "tone": tone,
    }
