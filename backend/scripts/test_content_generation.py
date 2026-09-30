"""
Developer smoke-test script for the content planner.

Usage (from backend/ directory):
    python scripts/test_content_generation.py

Requires GROQ_API_KEY and GROQ_MODEL to be set in .env or environment.
If the key is missing this script reports the config error and exits cleanly.

Does NOT call pytest — this is a manual live integration check.
"""

import json
import sys
import os

# Make sure backend/ package root is on the path when run as a script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.content_planner import generate_content_plan, ContentPlannerError, ContentPlanValidationError
from app.core.config import settings


def main() -> None:
    topic = "Why solar energy matters"
    duration = 45
    style = "educational"

    if not settings.groq_api_key:
        print(
            "[SKIP] Live Groq smoke test not performed because GROQ_API_KEY was not configured.\n"
            "Set GROQ_API_KEY and GROQ_MODEL in backend/.env and re-run this script.",
            file=sys.stderr,
        )
        sys.exit(0)

    if not settings.groq_model:
        print(
            "[ERROR] GROQ_MODEL is not set. Add it to backend/.env (e.g. GROQ_MODEL=llama-3.3-70b-versatile).",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Generating content plan for: {topic!r} ({duration}s, {style})\n")

    try:
        plan = generate_content_plan(topic=topic, duration=duration, style=style)
    except ContentPlanValidationError as exc:
        print(f"[VALIDATION ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
    except ContentPlannerError as exc:
        print(f"[PROVIDER ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    output = plan.model_dump()
    print(json.dumps(output, indent=2, ensure_ascii=False))

    # Assertions
    assert plan.title, "title is empty"
    assert plan.hook, "hook is empty"
    assert plan.script, "script is empty"
    assert plan.scenes, "scenes list is empty"
    ids = [s.scene_id for s in plan.scenes]
    assert len(ids) == len(set(ids)), "scene_ids are not unique"
    for scene in plan.scenes:
        assert scene.duration > 0, f"scene {scene.scene_id} has non-positive duration"
        assert scene.narration, f"scene {scene.scene_id} has empty narration"
        assert scene.visual_prompt, f"scene {scene.scene_id} has empty visual_prompt"

    total = plan.total_duration()
    print(f"\n[OK] {len(plan.scenes)} scenes | total duration: {total:.1f}s (requested: {duration}s)")


if __name__ == "__main__":
    main()
