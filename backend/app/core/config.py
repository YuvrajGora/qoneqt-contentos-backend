from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    base_url: str = "http://localhost:8000"
    frontend_origin: str | None = None

    # Milestone 2: Groq — scripting / content planning fallback
    groq_api_key: str = ""
    groq_model: str = "qwen/qwen3.8-27b"

    hf_token: str | None = None
    # Milestone 3 & 11: Google AI Studio / Gemini — visual & content generation
    gemini_api_key: str = ""
    gemini_text_model: str = "gemini-3.5-flash-lite"
    gemini_image_model: str = "gemini-3.1-flash-image"
    # gemini_video_model: str = ""  # reserved for Milestone 5 video generation

    # Milestone 4: ElevenLabs — TTS voiceover
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "pNInz6obpgDQGcFmaJgB"
    elevenlabs_model_id: str = "eleven_multilingual_v2"

    # Milestone 9: Cloud Storage (optional)
    s3_bucket_name: str | None = None
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_region: str | None = None
    s3_endpoint_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=(_BACKEND_DIR / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
