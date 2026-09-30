"""
Smoke test for VideoCompositor.

Generates dummy images (via PIL) and dummy MP3 files (via edge-tts fallback or a simple copy of a short audio),
then runs VideoCompositor.build_video_from_assets to produce a real MP4 on disk.
"""

import asyncio
from pathlib import Path

from PIL import Image

from app.services.tts_generator import tts_generator
from app.services.video_compositor import video_compositor
from app.services.image_generator import TEMP_ASSETS_DIR

def create_dummy_image(path: str, color: str):
    """Creates a 1080x1920 solid color image."""
    img = Image.new("RGB", (1080, 1920), color=color)
    img.save(path)

async def main():
    print("Preparing dummy assets for video composition...")
    TEMP_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    
    job_id = "smoke_video"
    
    # Dummy Image 1 (Red)
    img1_path = str((TEMP_ASSETS_DIR / f"{job_id}_img1.jpg").resolve())
    create_dummy_image(img1_path, "red")
    
    # Dummy Image 2 (Blue)
    img2_path = str((TEMP_ASSETS_DIR / f"{job_id}_img2.jpg").resolve())
    create_dummy_image(img2_path, "blue")
    
    # Dummy Audio 1
    # We will use our tts_generator (edge-tts fallback) to generate real MP3s so FFmpeg has valid audio streams.
    print("Synthesising dummy audio 1...")
    aud1_path = await tts_generator.generate_scene_audio(job_id, 1, "This is the first test scene.")
    
    # Dummy Audio 2
    print("Synthesising dummy audio 2...")
    aud2_path = await tts_generator.generate_scene_audio(job_id, 2, "And this is the second scene for our video composition smoke test.")
    
    scenes = [
        {"scene_id": 1, "image_path": img1_path, "audio_path": aud1_path},
        {"scene_id": 2, "image_path": img2_path, "audio_path": aud2_path},
    ]
    
    print("Building video...")
    final_mp4 = video_compositor.build_video_from_assets(job_id, scenes)
    
    final_size = Path(final_mp4).stat().st_size
    
    print("\n=================================")
    if final_size > 0:
        print(f"[OK] Video successfully generated!")
        print(f"Path: {final_mp4}")
        print(f"Size: {final_size / 1024:.2f} KB")
        # We could use mutagen to check duration, but file size > 0 implies FFmpeg ran successfully.
        
        try:
            from mutagen.mp4 import MP4
            audio = MP4(final_mp4)
            print(f"Duration: {audio.info.length:.2f} seconds")
        except Exception as e:
            print(f"Could not read duration with mutagen: {e}")
    else:
        print("[FAIL] Output MP4 is empty (0 bytes).")
    print("=================================\n")

if __name__ == "__main__":
    asyncio.run(main())
