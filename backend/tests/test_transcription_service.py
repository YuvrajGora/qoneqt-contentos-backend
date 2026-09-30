"""
Unit tests for TranscriptionService.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.transcription_service import TranscriptionError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_whisper():
    with patch("app.services.transcription_service.WhisperModel") as mock_model_class:
        mock_model_instance = MagicMock()
        mock_model_class.return_value = mock_model_instance
        yield mock_model_instance

@pytest.fixture
def transcription_service(mock_whisper):
    from app.services.transcription_service import TranscriptionService
    return TranscriptionService()

@pytest.fixture
def mock_audio(tmp_path):
    audio_path = tmp_path / "test.mp3"
    audio_path.write_text("fake audio")
    return str(audio_path), tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_generate_scene_srt_success(transcription_service, mock_whisper, mock_audio):
    audio_path, tmp_path = mock_audio
    
    # Mock return of model.transcribe
    # Returns (segments_generator, info)
    class DummyWord:
        def __init__(self, start, end, word):
            self.start = start
            self.end = end
            self.word = word
            
    class DummySegment:
        def __init__(self, words):
            self.words = words
            
    # "This is a test of the fast whisper subtitle system"
    # Chunk 1: This is a (0.0 -> 1.5)
    # Chunk 2: test of the (1.5 -> 3.0)
    # Chunk 3: fast whisper subtitle (3.0 -> 4.5)
    # Chunk 4: system (4.5 -> 5.0)
    seg1 = DummySegment([
        DummyWord(0.0, 0.5, "This"),
        DummyWord(0.5, 1.0, "is"),
        DummyWord(1.0, 1.5, "a"),
        DummyWord(1.5, 2.0, "test"),
        DummyWord(2.0, 2.5, "of"),
        DummyWord(2.5, 3.0, "the"),
    ])
    seg2 = DummySegment([
        DummyWord(3.0, 3.5, "fast"),
        DummyWord(3.5, 4.0, "whisper"),
        DummyWord(4.0, 4.5, "subtitle"),
        DummyWord(4.5, 5.0, "system"),
    ])
    
    mock_whisper.transcribe.return_value = ([seg1, seg2], None)
    
    with patch("app.services.transcription_service.TEMP_ASSETS_DIR", tmp_path):
        srt_path = transcription_service.generate_scene_srt("job1", 1, audio_path)
        
        assert Path(srt_path).exists()
        
        content = Path(srt_path).read_text()
        
        assert "1\n00:00:00,000 --> 00:00:01,500\nThis is a\n\n" in content
        assert "2\n00:00:01,500 --> 00:00:03,000\ntest of the\n\n" in content
        assert "3\n00:00:03,000 --> 00:00:04,500\nfast whisper subtitle\n\n" in content
        assert "4\n00:00:04,500 --> 00:00:05,000\nsystem\n\n" in content

def test_generate_scene_srt_missing_audio(transcription_service):
    with pytest.raises(TranscriptionError, match="Audio file not found"):
        transcription_service.generate_scene_srt("job1", 1, "/does/not/exist.mp3")

def test_generate_scene_srt_transcribe_failure(transcription_service, mock_whisper, mock_audio):
    audio_path, _ = mock_audio
    mock_whisper.transcribe.side_effect = Exception("Model out of memory")
    
    with pytest.raises(TranscriptionError, match="faster-whisper failed to transcribe: Model out of memory"):
        transcription_service.generate_scene_srt("job1", 1, audio_path)

def test_format_timestamp():
    from app.services.transcription_service import format_timestamp
    assert format_timestamp(0.0) == "00:00:00,000"
    assert format_timestamp(1.5) == "00:00:01,500"
    assert format_timestamp(61.999) == "00:01:01,999"
    assert format_timestamp(3600.001) == "01:00:00,001"
    # Rounding tests
    assert format_timestamp(1.9999) == "00:00:02,000"
