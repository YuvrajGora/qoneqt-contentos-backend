"""
Unit tests for TTSGenerator (ElevenLabs + Edge TTS).

ALL tests are fully mocked — no network calls, no API key required.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_edge_tts(tmp_path):
    """Patch edge_tts.Communicate and TEMP_ASSETS_DIR."""
    async def _fake_save(output_path: str):
        Path(output_path).write_bytes(b"ID3FAKEMP3DATA")

    mock_communicate_instance = MagicMock()
    mock_communicate_instance.save = _fake_save

    with patch("app.services.tts_generator.edge_tts") as mock_edge_tts_mod, \
         patch("app.services.tts_generator.TEMP_ASSETS_DIR", tmp_path):
        mock_edge_tts_mod.Communicate.return_value = mock_communicate_instance
        yield mock_edge_tts_mod, tmp_path

@pytest.fixture()
def mock_elevenlabs():
    """Patch AsyncElevenLabs to simulate success or failure."""
    with patch("app.services.tts_generator.AsyncElevenLabs") as mock_el_class, \
         patch("app.services.tts_generator.settings") as mock_settings:
        
        mock_settings.elevenlabs_api_key = "fake-elevenlabs-key"
        mock_settings.elevenlabs_voice_id = "fake-voice-id"
        mock_settings.elevenlabs_model_id = "fake-model-id"
        
        mock_client = MagicMock()
        mock_el_class.return_value = mock_client
        
        # Make the convert method return an async generator
        async def _fake_convert(**kwargs):
            yield b"ELEVENLABS_MP3_DATA"
            
        mock_client.text_to_speech.convert = _fake_convert
        yield mock_client, mock_settings

@pytest.fixture()
def mock_elevenlabs_no_key():
    """Patch settings so elevenlabs_api_key is empty."""
    with patch("app.services.tts_generator.settings") as mock_settings:
        mock_settings.elevenlabs_api_key = ""
        yield mock_settings

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGenerateSceneAudio:

    @pytest.mark.asyncio
    async def test_raises_on_empty_text(self, mock_edge_tts, mock_elevenlabs_no_key):
        """Whitespace-only text must raise TTSGenerationError before calling any SDK."""
        from app.services.tts_generator import TTSGenerator, TTSGenerationError
        tts = TTSGenerator()

        with pytest.raises(TTSGenerationError, match="must not be empty"):
            await tts.generate_scene_audio("job-003", 1, "   ")

    @pytest.mark.asyncio
    async def test_edge_tts_success(self, mock_edge_tts, mock_elevenlabs_no_key):
        """Without ElevenLabs key, falls back to edge-tts successfully."""
        mock_edge_tts_mod, tmp_path = mock_edge_tts
        from app.services.tts_generator import TTSGenerator
        tts = TTSGenerator()
        
        path = await tts.generate_scene_audio(
            "job-001", 1, "The sun delivers more energy in one hour than humanity uses in a year."
        )
        assert isinstance(path, str)
        assert path.endswith(".mp3")
        assert Path(path).exists()
        assert Path(path).read_bytes() == b"ID3FAKEMP3DATA"
        mock_edge_tts_mod.Communicate.assert_called_once()

    @pytest.mark.asyncio
    async def test_edge_tts_failure_raises(self, mock_edge_tts, mock_elevenlabs_no_key):
        """If edge-tts fails (and ElevenLabs is not active), raises TTSGenerationError."""
        mock_edge_tts_mod, tmp_path = mock_edge_tts
        async def _broken_save(output_path: str):
            raise ConnectionError("Edge TTS server unreachable")
        mock_edge_tts_mod.Communicate.return_value.save = _broken_save

        from app.services.tts_generator import TTSGenerator, TTSGenerationError
        tts = TTSGenerator()

        with pytest.raises(TTSGenerationError, match="Edge TTS server unreachable"):
            await tts.generate_scene_audio("job-005", 1, "A valid narration sentence.")

    @pytest.mark.asyncio
    async def test_elevenlabs_success(self, mock_edge_tts, mock_elevenlabs):
        """With ElevenLabs key, uses ElevenLabs and skips edge-tts."""
        mock_edge_tts_mod, tmp_path = mock_edge_tts
        mock_client, mock_settings = mock_elevenlabs
        
        from app.services.tts_generator import TTSGenerator
        tts = TTSGenerator()
        
        path = await tts.generate_scene_audio("job-el-1", 1, "ElevenLabs test")
        
        assert Path(path).exists()
        assert Path(path).read_bytes() == b"ELEVENLABS_MP3_DATA"
        # Edge TTS should not have been called
        mock_edge_tts_mod.Communicate.assert_not_called()

    @pytest.mark.asyncio
    async def test_elevenlabs_fallback_to_edge_tts(self, mock_edge_tts, mock_elevenlabs):
        """If ElevenLabs fails (e.g. quota), it catches the error and falls back to edge-tts."""
        mock_edge_tts_mod, tmp_path = mock_edge_tts
        mock_client, mock_settings = mock_elevenlabs
        
        # Simulate ElevenLabs failure
        async def _broken_convert(**kwargs):
            raise Exception("Quota exceeded")
            yield b""  # just to make it a generator
        mock_client.text_to_speech.convert = _broken_convert
        
        from app.services.tts_generator import TTSGenerator
        tts = TTSGenerator()
        
        path = await tts.generate_scene_audio("job-el-fallback", 2, "Fallback test")
        
        assert Path(path).exists()
        # The file content should be from the Edge TTS mock
        assert Path(path).read_bytes() == b"ID3FAKEMP3DATA"
        mock_edge_tts_mod.Communicate.assert_called_once()
