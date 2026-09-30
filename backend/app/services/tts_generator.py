"""
TTSGenerator service — Milestone 4.

Uses the ElevenLabs SDK for high-quality voiceover audio, falling back to
the free `edge-tts` library if no API key is provided or if ElevenLabs fails.
Audio is written as MP3 to temp_assets/{job_id}_scene_{scene_id}.mp3.

Architecture notes
------------------
* This is the ONLY module that imports elevenlabs and edge_tts. All other modules
  receive file paths or raise TTSGenerationError.
* `generate_scene_audio` is async. ElevenLabs streaming via AsyncElevenLabs
  is consumed asynchronously.
* Designed to consume ContentPlan.scenes[n].narration directly.
"""

import asyncio
import logging
from pathlib import Path

import edge_tts
from elevenlabs.client import AsyncElevenLabs
from elevenlabs.core.api_error import ApiError

from app.core.config import settings
from app.services.image_generator import TEMP_ASSETS_DIR  # reuse same output dir

logger = logging.getLogger(__name__)

DEFAULT_EDGE_VOICE = "en-US-ChristopherNeural"

# Pre-selected high-quality ElevenLabs voices mapped by style/requirement
ELEVENLABS_VOICE_MAP = {
    "educational": "pNInz6obpgDQGcFmaJgB", # Adam (Clear, authoritative)
    "dramatic": "JBFqnCBsd6RMkjVDRZzb",    # George (British, warm storyteller)
    "comedic": "FGY2WhTYpPnrIDTdsKH5",     # Laura (Sassy, enthusiastic)
    "social_media": "FGY2WhTYpPnrIDTdsKH5",# Laura
    "narrative": "EXAVITQu4vr4xnSDxMaL",   # Sarah (Mature, reassuring)
    "conversational": "CwhRBWXzGAHq8TQ4Fs17", # Roger (Laid-back)
    "energetic": "IKne3meq5aSn9XLyUdCD",   # Charlie (Hyped, energetic)
    "hindi": "x9wViLHrpGxKBhkUybpR",       # Aarav R (Deep Indian Hindi)
}

EDGE_VOICE_MAP = {
    "hindi": "hi-IN-MadhurNeural",         # Native Hindi male voice for Edge TTS
}


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class TTSGenerationError(Exception):
    """Raised for any failure during TTS synthesis.  Never exposes credentials."""


# ---------------------------------------------------------------------------
# TTSGenerator
# ---------------------------------------------------------------------------

class TTSGenerator:
    """Converts scene narration text to MP3 audio using ElevenLabs or Edge TTS."""

    def __init__(self):
        self._el_client: AsyncElevenLabs | None = None
        if settings.elevenlabs_api_key:
            self._el_client = AsyncElevenLabs(api_key=settings.elevenlabs_api_key)

    async def generate_scene_audio(
        self,
        job_id: str,
        scene_id: int,
        text: str,
        voice: str = DEFAULT_EDGE_VOICE,
        style: str = "educational",
    ) -> str:
        """
        Synthesise `text` to speech and save the result as an MP3.

        Parameters
        ----------
        job_id   : Unique job identifier (used to namespace the file name).
        scene_id : Scene number within the job.
        text     : Narration text from ContentPlan.scenes[n].narration.
        voice    : Edge TTS voice name (default: en-US-ChristopherNeural).
                   (ElevenLabs voice is configured via settings).

        Returns
        -------
        str — Absolute path to the saved MP3 file.

        Raises
        ------
        TTSGenerationError — on empty text, or if both primary and fallback fail.
        """
        if not text or not text.strip():
            raise TTSGenerationError(
                f"narration text for scene {scene_id} must not be empty."
            )

        logger.info(
            "Synthesising audio: job=%s scene=%d chars=%d",
            job_id, scene_id, len(text),
        )

        # Ensure output directory exists.
        TEMP_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

        output_path = TEMP_ASSETS_DIR / f"{job_id}_scene_{scene_id}.mp3"

        # Try ElevenLabs first if configured
        if self._el_client:
            # Pick best voice based on style, fallback to default config
            selected_voice = ELEVENLABS_VOICE_MAP.get(style.lower(), settings.elevenlabs_voice_id)
            
            logger.info("Attempting ElevenLabs TTS for scene %d (style: %s, voice: %s)...", scene_id, style, selected_voice)
            try:
                audio_stream = self._el_client.text_to_speech.convert(
                    text=text,
                    voice_id=selected_voice,
                    model_id=settings.elevenlabs_model_id,
                    output_format="mp3_44100_128",
                )
                
                with open(output_path, "wb") as f:
                    async for chunk in audio_stream:
                        if chunk:
                            f.write(chunk)
                
                logger.info("ElevenLabs audio saved: %s", output_path)
                return str(output_path.resolve())
            except Exception as exc:
                logger.warning(
                    "ElevenLabs TTS failed for scene %d, falling back to edge-tts: %s",
                    scene_id, type(exc).__name__
                )

        # Fallback to Edge TTS
        fallback_voice = EDGE_VOICE_MAP.get(style.lower(), voice)
        logger.info("Using Edge TTS for scene %d (voice=%s)...", scene_id, fallback_voice)
        try:
            communicate = edge_tts.Communicate(text, fallback_voice)
            await communicate.save(str(output_path))
        except TTSGenerationError:
            raise  # never swallow our own errors
        except Exception as exc:
            raise TTSGenerationError(
                f"Edge TTS failed for scene {scene_id}: {type(exc).__name__}: {exc}"
            ) from exc

        logger.info("Edge TTS audio saved: %s", output_path)
        return str(output_path.resolve())


# Module-level singleton
tts_generator = TTSGenerator()
