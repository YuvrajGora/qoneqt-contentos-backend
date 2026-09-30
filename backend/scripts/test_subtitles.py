"""
Smoke test for TranscriptionService (Subtitles).

Generates dummy assets, generates audio via TTS, uses faster-whisper to transcribe and format an SRT,
then uses FFmpeg to burn the subtitles into the MP4.
"""

import asyncio
from pathlib import Path

from PIL import Image

from app.services.tts_generator import tts_generator
from app.services.transcription_service import transcription_service
from app.services.video_compositor import video_compositor
from app.services.image_generator import TEMP_ASSETS_DIR

def create_dummy_image(path: str, color: str):
    """Creates a 1080x1920 solid color image."""
    img = Image.new("RGB", (1080, 1920), color=color)
    img.save(path)

async def main():
    print("Preparing dummy assets for subtitle smoke test...")
    TEMP_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    
    job_id = "smoke_subtitles"
    
    # Dummy Image (Blue)
    img_path = str((TEMP_ASSETS_DIR / f"{job_id}_img1.jpg").resolve())
    create_dummy_image(img_path, "blue")
    
    # Audio
    text = "This is a test of the fast whisper subtitle system for our hackathon project."
    print(f"Synthesising audio for: '{text}'...")
    aud_path = await tts_generator.generate_scene_audio(job_id, 1, text)
    
    # SRT
    print("Transcribing and generating SRT...")
    srt_path = transcription_service.generate_scene_srt(job_id, 1, aud_path)
    print(f"SRT saved to: {srt_path}")
    
    # Compose
    scenes = [
        {"scene_id": 1, "image_path": img_path, "audio_path": aud_path, "srt_path": srt_path},
    ]
    
    print("Building final video with burnt-in captions...")
    final_mp4 = video_compositor.build_video_from_assets(job_id, scenes)
    
    final_size = Path(final_mp4).stat().st_size
    
    print("\n=================================")
    if final_size > 0:
        print(f"[OK] Video with subtitles successfully generated!")
        print(f"Path: {final_mp4}")
        print(f"Size: {final_size / 1024:.2f} KB")
        try:
            from mutagen.mp4 import MP4
            audio = MP4(final_mp4)
            print(f"Duration: {audio.info.length:.2f} seconds")
        except Exception as e:
            pass
    else:
        print("[FAIL] Output MP4 is empty (0 bytes).")
    print("=================================\n")

if __name__ == "__main__":
    asyncio.run(main())
