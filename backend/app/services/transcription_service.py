"""
Transcription Service — Milestone 6.

Uses faster-whisper to extract word-level timestamps and generate short, punchy SRT files.
"""

import logging
from pathlib import Path

from faster_whisper import WhisperModel
from app.services.image_generator import TEMP_ASSETS_DIR

logger = logging.getLogger(__name__)

class TranscriptionError(Exception):
    """Raised for any failure during transcription or SRT generation."""

def format_timestamp(seconds: float) -> str:
    """Formats a time in seconds to SRT strict format HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    # If ms rounds to 1000, we could roll over, but for rough precision this is fine.
    # We will handle it by just keeping ms constrained.
    if ms >= 1000:
        secs += ms // 1000
        ms = ms % 1000
        if secs >= 60:
            minutes += secs // 60
            secs = secs % 60
            if minutes >= 60:
                hours += minutes // 60
                minutes = minutes % 60
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

class TranscriptionService:
    def __init__(self):
        self._model = None

    @property
    def model(self):
        if self._model is None:
            try:
                # Lazy-load tiny.en on demand only if needed
                self._model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
            except Exception as exc:
                raise TranscriptionError(f"Failed to initialize WhisperModel: {exc}") from exc
        return self._model

    def _get_audio_duration(self, audio_path: str) -> float:
        """Lightweight duration extraction without loading audio models (0 MB RAM)."""
        try:
            from mutagen.mp3 import MP3
            audio = MP3(audio_path)
            return float(audio.info.length)
        except Exception:
            pass
        try:
            from app.services.video_compositor import video_compositor
            return float(video_compositor.get_media_duration(audio_path))
        except Exception:
            return 0.0

    def generate_timed_srt_from_script(
        self,
        job_id: str,
        scene_id: int,
        narration: str,
        audio_duration: float,
        chunk_word_count: int = 3,
    ) -> str:
        """
        Generates a synchronized SRT subtitle file from narration text and audio duration.
        Consumes 0 MB RAM, avoids loading CTranslate2/Whisper, and executes in <1ms.
        """
        words = [w.strip() for w in narration.split() if w.strip()]
        if not words:
            words = ["..."]

        TEMP_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        srt_path = TEMP_ASSETS_DIR / f"{job_id}_scene_{scene_id}.srt"

        # Chunk into groups of 3 words (matches standard short-form caption density)
        chunks = []
        for i in range(0, len(words), chunk_word_count):
            chunks.append(words[i : i + chunk_word_count])

        total_chunks = len(chunks)
        chunk_duration = audio_duration / max(1, total_chunks)

        try:
            with open(srt_path, "w", encoding="utf-8") as f:
                for idx, chunk in enumerate(chunks, start=1):
                    start_sec = (idx - 1) * chunk_duration
                    end_sec = min(audio_duration, idx * chunk_duration)
                    f.write(f"{idx}\n")
                    f.write(f"{format_timestamp(start_sec)} --> {format_timestamp(end_sec)}\n")
                    f.write(f"{' '.join(chunk)}\n\n")
        except IOError as exc:
            raise TranscriptionError(f"Failed to write SRT file: {exc}") from exc

        logger.info(
            "Lightweight SRT generated (0 MB RAM): %s (%d chunks, %.2fs duration)",
            srt_path,
            total_chunks,
            audio_duration,
        )
        return str(srt_path.resolve())

    def generate_scene_srt(
        self,
        job_id: str,
        scene_id: int,
        audio_path: str,
        narration: str = None,
        duration: float = None,
    ) -> str:
        """
        Transcribes the audio file and writes an SRT subtitle file.
        Uses lightweight proportional timing if narration is provided (0 MB RAM).
        Falls back to faster-whisper only if narration is absent.
        """
        if not Path(audio_path).exists():
            raise TranscriptionError(f"Audio file not found: {audio_path}")

        # Production path: If narration text is available, generate SRT from script & audio duration.
        # This completely avoids loading the ~250MB faster-whisper model into process memory!
        if narration and narration.strip():
            audio_dur = duration if (duration and duration > 0) else self._get_audio_duration(audio_path)
            if audio_dur > 0:
                return self.generate_timed_srt_from_script(
                    job_id=job_id,
                    scene_id=scene_id,
                    narration=narration,
                    audio_duration=audio_dur,
                )

        # Fallback path: faster-whisper model transcription
        logger.info("Transcribing audio with faster-whisper for scene %d...", scene_id)
        
        try:
            segments, info = self.model.transcribe(audio_path, word_timestamps=True)
        except Exception as exc:
            raise TranscriptionError(f"faster-whisper failed to transcribe: {exc}") from exc

        TEMP_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        srt_path = TEMP_ASSETS_DIR / f"{job_id}_scene_{scene_id}.srt"
        
        try:
            with open(srt_path, "w", encoding="utf-8") as f:
                idx = 1
                for segment in segments:
                    if not segment.words:
                        continue
                    
                    chunk = []
                    chunk_start = None
                    chunk_end = None
                    
                    for i, word in enumerate(segment.words):
                        if not chunk:
                            chunk_start = word.start
                        chunk.append(word.word.strip())
                        chunk_end = word.end
                        
                        # Chunk size of 3
                        if len(chunk) >= 3 or i == len(segment.words) - 1:
                            f.write(f"{idx}\n")
                            f.write(f"{format_timestamp(chunk_start)} --> {format_timestamp(chunk_end)}\n")
                            f.write(f"{' '.join(chunk)}\n\n")
                            idx += 1
                            chunk = []
                            chunk_start = None
                            chunk_end = None
                            
        except IOError as exc:
            raise TranscriptionError(f"Failed to write SRT file: {exc}") from exc

        logger.info("SRT generated: %s", srt_path)
        return str(srt_path.resolve())

# Module-level singleton
transcription_service = TranscriptionService()
