"""
Developer test for TTS generation with dynamic styles.

This script tests the newly implemented ElevenLabs style-to-voice mapping.
It iterates over multiple styles and generates audio using the respective voice.

Usage (from backend/ directory):
    python scripts/test_tts_styles.py
"""

import asyncio
import sys
import codecs
from pathlib import Path

# Ensure backend/ package root is importable when run as a standalone script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.tts_generator import TTSGenerator, TTSGenerationError

async def main() -> None:
    test_job_id = "test-styles-job"
    
    test_cases = [
        ("educational", "Welcome to today's lesson. We'll be exploring the fascinating world of quantum physics."),
        ("dramatic", "In a world where shadows reign, one hero must rise above the darkness."),
        ("comedic", "Why did the chicken cross the road? To get away from this ridiculous script!"),
        ("energetic", "Are you ready for the most incredible experience of your life? Let's go!"),
        ("hindi", "नमस्ते, आज हम क्वांटम भौतिकी की दिलचस्प दुनिया के बारे में जानेंगे।")
    ]

    tts = TTSGenerator()

    for i, (style, text) in enumerate(test_cases, start=1):
        print(f"\n[{i}/{len(test_cases)}] Synthesising with style: {style}")
        print(f"Text: {text}")
        try:
            path = await tts.generate_scene_audio(
                job_id=test_job_id,
                scene_id=i,
                text=text,
                style=style
            )
            assert Path(path).exists(), f"File not found: {path}"
            size_kb = Path(path).stat().st_size // 1024
            print(f"[OK] Audio saved to: {path} ({size_kb} KB)")
        except TTSGenerationError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
