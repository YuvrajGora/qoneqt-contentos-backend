"""
Developer smoke test for TTS generation (Milestone 4).

Performs a LIVE edge-tts call — no API key is required; edge-tts connects to
Microsoft's servers directly. An internet connection is needed.

Usage (from backend/ directory):
    python scripts/test_tts_generation.py

Writes the output MP3 to temp_assets/smoke-test-job_scene_1.mp3.
"""

import asyncio
import sys
from pathlib import Path

# Ensure backend/ package root is importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.tts_generator import TTSGenerator, TTSGenerationError


async def main() -> None:
    test_job_id = "smoke-test-job"
    test_scene_id = 1
    test_text = (
        "This is a live test of the Edge TTS integration for our video pipeline. "
        "The voice is natural, expressive, and ready to be combined with scene visuals."
    )

    print(f"Synthesising: {test_text[:80]}...\n")

    tts = TTSGenerator()
    try:
        path = await tts.generate_scene_audio(test_job_id, test_scene_id, test_text)
    except TTSGenerationError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    assert Path(path).exists(), f"File not found: {path}"
    size_kb = Path(path).stat().st_size // 1024
    print(f"[OK] Audio saved to: {path}  ({size_kb} KB)")


if __name__ == "__main__":
    asyncio.run(main())
