"""
ContentPlanner service.

Responsibilities:
  1. Accept topic / duration / style from the caller.
  2. Build prompts.
  3. Call the Groq client.
  4. Validate the response with Pydantic.
  5. Validate duration coverage.
  6. Return a validated ContentPlan (or raise a descriptive exception).

This module has NO FastAPI dependency and can be called from:
  - A background job worker (future milestone)
  - A development smoke-test script
  - Unit tests with a mocked Groq client
"""

import logging
import json
import time
from typing import Any, Dict

from pydantic import ValidationError
from google import genai
from google.genai import types

from app.schemas.content import ContentPlan
from app.services.prompts import SYSTEM_INSTRUCTION, build_user_prompt
from app.core.config import settings

logger = logging.getLogger(__name__)

# How far off (as a fraction) total scene duration may be from requested duration.
# 0.35 = ±35 % tolerance — generous because LLMs sometimes round durations.
DURATION_TOLERANCE = 0.35


class ContentPlanValidationError(Exception):
    """The generated content plan failed Pydantic or semantic validation."""


class ContentPlannerError(Exception):
    """Base class for content planner failures passed back to the caller."""


def generate_content_plan(
    topic: str,
    duration: int,
    style: str,
    *,
    _provider_fn=None,  # injectable for unit tests
) -> ContentPlan:
    """
    Generate a validated ContentPlan for the given topic/duration/style.

    Parameters
    ----------
    topic    : subject of the video
    duration : total desired video length in seconds
    style    : tone/style descriptor (e.g. "educational", "entertaining")
    _provider_fn : optional override for the Groq call (used in tests)

    Returns
    -------
    ContentPlan

    Raises
    ------
    ContentPlanValidationError  – model output failed validation
    ContentPlannerError         – provider or config error (wraps provider exceptions)
    """
    # Lazy inject
    if _provider_fn is None:
        def _default_provider(system_prompt: str | None = None, user_prompt: str | None = None, **kwargs) -> Dict[str, Any]:
            if not settings.gemini_api_key:
                raise ContentPlannerError("GEMINI_API_KEY is not configured.")
            client = genai.Client(api_key=settings.gemini_api_key)
            
            for attempt in range(4):
                try:
                    response = client.models.generate_content(
                        model=settings.gemini_text_model,
                        contents=user_prompt,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            response_mime_type="application/json",
                            response_schema=ContentPlan,
                        ),
                    )
                    return json.loads(response.text)
                except Exception as e:
                    if attempt < 3:
                        delay = 2 ** attempt
                        print(f"Gemini API overloaded. Retrying in {delay}s (Attempt {attempt + 1}/4)...")
                        time.sleep(delay)
                        continue
                    raise e
            
        _provider_fn = _default_provider

    system_prompt = SYSTEM_INSTRUCTION
    user_prompt = build_user_prompt(topic=topic, duration=duration, style=style)

    logger.info("Generating content plan with Gemini: topic=%r duration=%d style=%r", topic, duration, style)

    try:
        raw: Dict[str, Any] = _provider_fn(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    except Exception as exc:
        # Re-raise provider exceptions as ContentPlannerError without leaking
        # SDK internals or credentials.
        raise ContentPlannerError(str(exc)) from exc

    # --- Pydantic validation ---
    try:
        plan = ContentPlan.model_validate(raw)
    except ValidationError as exc:
        # Extract human-readable errors without leaking raw LLM output.
        error_summary = "; ".join(
            f"{'.'.join(str(l) for l in e['loc'])}: {e['msg']}"
            for e in exc.errors()
        )
        raise ContentPlanValidationError(
            f"Generated content plan failed validation: {error_summary}"
        ) from exc

    # --- Duration coverage validation ---
    total = plan.total_duration()
    lower = duration * (1 - DURATION_TOLERANCE)
    upper = duration * (1 + DURATION_TOLERANCE)
    if not (lower <= total <= upper):
        raise ContentPlanValidationError(
            f"Total scene duration {total:.1f}s is too far from requested "
            f"{duration}s (tolerance ±{int(DURATION_TOLERANCE * 100)}%). "
            "The model produced an implausible plan."
        )

    logger.info(
        "Content plan validated: %d scenes, %.1fs total (requested %ds)",
        len(plan.scenes),
        total,
        duration,
    )
    return plan
