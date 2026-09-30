"""
Unit tests for ImageGenerator.

ALL tests are fully mocked — no API key required, no network calls made.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
from PIL import Image

import pytest

from app.services.image_generator import ImageGenerator, ImageGenerationError


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_hf_client(tmp_path):
    """
    Patch:
      - InferenceClient (to return mock responses)
      - TEMP_ASSETS_DIR (redirect writes to tmp_path)
      - os.getenv (for HF_TOKEN fallback)
      - settings.hf_token
    """
    with patch("app.services.image_generator.InferenceClient") as mock_client_cls, \
         patch("app.services.image_generator.TEMP_ASSETS_DIR", tmp_path), \
         patch("app.services.image_generator.os.getenv") as mock_getenv, \
         patch("app.services.image_generator.settings") as mock_settings:
        
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_getenv.return_value = None
        mock_settings.hf_token = "fake-hf-token"
        
        yield mock_client, tmp_path, mock_getenv


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestGenerateSceneImage:

    def test_returns_path_string_on_success(self, mock_hf_client):
        """Happy path: InferenceClient returns image → file saved → path returned."""
        mock_client, tmp_path, _ = mock_hf_client
        
        mock_image = MagicMock()
        def fake_save(path):
            Path(path).write_bytes(b"fake_png_data")
            
        mock_image.save.side_effect = fake_save
        mock_client.text_to_image.return_value = mock_image

        ig = ImageGenerator()
        path = ig.generate_scene_image("job-001", 1, "A sunny solar farm at dawn")

        assert isinstance(path, str)
        assert path.endswith(".png")
        assert "job-001" in path
        assert "scene_1" in path

        # Check that the file was written
        assert Path(path).exists()
        assert Path(path).read_bytes() == b"fake_png_data"

    def test_filename_format(self, mock_hf_client):
        """File must be named {job_id}_scene_{scene_id}.png."""
        mock_client, tmp_path, _ = mock_hf_client
        
        mock_image = MagicMock()
        mock_client.text_to_image.return_value = mock_image

        ig = ImageGenerator()
        path = ig.generate_scene_image("abc-xyz-123", 7, "Underwater coral reef")

        assert Path(path).name == "abc-xyz-123_scene_7.png"

    def test_raises_on_api_error_when_fallback_disabled(self, mock_hf_client):
        """API exceptions must be wrapped in ImageGenerationError when fallback is disabled."""
        mock_client, tmp_path, _ = mock_hf_client
        mock_client.text_to_image.side_effect = Exception("500 Server Error")

        ig = ImageGenerator()
        with pytest.raises(ImageGenerationError, match="Hugging Face image generation failed"):
            ig.generate_scene_image("job-005", 1, "Clear blue sky with clouds", allow_fallback=False)

    def test_raises_on_network_error_when_fallback_disabled(self, mock_hf_client):
        """Network exceptions must be wrapped in ImageGenerationError when fallback is disabled."""
        mock_client, tmp_path, _ = mock_hf_client
        mock_client.text_to_image.side_effect = ConnectionError("Network unreachable")

        ig = ImageGenerator()
        with pytest.raises(ImageGenerationError, match="Hugging Face image generation failed"):
            ig.generate_scene_image("job-005", 1, "Clear blue sky with clouds", allow_fallback=False)

    def test_raises_on_empty_prompt(self, mock_hf_client):
        """An empty visual prompt must raise ImageGenerationError before calling the API."""
        mock_client, tmp_path, _ = mock_hf_client

        ig = ImageGenerator()
        with pytest.raises(ImageGenerationError, match="must not be empty"):
            ig.generate_scene_image("job-006", 1, "   ")

        # Ensure we never even called the API
        mock_client.text_to_image.assert_not_called()

    def test_raises_when_api_key_missing_and_fallback_disabled(self, mock_hf_client):
        """Missing HF_TOKEN must raise ImageGenerationError when fallback is disabled."""
        mock_client, tmp_path, mock_getenv = mock_hf_client
        
        with patch("app.services.image_generator.settings") as mock_settings:
            mock_settings.hf_token = None
            mock_getenv.return_value = None
            
            ig = ImageGenerator()
            with pytest.raises(ImageGenerationError, match="HF_TOKEN is not configured"):
                ig.generate_scene_image("job-008", 1, "A sunny landscape", allow_fallback=False)

    def test_different_scenes_produce_different_paths(self, mock_hf_client):
        """Each scene_id should produce a unique file name."""
        mock_client, tmp_path, _ = mock_hf_client
        
        mock_image = MagicMock()
        mock_client.text_to_image.return_value = mock_image

        ig = ImageGenerator()
        path1 = ig.generate_scene_image("job-007", 1, "Dense forest canopy at midday")
        path2 = ig.generate_scene_image("job-007", 2, "Open grassland plains at dusk")

        assert path1 != path2
        assert "scene_1" in path1
        assert "scene_2" in path2

    def test_hf_402_depleted_credits_immediately_triggers_fallback(self, mock_hf_client):
        """HF 402 Payment Required must immediately fall back without useless retries."""
        mock_client, tmp_path, _ = mock_hf_client
        mock_client.text_to_image.side_effect = Exception(
            "Client error '402 Payment Required': You have depleted your monthly included credits."
        )

        ig = ImageGenerator()
        path = ig.generate_scene_image("job-fallback", 1, "Neural network visual synthesis")

        # Must have fallen back and generated real PNG
        assert Path(path).exists()
        assert Path(path).name == "job-fallback_scene_1.png"
        # Must only have been called ONCE (skipped retrying on 402)
        assert mock_client.text_to_image.call_count == 1

        # Verify image properties
        with Image.open(path) as img:
            assert img.size == (1080, 1920)
            assert img.format == "PNG"

    def test_missing_hf_token_uses_fallback(self, mock_hf_client):
        """When HF_TOKEN is not set, fallback automatically generates the scene image."""
        mock_client, tmp_path, mock_getenv = mock_hf_client
        with patch("app.services.image_generator.settings") as mock_settings:
            mock_settings.hf_token = None
            mock_getenv.return_value = None
            
            ig = ImageGenerator()
            path = ig.generate_scene_image("job-notoken", 2, "Decentralized computing nodes")
            
            assert Path(path).exists()
            assert Path(path).name == "job-notoken_scene_2.png"
            with Image.open(path) as img:
                assert img.size == (1080, 1920)
