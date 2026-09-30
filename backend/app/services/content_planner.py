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
import os
import time
from typing import Any, Dict

from pydantic import ValidationError
from google import genai
from google.genai import types

from app.schemas.content import ContentPlan
from app.services.prompts import SYSTEM_INSTRUCTION, build_user_prompt
from app.services.groq_client import generate_structured_json
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
    """
    # Lazy inject
    if _provider_fn is None:
        def _default_provider(system_prompt: str | None = None, user_prompt: str | None = None, **kwargs) -> Dict[str, Any]:
            errors = []

            # 1. Attempt Gemini with automatic model fallback
            if settings.gemini_api_key:
                try:
                    client = genai.Client(api_key=settings.gemini_api_key)
                    models_to_try = [settings.gemini_text_model]
                    for m in ["gemini-3.5-flash-lite", "gemini-flash-latest", "gemini-3.5-flash", "gemini-3.7-flash"]:
                        if m not in models_to_try:
                            models_to_try.append(m)

                    for model in models_to_try:
                        for attempt in range(2):
                            try:
                                logger.info("Calling Gemini for content planning (model=%s, attempt=%d)", model, attempt + 1)
                                response = client.models.generate_content(
                                    model=model,
                                    contents=user_prompt,
                                    config=types.GenerateContentConfig(
                                        system_instruction=system_prompt,
                                        response_mime_type="application/json",
                                        response_schema=ContentPlan,
                                    ),
                                )
                                if response.text:
                                    return json.loads(response.text)
                            except Exception as ge:
                                err_str = str(ge)
                                is_quota = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower()
                                if is_quota:
                                    logger.warning("Gemini model %s quota exhausted (429 RESOURCE_EXHAUSTED). Skipping retries on this model.", model)
                                    errors.append(f"Gemini {model}: 429 quota exhausted")
                                    break  # Do not waste time retrying daily quota exhaustion on same model
                                else:
                                    logger.warning("Gemini model %s error: %s", model, err_str)
                                    errors.append(f"Gemini {model}: {err_str}")
                                    if attempt < 1:
                                        time.sleep(1)
                                        continue
                                    break
                except Exception as ce:
                    errors.append(f"Gemini client initialization failed: {ce}")
            else:
                errors.append("GEMINI_API_KEY not configured")

            # 2. Attempt Groq fallback if configured
            groq_key = settings.groq_api_key or os.getenv("GROQ_API_KEY")
            if groq_key:
                try:
                    logger.info("Attempting Groq fallback for content planning...")
                    groq_data = generate_structured_json(
                        system_prompt=system_prompt or SYSTEM_INSTRUCTION,
                        user_prompt=user_prompt or ""
                    )
                    if groq_data:
                        logger.info("Content planning succeeded via Groq fallback.")
                        return groq_data
                except Exception as groq_err:
                    logger.warning("Groq fallback failed: %s", groq_err)
                    errors.append(f"Groq fallback: {groq_err}")
            else:
                errors.append("GROQ_API_KEY not configured for fallback")

            # 3. All failed — raise structured error
            error_details = "; ".join(errors)
            raise ContentPlannerError(f"Content planning failed across all AI providers. Details: {error_details}")

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
