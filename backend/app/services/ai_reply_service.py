import asyncio
import logging
from xml.sax.saxutils import escape as xml_escape

from app.models.review import Review
from app.models.location import Location
from app.llm.factory import get_llm_provider

logger = logging.getLogger(__name__)

MAX_REPLY_TOKENS = 300


def _sanitize_prompt_input(value, max_len=200):
    if not value:
        return "Not specified"
    return " ".join(str(value).split())[:max_len]


async def generate_reply(review: Review, location: Location) -> dict:
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

    system_prompt = """You are an expert Google Business Profile review reply specialist for local businesses.
Your job is to write a single, concise reply to a customer review on behalf of the business owner.

Rules:
- Reply must be between 40 and 100 words. Keep it highly concise.
- Never mention competitor names.
- Never make promises you cannot keep (e.g., "we will fix this immediately").
- Never invent services, staff, policies, or facts not provided in the context.
- Never use generic filler phrases like "Thank you for your feedback" as the opening line.
- Write in first-person plural (we/our) as the business owner.
- Do not use hashtags or emojis.
- Return ONLY the reply text. No preamble, no explanation, no quotation marks, no em-dash.
- If the review has no text (rating only), write a brief acknowledgment appropriate to the star rating without referencing specific praise or complaints.

Tone rules based on star rating:
- 5 stars: Warm, enthusiastic, grateful. Reinforce what the reviewer praised.
- 4 stars: Positive and appreciative. Acknowledge any minor concern if mentioned.
- 3 stars: Professional, balanced. Acknowledge the experience, show commitment to improvement.
- 2 stars: Empathetic and apologetic. Take responsibility without being defensive. Invite direct outreach.
- 1 star: Deeply empathetic, apologetic, calm, and resolution-oriented. Offer to resolve offline."""

    user_message = f"""Business Name: {location_name}
Business Type: {primary_category}
Business Address: {address}
Star Rating: {rating} out of 5
Reviewer Name: {reviewer_name}
Customer Review:

{review_text_xml}


Write a reply following the tone rules for a {rating}-star rating."""

    llm = get_llm_provider()
    generated = None
    for attempt in range(3):
        try:
            generated = await asyncio.wait_for(
                llm.complete(system_prompt, user_message, max_tokens=MAX_REPLY_TOKENS),
                timeout=30,
            )
            break
        except Exception as e:
            if attempt == 2:
                raise
            await asyncio.sleep(2 ** attempt)

    return {
        "generated_reply": generated,
        "tone": tone
    }
