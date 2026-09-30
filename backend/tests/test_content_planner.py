"""
Tests for the ContentPlanner service.

ALL tests use mocked Gemini responses — no real API key required.
The real Gemini call is replaced by injecting a _provider_fn into generate_content_plan.
"""

import pytest
from pydantic import ValidationError
from unittest.mock import patch

from app.services.content_planner import (
    generate_content_plan,
    ContentPlanValidationError,
    ContentPlannerError,
)
from app.schemas.content import ContentPlan, Scene


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_raw(
    title="Why Solar Energy Matters",
    hook="Did you know the sun could power the entire world in one hour?",
    script="Solar energy is abundant, clean, and increasingly affordable...",
    scenes=None,
):
    if scenes is None:
        scenes = [
            {
                "scene_id": 1,
                "duration": 10.0,
                "narration": "The sun delivers more energy in one hour than humanity uses in a year.",
                "visual_prompt": (
                    "Aerial view of a vast solar farm at sunrise, golden light reflecting off "
                    "thousands of photovoltaic panels stretching to the horizon, wide establishing "
                    "shot, warm orange-yellow tones, gentle camera push forward."
                ),
                "on_screen_text": "The sun: our biggest energy source",
            },
            {
                "scene_id": 2,
                "duration": 12.0,
                "narration": "Solar panel costs have fallen over 90% in the last decade alone.",
                "visual_prompt": (
                    "Close-up of a technician's hands installing a sleek black solar panel on a "
                    "suburban rooftop, overcast sky in background emphasising the clean white panel, "
                    "shallow depth of field, natural daylight, eye-level shot."
                ),
                "on_screen_text": "90% cost drop in 10 years",
            },
            {
                "scene_id": 3,
                "duration": 12.0,
                "narration": "Countries like Germany and Denmark now generate over 50% of their electricity from renewables.",
                "visual_prompt": (
                    "Time-lapse style graphic showing a world map with green energy coverage expanding "
                    "across Europe, clean minimalist design, bright green glowing regions, dark blue "
                    "background, data-driven motion infographic feel."
                ),
                "on_screen_text": "50%+ renewable in some nations",
            },
            {
                "scene_id": 4,
                "duration": 11.0,
                "narration": "Making the switch isn't just good for the planet — it's good for your wallet too.",
                "visual_prompt": (
                    "A happy family looking at a noticeably lower electricity bill at their kitchen "
                    "table, solar panels visible through the window behind them, warm interior "
                    "lighting, medium shot, candid lifestyle feel."
                ),
                "on_screen_text": "Save money. Save the planet.",
            },
        ]
    return {
        "title": title,
        "hook": hook,
        "script": script,
        "scenes": scenes,
    }


def _mock_provider(raw: dict):
    """Returns a provider_fn that always returns `raw`."""
    return lambda system_prompt, user_prompt: raw


# ---------------------------------------------------------------------------
# 1. Valid ContentPlan is accepted
# ---------------------------------------------------------------------------

def test_valid_content_plan_accepted():
    raw = _make_valid_raw()
    plan = generate_content_plan("solar energy", 45, "educational", _provider_fn=_mock_provider(raw))
    assert isinstance(plan, ContentPlan)
    assert plan.title == raw["title"]
    assert plan.hook == raw["hook"]
    assert len(plan.scenes) == 4


# ---------------------------------------------------------------------------
# 2. Missing title rejected
# ---------------------------------------------------------------------------

def test_missing_title_rejected():
    raw = _make_valid_raw(title="")
    with pytest.raises(ContentPlanValidationError, match="title"):
        generate_content_plan("solar energy", 45, "educational", _provider_fn=_mock_provider(raw))


# ---------------------------------------------------------------------------
# 3. Empty narration rejected
# ---------------------------------------------------------------------------

def test_empty_narration_rejected():
    scenes = _make_valid_raw()["scenes"]
    scenes[1]["narration"] = ""
    raw = _make_valid_raw(scenes=scenes)
    with pytest.raises(ContentPlanValidationError):
        generate_content_plan("solar energy", 45, "educational", _provider_fn=_mock_provider(raw))


# ---------------------------------------------------------------------------
# 4. Empty visual_prompt rejected
# ---------------------------------------------------------------------------

def test_empty_visual_prompt_rejected():
    scenes = _make_valid_raw()["scenes"]
    scenes[0]["visual_prompt"] = ""
    raw = _make_valid_raw(scenes=scenes)
    with pytest.raises(ContentPlanValidationError):
        generate_content_plan("solar energy", 45, "educational", _provider_fn=_mock_provider(raw))


# ---------------------------------------------------------------------------
# 5. Duplicate scene IDs rejected
# ---------------------------------------------------------------------------

def test_duplicate_scene_ids_rejected():
    scenes = _make_valid_raw()["scenes"]
    scenes[2]["scene_id"] = 1  # duplicate
    raw = _make_valid_raw(scenes=scenes)
    with pytest.raises(ContentPlanValidationError, match="unique"):
        generate_content_plan("solar energy", 45, "educational", _provider_fn=_mock_provider(raw))


# ---------------------------------------------------------------------------
# 6. Invalid (non-positive) scene duration rejected
# ---------------------------------------------------------------------------

def test_invalid_scene_duration_rejected():
    scenes = _make_valid_raw()["scenes"]
    scenes[0]["duration"] = -5.0
    raw = _make_valid_raw(scenes=scenes)
    with pytest.raises(ContentPlanValidationError):
        generate_content_plan("solar energy", 45, "educational", _provider_fn=_mock_provider(raw))


# ---------------------------------------------------------------------------
# 7. Valid mocked Gemini response becomes a valid ContentPlan
# ---------------------------------------------------------------------------

def test_mocked_gemini_response_produces_valid_plan():
    raw = _make_valid_raw()
    plan = generate_content_plan("solar energy", 45, "educational", _provider_fn=_mock_provider(raw))
    assert plan.total_duration() == pytest.approx(45.0, abs=0.1)
    ids = [s.scene_id for s in plan.scenes]
    assert len(ids) == len(set(ids)), "scene IDs should be unique"
    for scene in plan.scenes:
        assert scene.duration > 0
        assert scene.narration
        assert scene.visual_prompt


# ---------------------------------------------------------------------------
# 8. Missing GEMINI_API_KEY raises a controlled error
# ---------------------------------------------------------------------------

def test_missing_api_key_raises_provider_config_error():
    def _bad_provider(system_prompt, user_prompt):
        raise ContentPlannerError("GEMINI_API_KEY is not configured.")

    with pytest.raises(ContentPlannerError, match="GEMINI_API_KEY"):
        generate_content_plan("solar energy", 45, "educational", _provider_fn=_bad_provider)


# ---------------------------------------------------------------------------
# 9. Scene schema: scene_id must be positive
# ---------------------------------------------------------------------------

def test_scene_id_must_be_positive():
    with pytest.raises(ValidationError):
        Scene(
            scene_id=0,
            duration=10.0,
            narration="Test narration",
            visual_prompt="Test visual prompt describing a sunny day",
            on_screen_text="Test text",
        )


# ---------------------------------------------------------------------------
# 10. Duration coverage validation (too far off)
# ---------------------------------------------------------------------------

def test_duration_coverage_out_of_tolerance():
    # Request 45s but provide scenes totalling only 5s — way outside tolerance
    scenes = [
        {
            "scene_id": 1,
            "duration": 2.5,
            "narration": "Short narration",
            "visual_prompt": "Close-up of a single solar panel in bright sunlight, minimal composition.",
            "on_screen_text": "Solar power",
        },
        {
            "scene_id": 2,
            "duration": 2.5,
            "narration": "Another short narration",
            "visual_prompt": "Wide shot of a wind turbine farm at dusk, purple sky, cinematic.",
            "on_screen_text": "Clean energy",
        },
    ]
    raw = _make_valid_raw(scenes=scenes)
    with pytest.raises(ContentPlanValidationError, match="duration"):
        generate_content_plan("solar energy", 45, "educational", _provider_fn=_mock_provider(raw))
