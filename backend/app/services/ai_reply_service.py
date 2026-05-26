from app.models.review import Review
from app.models.location import Location
from app.llm.factory import get_llm_provider

async def generate_reply(review: Review, location: Location) -> dict:
    rating = review.rating if review.rating is not None else 3
    if rating in (4, 5):
        tone = "grateful"
    elif rating == 3:
        tone = "neutral"
    else:
        tone = "empathetic"

    safe_comment = (review.comment or "")[:2000]
    review_text_xml = f"<review>{safe_comment}</review>" if safe_comment else "No written review provided."

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

    user_message = f"""Business Name: {location.location_name}
Business Type: {location.primary_category}
Business Address: {location.address}
Star Rating: {rating} out of 5
Reviewer Name: {review.reviewer_name}
Customer Review:

{review_text_xml}


Write a reply following the tone rules for a {rating}-star rating."""

    llm = get_llm_provider()
    generated = await llm.complete(system_prompt, user_message, max_tokens=200)

    return {
        "generated_reply": generated,
        "tone": tone
    }
