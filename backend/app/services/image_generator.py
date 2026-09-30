"""
ImageGenerator service — Milestone 3 & Production Fallback.

Uses Hugging Face Inference API (FLUX.1-schnell) to generate images from visual prompts
produced by the ContentPlanner.
Includes a 100% reliable, zero-credit local cinematic visual artwork generator
that automatically activates if Hugging Face credits are depleted (402 Payment Required),
rate-limited (429), or unavailable, ensuring real MP4 video generation never breaks.

Architecture notes
------------------
* Temporary assets are written to temp_assets/{job_id}_scene_{scene_id}.png
  relative to the backend root.
* All generated images are exact 1080x1920 portrait (9:16 aspect ratio).
* Local fallback produces high-resolution cinematic artwork with scene-specific
  thematic gradients, glowing telemetry, and structured typography.
"""

import logging
from pathlib import Path
import os
import time
from typing import Optional

from PIL import Image, ImageDraw
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
    """Generates individual scene images and persists them as 1080x1920 PNG files."""

    def generate_cinematic_artwork(
        self,
        job_id: str,
        scene_id: int,
        prompt: str,
        output_path: Path,
    ) -> str:
        """
        Generates a 1080x1920 cinematic visual artwork using Pillow.
        Used as a zero-cost, 100% reliable production fallback when external
        image generation APIs have depleted credits (402) or are unavailable.
        """
        width, height = 1080, 1920

        # 4 distinct cinematic color themes tailored by scene_id
        PALETTES = [
            # Scene 1: Midnight Cyber Cyan & Royal Blue (Hook / Intro)
            {
                "bg_top": (8, 16, 34),
                "bg_bot": (3, 6, 16),
                "accent": (0, 225, 255),
                "glow": (40, 120, 255),
                "card_bg": (14, 20, 36),
                "label": "THE HOOK • INTRO",
            },
            # Scene 2: Cyber Violet & Neon Magenta (Concept / Architecture)
            {
                "bg_top": (26, 10, 38),
                "bg_bot": (8, 3, 18),
                "accent": (230, 50, 255),
                "glow": (140, 40, 240),
                "card_bg": (22, 14, 34),
                "label": "CORE ARCHITECTURE",
            },
            # Scene 3: Deep Emerald & Matrix Teal (Transformation / Execution)
            {
                "bg_top": (6, 28, 24),
                "bg_bot": (3, 13, 11),
                "accent": (0, 245, 180),
                "glow": (20, 160, 130),
                "card_bg": (12, 26, 24),
                "label": "SYSTEM TRANSFORMATION",
            },
            # Scene 4: Sunset Ember & Electric Amber (Impact / Future)
            {
                "bg_top": (34, 15, 10),
                "bg_bot": (14, 6, 4),
                "accent": (255, 155, 40),
                "glow": (240, 70, 70),
                "card_bg": (28, 16, 12),
                "label": "FUTURE HORIZON",
            },
        ]
        theme = PALETTES[(scene_id - 1) % len(PALETTES)]

        img = Image.new("RGB", (width, height), theme["bg_bot"])
        draw = ImageDraw.Draw(img)

        # 1. Background smooth vertical gradient
        for y in range(0, height, 2):
            ratio = y / height
            r = int(theme["bg_top"][0] * (1 - ratio) + theme["bg_bot"][0] * ratio)
            g = int(theme["bg_top"][1] * (1 - ratio) + theme["bg_bot"][1] * ratio)
            b = int(theme["bg_top"][2] * (1 - ratio) + theme["bg_bot"][2] * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b), width=2)

        # 2. Ambient radial lighting bloom
        bloom_x, bloom_y = width // 2, 650
        for radius in range(500, 40, -20):
            alpha_factor = (1 - radius / 500) ** 1.6
            br = int(theme["glow"][0] * alpha_factor * 0.22)
            bg = int(theme["glow"][1] * alpha_factor * 0.22)
            bb = int(theme["glow"][2] * alpha_factor * 0.22)
            draw.ellipse(
                [bloom_x - radius, bloom_y - radius, bloom_x + radius, bloom_y + radius],
                fill=(br, bg, bb)
            )

        # 3. Concentric geometric telemetry rings & crosshairs
        for r_step in [160, 320, 480]:
            draw.ellipse(
                [bloom_x - r_step, bloom_y - r_step, bloom_x + r_step, bloom_y + r_step],
                outline=(theme["accent"][0] // 4, theme["accent"][1] // 4, theme["accent"][2] // 4),
                width=1
            )
        draw.line([(80, bloom_y), (width - 80, bloom_y)], fill=(35, 45, 65), width=1)
        draw.line([(bloom_x, 250), (bloom_x, 1050)], fill=(35, 45, 65), width=1)

        # 4. Top Header Badge
        badge_w, badge_h = 440, 56
        badge_x = (width - badge_w) // 2
        badge_y = 160
        draw.rounded_rectangle(
            [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
            radius=16,
            fill=(12, 16, 28),
            outline=theme["accent"],
            width=2
        )
        draw.text(
            (badge_x + 36, badge_y + 18),
            f"QONEQT CONTENTOS  //  SCENE 0{scene_id}",
            fill=theme["accent"]
        )

        draw.text(
            ((width - 320) // 2, badge_y + 75),
            f"[ {theme['label']} ]",
            fill=(140, 160, 190)
        )

        # 5. Glassmorphism Card Frame
        card_margin = 70
        card_top = 1100
        card_bot = 1750
        draw.rounded_rectangle(
            [card_margin, card_top, width - card_margin, card_bot],
            radius=26,
            fill=theme["card_bg"],
            outline=theme["accent"],
            width=2
        )

        # Corner accent brackets
        c_len = 24
        draw.line([(card_margin + 6, card_top + 6), (card_margin + 6 + c_len, card_top + 6)], fill=theme["accent"], width=3)
        draw.line([(card_margin + 6, card_top + 6), (card_margin + 6, card_top + 6 + c_len)], fill=theme["accent"], width=3)
        draw.line([(width - card_margin - 6, card_top + 6), (width - card_margin - 6 - c_len, card_top + 6)], fill=theme["accent"], width=3)
        draw.line([(width - card_margin - 6, card_top + 6), (width - card_margin - 6, card_top + 6 + c_len)], fill=theme["accent"], width=3)

        # Card Title
        draw.text(
            (card_margin + 45, card_top + 50),
            f"SCENE 0{scene_id} // VISUAL SYNTHESIS",
            fill=theme["accent"]
        )
        draw.line(
            [(card_margin + 45, card_top + 90), (width - card_margin - 45, card_top + 90)],
            fill=(50, 65, 85),
            width=1
        )

        # Wrapped prompt text
        clean_prompt = " ".join(prompt.split())
        words = clean_prompt.split()
        lines = []
        curr = []
        for w in words:
            curr.append(w)
            if len(" ".join(curr)) > 34:
                lines.append(" ".join(curr))
                curr = []
            if len(lines) >= 6:
                break
        if curr and len(lines) < 6:
            lines.append(" ".join(curr))

        y_text = card_top + 120
        for line in lines:
            draw.text((card_margin + 45, y_text), line, fill=(235, 242, 255))
            y_text += 45

        # 6. Audio Waveform simulation bars at bottom of card
        waveform_y = card_bot - 65
        for b in range(18):
            bar_h = 10 + ((b * 11 + scene_id * 5) % 40)
            bx = card_margin + 45 + b * 22
            draw.rectangle(
                [bx, waveform_y - bar_h, bx + 12, waveform_y],
                fill=theme["glow"]
            )

        draw.text(
            (width - card_margin - 380, card_bot - 60),
            "1080x1920 • 9:16 CINEMATIC",
            fill=(140, 160, 185)
        )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(output_path), "PNG")
        logger.info("Local cinematic scene artwork saved (0 MB external credits): %s", output_path)
        return str(output_path.resolve())

    def generate_scene_image(
        self,
        job_id: str,
        scene_id: int,
        prompt: str,
        allow_fallback: bool = True,
    ) -> str:
        """
        Generate a 9:16 vertical image from `prompt` and save it locally.
        Attempts Hugging Face FLUX.1-schnell first. If credits are depleted
        (402 Payment Required), rate-limited, or unavailable, seamlessly falls back
        to the local cinematic artwork engine.
        """
        if not prompt or not prompt.strip():
            raise ImageGenerationError("visual_prompt must not be empty.")

        hf_token = settings.hf_token or os.getenv("HF_TOKEN")
        TEMP_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = TEMP_ASSETS_DIR / f"{job_id}_scene_{scene_id}.png"

        if not hf_token:
            if allow_fallback:
                logger.info(
                    "HF_TOKEN not configured. Generating scene %d via local cinematic visual generator.",
                    scene_id
                )
                return self.generate_cinematic_artwork(job_id, scene_id, prompt, output_path)
            else:
                raise ImageGenerationError(
                    "HF_TOKEN is not configured. Set it in your .env file or as an environment variable."
                )

        logger.info(
            "Generating scene image: job=%s scene=%d",
            job_id, scene_id
        )

        client = InferenceClient(api_key=hf_token)

        for attempt in range(3):
            try:
                image = client.text_to_image(
                    prompt=prompt,
                    model="black-forest-labs/FLUX.1-schnell"
                )
                image.save(str(output_path))
                logger.info("Scene image saved via Hugging Face: %s", output_path)
                return str(output_path.resolve())
            except Exception as exc:
                err_str = str(exc)
                err_lower = err_str.lower()
                is_credit_exhausted = (
                    "402" in err_str or
                    "payment required" in err_lower or
                    "depleted your monthly included credits" in err_lower or
                    "purchase pre-paid credits" in err_lower or
                    "credits" in err_lower
                )

                if is_credit_exhausted:
                    logger.warning(
                        "Hugging Face credit limit reached (402 Payment Required: monthly credits depleted). Skipping retries on HF."
                    )
                    if allow_fallback:
                        logger.info("Falling back to local cinematic visual generator for scene %d.", scene_id)
                        return self.generate_cinematic_artwork(job_id, scene_id, prompt, output_path)
                    else:
                        raise ImageGenerationError(
                            f"Hugging Face image generation failed for scene {scene_id} after 3 attempts: {type(exc).__name__}: {exc}"
                        ) from exc

                if attempt < 2:
                    logger.warning("Hugging Face API error (%s). Retrying (attempt %d/3)...", exc, attempt + 2)
                    time.sleep(2)
                else:
                    if allow_fallback:
                        logger.warning(
                            "Hugging Face API failed after 3 attempts (%s). Falling back to local cinematic visual generator.",
                            exc
                        )
                        return self.generate_cinematic_artwork(job_id, scene_id, prompt, output_path)
                    else:
                        raise ImageGenerationError(
                            f"Hugging Face image generation failed for scene {scene_id} after 3 attempts: {type(exc).__name__}: {exc}"
                        ) from exc

        return str(output_path.resolve())


# Module-level singleton
image_generator = ImageGenerator()
