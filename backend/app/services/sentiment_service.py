import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from xml.sax.saxutils import escape as xml_escape

from sqlalchemy.orm import Session

from app.constants.review_sentiment import ALLOWED_SENTIMENTS, ALLOWED_ISSUE_CATEGORIES
from app.llm.exceptions import LLMProviderError
from app.llm.factory import get_llm_provider
from app.models.review import Review

logger = logging.getLogger(__name__)

# Number of reviews classified per LLM call. Used by BOTH the chunking and the
# max_tokens budget below so the two can never drift (a stale "5" in the docstring
# vs a real "15" once made truncation silent — see _tag_batch).
SENTIMENT_BATCH_SIZE = 15
# Worst-case completion tokens for one classified review (its JSON object plus the
# array punctuation). max_tokens is sized to the batch from this so a full batch's
# JSON array is never truncated mid-output (which would drop the whole batch).
_TOKENS_PER_REVIEW = 60
_MIN_COMPLETION_TOKENS = 256

SYSTEM_PROMPT = """You are a review classification engine for a local business reputation management platform.

Your job is to analyze customer reviews and classify each one with:
1. A sentiment label
2. An issue category label

Sentiment options (pick exactly one):
- "Positive": happy, satisfied, praise-heavy
- "Neutral": mixed, neither clearly positive nor negative
- "Negative": dissatisfied, disappointed, critical
- "Angry": hostile, threatening, highly emotional, demanding

Issue category options (pick exactly one):
- "Staff Praise": compliments about employees, service attitude, helpfulness
- "Service Issue": complaints or feedback about service quality or experience
- "Pricing Concern": mentions of cost, value for money, expensive, cheap
- "Cleanliness": mentions of hygiene, tidiness, appearance of premises
- "Delivery Issue": problems with delivery, shipping, timing of orders
- "Wait Time": mentions of queues, waiting, slow service
- "Product Quality": feedback about the product itself, quality, taste, durability
- "General Feedback": anything that does not clearly fit the above categories

Rules:
- Return ONLY a valid JSON array. No preamble, no explanation, no markdown fences.
- Each object must have exactly these keys: "id", "sentiment", "issue_category"
- "id" must be the integer review ID as provided in the input
- If the review has no text (comment is null or empty), classify using star rating only:
    5 or 4 stars → "Positive", "General Feedback"
    3 stars       → "Neutral",  "General Feedback"
    1 or 2 stars  → "Negative", "General Feedback"
- Never use label strings not listed above."""


async def tag_reviews_sentiment(reviews: list[Review], db: Session) -> None:
    """
    Public entry point. Filters to untagged reviews, splits into batches of
    SENTIMENT_BATCH_SIZE, and calls _tag_batch() for each. A failed batch never
    aborts remaining batches.

    On LLM failure we intentionally do NOT re-enqueue work here. Reviews that fail
    tagging keep sentiment_tagged_at = NULL and are re-swept by the hourly
    retry_failed_sentiment_beat_task. Re-enqueuing the whole-location task per failing
    chunk (as we used to) multiplied calls into an unbounded paid-LLM storm whenever
    Groq was unhealthy — the hourly sweep already provides bounded, idempotent retry.
    """
    untagged = [r for r in reviews if r.sentiment_tagged_at is None]

    if not untagged:
        return

    chunks: list[list[Review]] = [
        untagged[i:i + SENTIMENT_BATCH_SIZE]
        for i in range(0, len(untagged), SENTIMENT_BATCH_SIZE)
    ]

    for chunk in chunks:
        try:
            await _tag_batch(chunk, db)
        except LLMProviderError as e:
            # Leave these reviews untagged; the hourly beat sweep will retry them.
            logger.error("LLMProviderError tagging sentiment batch (will retry via hourly sweep): %s", str(e))
        except Exception as e:
            logger.error("Unexpected error tagging sentiment batch: %s", str(e))


async def _tag_batch(reviews: list[Review], db: Session) -> None:
    """
    Classifies a batch of reviews via LLM and persists valid results.
    Skips individual items that fail validation; never writes partial/invalid labels.
    """
    # Build user message. The comment is attacker-controlled text, so XML-escape it
    # before embedding in <review> tags — otherwise a review containing "</review>",
    # fake "ID:"/"---" delimiters, or direct instructions could spoof another review's
    # id or coax a wrong sentiment label (prompt/structure injection). Matches the
    # escaping the ai_reply_service already applies to the same field.
    review_lines: list[str] = []
    for review in reviews:
        safe_comment = xml_escape((review.comment or "")[:500])
        comment_xml = f"<review>{safe_comment}</review>" if safe_comment else "<review></review>"
        review_lines.append(
            f"ID: {review.id}\nRating: {review.rating} stars\nReview: {comment_xml}"
        )

    reviews_block = "\n\n---\n\n".join(review_lines)
    user_message = (
        f"Classify the following {len(reviews)} reviews. "
        f"Return a JSON array with one object per review.\n\n"
        f"Reviews:\n{reviews_block}\n\n---"
    )

    # Size the completion budget to the batch so the JSON array can't be truncated
    # mid-output (which raises JSONDecodeError below and silently drops the entire
    # batch, leaving the reviews to loop through the hourly retry forever).
    max_tokens = max(_MIN_COMPLETION_TOKENS, len(reviews) * _TOKENS_PER_REVIEW)

    llm = get_llm_provider()
    raw: str = ""
    for attempt in range(3):
        try:
            raw = await llm.complete(SYSTEM_PROMPT, user_message, max_tokens=max_tokens, temperature=0.1)
            break
        except LLMProviderError as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt  # 1s, 2s
            logger.warning("LLM batch attempt %d failed, retrying in %ds: %s", attempt + 1, wait, str(e))
            await asyncio.sleep(wait)

    # Strip markdown fences if present
    raw_text = raw
    cleaned = re.sub(r"^\s*```(?:json)?\s*\n?|\n?\s*```\s*$", "", raw_text.strip(), flags=re.MULTILINE)

    # Parse JSON
    try:
        items: list[Any] = json.loads(cleaned)
    except json.JSONDecodeError as e:
        logger.error("Failed to parse LLM JSON response for sentiment batch: %s", str(e))
        return

    if not isinstance(items, list):
        logger.error("LLM sentiment response was not a JSON array — skipping batch.")
        return

    # Build a lookup map for the batch
    review_map: dict[int, Review] = {r.id: r for r in reviews}

    # Validate and apply each item
    valid_updates: list[Review] = []
    for item in items:
        if not isinstance(item, dict):
            logger.warning("Skipping non-dict item in sentiment batch response.")
            continue

        if not all(k in item for k in ("id", "sentiment", "issue_category")):
            logger.warning("Skipping item missing required keys: %s", list(item.keys()))
            continue

        try:
            review_id = int(item["id"])
        except (ValueError, TypeError, KeyError):
            logger.warning("Skipping item with unparseable id: %s", item.get("id"))
            continue

        sentiment = item["sentiment"]
        issue_category = item["issue_category"]

        if sentiment not in ALLOWED_SENTIMENTS:
            logger.warning("Skipping item %s — invalid sentiment: %s", review_id, sentiment)
            continue

        if issue_category not in ALLOWED_ISSUE_CATEGORIES:
            logger.warning("Skipping item %s — invalid issue_category: %s", review_id, issue_category)
            continue

        review = review_map.get(review_id)
        if review is None:
            logger.warning("Skipping item — review id %s not found in batch.", review_id)
            continue

        review.sentiment = sentiment
        review.issue_category = issue_category
        review.sentiment_tagged_at = datetime.now(timezone.utc)
        valid_updates.append(review)

    if not valid_updates:
        return

    for r in valid_updates:
        db.add(r)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("DB error committing sentiment updates: %s", str(e))
