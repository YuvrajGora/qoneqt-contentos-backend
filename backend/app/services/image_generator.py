"""
ImageGenerator service — Milestone 3 (Updated).

Uses Hugging Face Inference API (FLUX.1-schnell) to generate images from visual prompts
produced by the ContentPlanner.

Architecture notes
------------------
* Temporary assets are written to temp_assets/{job_id}_scene_{scene_id}.png
  relative to the backend root.  The caller is responsible for clean-up.

Downstream pipeline
-------------------
  scene.visual_prompt  →  ImageGenerator.generate_scene_image()
                       →  PNG file path
                       →  Milestone 5: FFmpeg compositor reads the file
"""

import logging
from pathlib import Path
import os
import time

from huggingface_hub import InferenceClient

from app.core.config import settings

logger = logging.getLogger(__name__)

# Resolved once at module load so tests can patch it easily.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
TEMP_ASSETS_DIR = _BACKEND_ROOT / "temp_assets"


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class ImageGenerationError(Exception):
    """Raised for any failure during image generation."""


# ---------------------------------------------------------------------------
# ImageGenerator
# ---------------------------------------------------------------------------

class ImageGenerator:
    """Generates individual scene images and persists them as PNG files."""

    def generate_scene_image(self, job_id: str, scene_id: int, prompt: str) -> str:
        """
        Generate a 9:16 vertical image from `prompt` and save it locally.

        Parameters
        ----------
        job_id   : Unique job identifier (used to namespace the file name).
        scene_id : Scene number within the job.
        prompt   : Rich visual-generation prompt from ContentPlan.scenes[n].visual_prompt.

        Returns
        -------
        str — Absolute path to the saved PNG file.

        Raises
        ------
        ImageGenerationError — on any network or I/O failure.
        """
        if not prompt or not prompt.strip():
            raise ImageGenerationError("visual_prompt must not be empty.")

        hf_token = settings.hf_token or os.getenv("HF_TOKEN")
        if not hf_token:
            raise ImageGenerationError(
                "HF_TOKEN is not configured. Set it in your .env file or as an environment variable."
            )

        logger.info(
            "Generating scene image (Hugging Face): job=%s scene=%d",
            job_id, scene_id
        )

        client = InferenceClient(api_key=hf_token)
        
        # Ensure output directory exists.
        TEMP_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = TEMP_ASSETS_DIR / f"{job_id}_scene_{scene_id}.png"

        for attempt in range(3):
            try:
                image = client.text_to_image(
                    prompt=prompt,
                    model="black-forest-labs/FLUX.1-schnell"
                )
                image.save(str(output_path))
                break  # Success, exit loop
            except Exception as exc:
                if attempt < 2:
                    logger.warning("Hugging Face API overloaded/warming up. Retrying (attempt %d/3)...", attempt + 2)
                    time.sleep(5)
                else:
                    raise ImageGenerationError(
                        f"Hugging Face image generation failed for scene {scene_id} after 3 attempts: {type(exc).__name__}: {exc}"
                    ) from exc

        logger.info("Scene image saved: %s", output_path)
        return str(output_path.resolve())


# Module-level singleton
image_generator = ImageGenerator()
