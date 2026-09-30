import os
import shutil
from fastapi import APIRouter
from app.core.config import settings

router = APIRouter()

def _check_ffmpeg() -> bool:
    if shutil.which("ffmpeg"):
        return True
    try:
        import imageio_ffmpeg
        return bool(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        return False

@router.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "qoneqt-contentos-backend",
        "version": "1.0.0",
        "dependencies": {
            "ffmpeg": _check_ffmpeg(),
            "gemini_configured": bool(settings.gemini_api_key),
            "huggingface_configured": bool(settings.hf_token or os.getenv("HF_TOKEN")),
            "elevenlabs_configured": bool(settings.elevenlabs_api_key),
            "s3_configured": bool(settings.s3_bucket_name),
        }
    }
