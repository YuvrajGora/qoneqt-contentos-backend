"""
Video Compositor service — Milestone 5.

Assembles scene clips from generated 9:16 images and TTS audio using FFmpeg.
Provides concatenation to combine individual scene clips into a final MP4.

Relies on `imageio_ffmpeg` for a bundled cross-platform FFmpeg executable.
"""

import logging
import os
import re
import subprocess
from pathlib import Path

import imageio_ffmpeg

from app.services.image_generator import TEMP_ASSETS_DIR

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------

class VideoCompositionError(Exception):
    """Raised for any failure during video assembly (FFmpeg errors, missing files, etc)."""


# ---------------------------------------------------------------------------
# VideoCompositor
# ---------------------------------------------------------------------------

class VideoCompositor:
    """Assembles final MP4 videos from individual scene assets."""

    def __init__(self):
        try:
            self._ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as exc:
            raise VideoCompositionError(f"Failed to locate FFmpeg executable: {exc}") from exc

    def get_media_duration(self, file_path: str) -> float:
        """Extract media duration in seconds using FFmpeg stderr."""
        if not file_path or not Path(file_path).exists():
            return 0.0
        try:
            cmd = [self._ffmpeg_path, "-i", str(file_path)]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", p.stderr)
            if m:
                h, mn, s = map(float, m.groups())
                return h * 3600.0 + mn * 60.0 + s
        except Exception as exc:
            logger.warning("Could not read duration for %s: %s", file_path, exc)
        return 0.0

    def compose_scene_clip(
        self,
        image_path: str,
        audio_path: str,
        output_clip_path: str,
        srt_path: str = None,
        target_duration: float = None
    ) -> str:
        """
        Executes FFmpeg to render a single 9:16 vertical clip from an image and audio file.
        
        Parameters
        ----------
        image_path       : Absolute path to the scene image.
        audio_path       : Absolute path to the scene audio.
        output_clip_path : Absolute path where the scene MP4 should be saved.
        srt_path         : Optional absolute path to an SRT file for subtitles.
        target_duration  : Optional target scene duration in seconds to prevent premature truncation.
        
        Returns
        -------
        str — The absolute path to the rendered scene clip.
        """
        if not Path(image_path).exists():
            raise VideoCompositionError(f"Image file not found: {image_path}")
        if not Path(audio_path).exists():
            raise VideoCompositionError(f"Audio file not found: {audio_path}")
        if srt_path and not Path(srt_path).exists():
            raise VideoCompositionError(f"SRT file not found: {srt_path}")

        logger.info("Composing scene clip: %s (target_duration=%s)", output_clip_path, target_duration)

        cwd = os.path.dirname(image_path)
        img_base = os.path.basename(image_path)
        aud_base = os.path.basename(audio_path)
        out_base = os.path.basename(output_clip_path)
        
        vf_string = "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"
        if srt_path:
            srt_base = os.path.basename(srt_path)
            vf_string += f",subtitles={srt_base}:force_style='Fontname=Arial,Fontsize=24,PrimaryColour=&H00FFFF,Outline=1,Alignment=2,MarginV=150'"

        cmd = [
            self._ffmpeg_path,
            "-y",  # overwrite output if exists
            "-loop", "1",
            "-i", img_base,
            "-i", aud_base,
            "-vf", vf_string,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-threads", "2",
            "-max_muxing_queue_size", "1024",
            "-tune", "stillimage",
            "-pix_fmt", "yuv420p",
            "-r", "30",
        ]

        if target_duration is not None and float(target_duration) > 0:
            audio_dur = self.get_media_duration(audio_path)
            clip_dur = max(audio_dur, float(target_duration))
            cmd.extend([
                "-af", "apad",
                "-t", f"{clip_dur:.2f}",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                out_base
            ])
        else:
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",  # end clip when audio ends
                "-movflags", "+faststart",
                out_base
            ])

        try:
            result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True, timeout=120)
            import gc
            gc.collect()
        except subprocess.TimeoutExpired as exc:
            logger.error("FFmpeg scene clip composition timed out: %s", exc)
            raise VideoCompositionError(f"FFmpeg timed out rendering scene clip after 120 seconds: {exc}") from exc
        except subprocess.CalledProcessError as exc:
            logger.error("FFmpeg failed: %s", exc.stderr)
            raise VideoCompositionError(f"FFmpeg failed to compose scene clip: {exc.stderr}") from exc

        return output_clip_path

    def concatenate_scenes(self, job_id: str, scene_clip_paths: list[str]) -> str:
        """
        Concatenates multiple scene MP4 clips into a single final MP4 video.
        
        Parameters
        ----------
        job_id           : Unique job identifier for the video.
        scene_clip_paths : List of absolute paths to individual scene clips in order.
        
        Returns
        -------
        str — The absolute path to the concatenated final MP4.
        """
        if not scene_clip_paths:
            raise VideoCompositionError("No scene clips provided for concatenation.")

        for clip_path in scene_clip_paths:
            if not Path(clip_path).exists():
                raise VideoCompositionError(f"Scene clip not found: {clip_path}")

        # Ensure output directory exists
        TEMP_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

        concat_list_path = TEMP_ASSETS_DIR / f"{job_id}_concat.txt"
        final_mp4_path = TEMP_ASSETS_DIR / f"{job_id}_final.mp4"

        logger.info("Concatenating %d scenes to %s", len(scene_clip_paths), final_mp4_path)

        # Write FFmpeg concat manifest
        try:
            with open(concat_list_path, "w", encoding="utf-8") as f:
                for clip_path in scene_clip_paths:
                    # FFmpeg requires escaping single quotes in paths, but since we control temp_assets
                    # we just format it as file 'path' with forward slashes for cross-platform compatibility.
                    safe_path = Path(clip_path).as_posix()
                    f.write(f"file '{safe_path}'\n")
        except IOError as exc:
            raise VideoCompositionError(f"Failed to write concat manifest: {exc}") from exc

        cmd = [
            self._ffmpeg_path,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list_path),
            "-c", "copy",
            str(final_mp4_path)
        ]

        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=180)
            import gc
            gc.collect()
        except subprocess.TimeoutExpired as exc:
            logger.error("FFmpeg concat timed out: %s", exc)
            raise VideoCompositionError(f"FFmpeg timed out concatenating scenes after 180 seconds: {exc}") from exc
        except subprocess.CalledProcessError as exc:
            logger.error("FFmpeg concat failed: %s", exc.stderr)
            raise VideoCompositionError(f"FFmpeg failed to concatenate scenes: {exc.stderr}") from exc
        finally:
            # Clean up the manifest
            if concat_list_path.exists():
                try:
                    concat_list_path.unlink()
                except OSError as e:
                    logger.warning("Could not remove concat manifest %s: %s", concat_list_path, e)

        return str(final_mp4_path.resolve())

    def build_video_from_assets(self, job_id: str, scenes: list[dict], requested_duration: float = None) -> str:
        """
        End-to-end composition of a full video from a list of scene asset dictionaries.
        
        Parameters
        ----------
        job_id             : Unique identifier for the video job.
        scenes             : List of dicts, e.g. [{"scene_id": int, "image_path": str, "audio_path": str, ...}, ...]
        requested_duration : Optional target duration in seconds for validation.
        
        Returns
        -------
        str — The absolute path to the final assembled MP4.
        """
        if not scenes:
            raise VideoCompositionError("No scenes provided to build video.")

        TEMP_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        
        scene_clip_paths = []

        # Sort scenes by scene_id to ensure strict ordering
        try:
            sorted_scenes = sorted(scenes, key=lambda s: s["scene_id"])
        except KeyError as exc:
            raise VideoCompositionError(f"Missing required key in scene dict: {exc}") from exc

        for scene in sorted_scenes:
            scene_id = scene["scene_id"]
            image_path = scene["image_path"]
            audio_path = scene["audio_path"]
            srt_path = scene.get("srt_path")
            target_dur = scene.get("target_duration") or scene.get("duration")
            
            output_clip_path = str((TEMP_ASSETS_DIR / f"{job_id}_scene_{scene_id}.mp4").resolve())
            
            self.compose_scene_clip(image_path, audio_path, output_clip_path, srt_path, target_duration=target_dur)
            scene_clip_paths.append(output_clip_path)
            
        final_mp4_path = self.concatenate_scenes(job_id, scene_clip_paths)

        # Validate final duration
        actual_dur = self.get_media_duration(final_mp4_path)
        logger.info("Assembled final MP4 for %s: duration=%.2fs", job_id, actual_dur)
        if requested_duration and actual_dur > 0:
            diff_ratio = abs(actual_dur - requested_duration) / requested_duration
            if diff_ratio > 0.20:
                logger.warning(
                    "DURATION MISMATCH: Requested %ds, but final video is %.2fs (%.1f%% difference).",
                    requested_duration,
                    actual_dur,
                    diff_ratio * 100
                )
        return final_mp4_path



# Module-level singleton
video_compositor = VideoCompositor()
