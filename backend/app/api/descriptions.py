import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.deps import require_location_access, staff_required
from app.core.authorization import assert_location_active
from app.core.roles import Role
from app.models.user import User
from app.models.location import Location
from app.models.description_generation import DescriptionGeneration
from app.schemas.description import (
    GenerateDescriptionRequest, DescriptionResponse, PolicyFlags,
    ValidateDescriptionRequest, ValidateDescriptionResponse,
)
from app.services.description_generator_service import generate_description
from app.services import description_validation
from app.services.billing.credit_service import CreditService
from app.llm.exceptions import LLMProviderError

logger = logging.getLogger(__name__)

router = APIRouter()

FIRST_GENERATION_CREDITS = 5
REGENERATION_CREDITS = 2
# The prompt aims for 700-740, but LLMs can't hit a tight char window — chasing it
# oscillates (expand overshoots >800, shorten overcorrects <600). So we only correct
# a draft that is genuinely short (<600) or invalid (>750, a hard flag); anything in
# 600-750 is accepted as substantial. Biasing long happens in the prompt, not the loop.
TARGET_MIN_CHARS = 600
MAX_CORRECTIVE_PASSES = 2  # bound on LLM calls: initial + at most this many rewrites


class _Unbilled(Exception):
    """Raised inside the credit context to skip the charge when the final output
    still fails the hard-policy validator after one rewrite. The user keeps the
    draft to hand-edit (free /validate) and is not charged for unusable output."""


@router.post("/locations/{location_id}/description/generate", response_model=DescriptionResponse)
async def generate_location_description(
    body: GenerateDescriptionRequest,
    location_id: int = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    if current_user.role == Role.VIEWER:
        raise HTTPException(status_code=403, detail="Viewers cannot generate descriptions")

    assert_location_active(db, location_id)

    location = db.query(Location).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id,
    ).first()
    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    # First successful generation for this location costs more; regenerations are
    # cheaper. Blocked attempts never persist a row, so they never bump the price.
    is_first = db.query(DescriptionGeneration.id).filter(
        DescriptionGeneration.location_id == location_id
    ).first() is None
    price = FIRST_GENERATION_CREDITS if is_first else REGENERATION_CREDITS
    action_name = "generate_business_description" if is_first else "regenerate_business_description"

    mode = body.mode
    # Refine the on-screen draft if the client sent one, else the saved description.
    existing = (body.base_text or location.description or "").strip()
    if mode == "improve_existing" and not existing:
        mode = "generate_new"  # nothing to improve — generate fresh

    result = None
    analysis = None
    try:
        with CreditService.consume_ai_credit(db, current_user.organization_id, action_name, credits_required=price):
            result = await generate_description(
                location, tone=body.tone, language=body.language, usp=body.usp,
                services=body.services, audience=body.audience, mode=mode,
                nudge=body.nudge, existing_description=existing or None,
            )
            analysis = description_validation.analyze(result["description"], location.primary_category)

            # Corrective passes fix hard policy issues AND steer length to the 700-740 band
            # (expand if short, shorten if >750), so paying never lands on a thin/short result.
            for _ in range(MAX_CORRECTIVE_PASSES):
                too_short = result["char_count"] < TARGET_MIN_CHARS
                if not (analysis["hard_flags"] or too_short):
                    break
                result = await generate_description(
                    location, tone=body.tone, language=body.language, usp=body.usp,
                    services=body.services, audience=body.audience,
                    mode="rewrite_policy_safe", existing_description=result["description"],
                    policy_issues=analysis["hard_flags"], current_chars=result["char_count"],
                )
                analysis = description_validation.analyze(result["description"], location.primary_category)

            if analysis["hard_flags"]:
                raise _Unbilled()  # skips the deduction; draft returned below uncharged

            db.add(DescriptionGeneration(
                organization_id=current_user.organization_id,
                location_id=location_id,
                user_id=current_user.id,
                action=action_name,
                payload=body.model_dump(),
                generated_text=result["description"],
                char_count=result["char_count"],
                category_mentioned=result["category_mentioned"],
                locality_used=result["locality_used"],
                improvement_notes=result["improvement_notes"],
                policy_flags={"hard": analysis["hard_flags"], "soft": analysis["soft_flags"]},
            ))
        # contextmanager committed the deduction + the row together on clean exit.
    except _Unbilled:
        return DescriptionResponse(
            charged=False, credits_charged=0, is_valid=False,
            description=result["description"], char_count=result["char_count"],
            status=analysis["status"],
            policy_flags=PolicyFlags(hard=analysis["hard_flags"], soft=analysis["soft_flags"]),
            improvement_notes=result["improvement_notes"], seo_terms=result["seo_terms"],
            category_mentioned=result["category_mentioned"], locality_used=result["locality_used"],
        )
    except LLMProviderError:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="AI service temporarily unavailable. Please try again.")
    except HTTPException:
        raise  # credit pre-check (402/404) and access errors pass through unchanged
    except Exception as e:
        logger.error("Description generation failed for location %s: %s", location_id, e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY,
                            detail="AI service temporarily unavailable. Please try again.")

    return DescriptionResponse(
        charged=True, credits_charged=price, is_valid=True,
        description=result["description"], char_count=result["char_count"],
        status=analysis["status"],
        policy_flags=PolicyFlags(hard=[], soft=analysis["soft_flags"]),
        improvement_notes=result["improvement_notes"], seo_terms=result["seo_terms"],
        category_mentioned=result["category_mentioned"], locality_used=result["locality_used"],
    )


@router.post("/locations/{location_id}/description/validate", response_model=ValidateDescriptionResponse)
def validate_location_description(
    body: ValidateDescriptionRequest,
    location_id: int = Depends(require_location_access),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_required),
):
    """Deterministic, no-LLM, no-credit policy check for live editing."""
    location = db.query(Location.primary_category).filter(
        Location.id == location_id,
        Location.organization_id == current_user.organization_id,
    ).first()
    primary_category = location[0] if location else None
    v = description_validation.validate(body.text, primary_category)
    return ValidateDescriptionResponse(**v)
