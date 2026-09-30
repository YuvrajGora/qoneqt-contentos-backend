"""
Developer smoke test for image generation (Milestone 3).

Loads .env, calls ImageGenerator with a dummy job/scene ID and a test prompt,
and reports the saved file path.

Usage (from backend/ directory):
    python scripts/test_image_generation.py

Requires GEMINI_API_KEY to be set in backend/.env.
If the key is missing this script reports clearly and exits cleanly.
"""

import json
import os
import sys
from pathlib import Path

# Ensure backend/ package root is importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.services.image_generator import ImageGenerator, ImageGenerationError


def main() -> None:
    if not settings.gemini_api_key:
        print(
            "[SKIP] Live Gemini smoke test not performed because GEMINI_API_KEY was not configured.\n"
            "Set GEMINI_API_KEY in backend/.env and re-run this script.",
            file=sys.stderr,
        )
        sys.exit(0)

    test_job_id = "smoke-test-job"
    test_scene_id = 1
    test_prompt = (
        "A cinematic shot of a cyberpunk city at night. Neon-lit skyscrapers reflected "
        "in rain-soaked streets, volumetric fog, vertical composition, wide establishing shot, "
        "deep blue and magenta colour grading, photorealistic."
    )

    print(f"Generating image for: {test_prompt[:80]}...\n")

    ig = ImageGenerator()
    try:
        path = ig.generate_scene_image(test_job_id, test_scene_id, test_prompt)
    except ImageGenerationError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"[OK] Image saved to: {path}")
    assert Path(path).exists(), "File was not found on disk after saving."


if __name__ == "__main__":
    main()
