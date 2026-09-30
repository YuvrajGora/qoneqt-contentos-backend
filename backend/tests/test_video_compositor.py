"""
Unit tests for VideoCompositor.

Mocks subprocess.run to verify FFmpeg commands without requiring a real binary.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.video_compositor import VideoCompositionError, VideoCompositor


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_ffmpeg():
    with patch("imageio_ffmpeg.get_ffmpeg_exe", return_value="/mock/path/to/ffmpeg"):
        yield

@pytest.fixture
def mock_subprocess_run():
    with patch("subprocess.run") as mock_run:
        yield mock_run

@pytest.fixture
def compositor(mock_ffmpeg):
    return VideoCompositor()

@pytest.fixture
def mock_files(tmp_path):
    img = tmp_path / "test_image.jpg"
    img.write_text("fake image data")
    
    aud = tmp_path / "test_audio.mp3"
    aud.write_text("fake audio data")
    
    return str(img), str(aud), tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_compose_scene_clip_success(compositor, mock_files, mock_subprocess_run):
    img_path, aud_path, tmp_path = mock_files
    out_path = str(tmp_path / "out_clip.mp4")
    
    result = compositor.compose_scene_clip(img_path, aud_path, out_path)
    
    assert result == out_path
    mock_subprocess_run.assert_called_once()
    
    # Verify FFmpeg args
    cmd = mock_subprocess_run.call_args[0][0]
    cwd = mock_subprocess_run.call_args[1].get("cwd")
    import os
    assert cwd == os.path.dirname(img_path)
    
    assert cmd[0] == "/mock/path/to/ffmpeg"
    assert "-loop" in cmd
    assert "1" in cmd
    assert "-i" in cmd
    assert "test_image.jpg" in cmd  # uses basename
    assert "test_audio.mp3" in cmd  # uses basename
    assert "-c:v" in cmd
    assert "libx264" in cmd
    assert "-shortest" in cmd
    assert cmd[-1] == "out_clip.mp4"
    assert "subtitles=" not in cmd[cmd.index("-vf") + 1]

def test_compose_scene_clip_with_subtitles(compositor, mock_files, mock_subprocess_run, tmp_path):
    img_path, aud_path, _ = mock_files
    srt_path = tmp_path / "test.srt"
    srt_path.write_text("fake srt")
    out_path = str(tmp_path / "out_clip.mp4")
    
    compositor.compose_scene_clip(img_path, aud_path, out_path, srt_path=str(srt_path))
    
    cmd = mock_subprocess_run.call_args[0][0]
    vf_arg = cmd[cmd.index("-vf") + 1]
    assert "subtitles=test.srt:force_style=" in vf_arg

def test_compose_scene_clip_missing_image(compositor, mock_files):
    _, aud_path, tmp_path = mock_files
    with pytest.raises(VideoCompositionError, match="Image file not found"):
        compositor.compose_scene_clip("/does/not/exist.jpg", aud_path, str(tmp_path / "out.mp4"))

def test_compose_scene_clip_missing_audio(compositor, mock_files):
    img_path, _, tmp_path = mock_files
    with pytest.raises(VideoCompositionError, match="Audio file not found"):
        compositor.compose_scene_clip(img_path, "/does/not/exist.mp3", str(tmp_path / "out.mp4"))

def test_compose_scene_clip_ffmpeg_failure(compositor, mock_files, mock_subprocess_run):
    img_path, aud_path, tmp_path = mock_files
    out_path = str(tmp_path / "out_clip.mp4")
    
    mock_subprocess_run.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd=["ffmpeg"], stderr="Invalid filtergraph"
    )
    
    with pytest.raises(VideoCompositionError, match="Invalid filtergraph"):
        compositor.compose_scene_clip(img_path, aud_path, out_path)

def test_concatenate_scenes_success(compositor, mock_files, mock_subprocess_run):
    _, _, tmp_path = mock_files
    clip1 = tmp_path / "clip1.mp4"
    clip2 = tmp_path / "clip2.mp4"
    clip1.write_text("fake clip 1")
    clip2.write_text("fake clip 2")
    
    with patch("app.services.video_compositor.TEMP_ASSETS_DIR", tmp_path):
        result = compositor.concatenate_scenes("job123", [str(clip1), str(clip2)])
        
        assert "job123_final.mp4" in result
        mock_subprocess_run.assert_called_once()
        
        cmd = mock_subprocess_run.call_args[0][0]
        assert cmd[0] == "/mock/path/to/ffmpeg"
        assert "-f" in cmd
        assert "concat" in cmd
        
        # Verify the concat manifest was created and then cleaned up
        concat_txt_path = tmp_path / "job123_concat.txt"
        assert not concat_txt_path.exists()  # should be cleaned up by finally block

def test_concatenate_scenes_empty_list(compositor):
    with pytest.raises(VideoCompositionError, match="No scene clips provided"):
        compositor.concatenate_scenes("job123", [])

def test_concatenate_scenes_missing_clip(compositor):
    with pytest.raises(VideoCompositionError, match="Scene clip not found"):
        compositor.concatenate_scenes("job123", ["/does/not/exist.mp4"])

def test_build_video_from_assets_success(compositor, mock_files, mock_subprocess_run):
    img_path, aud_path, tmp_path = mock_files
    
    scenes = [
        {"scene_id": 2, "image_path": img_path, "audio_path": aud_path},
        {"scene_id": 1, "image_path": img_path, "audio_path": aud_path}
    ]
    
    with patch("app.services.video_compositor.TEMP_ASSETS_DIR", tmp_path), \
         patch.object(compositor, "compose_scene_clip") as mock_compose, \
         patch.object(compositor, "concatenate_scenes", return_value="final.mp4") as mock_concat:
        
        result = compositor.build_video_from_assets("job456", scenes)
        
        assert result == "final.mp4"
        
        # Should be called twice (once per scene)
        assert mock_compose.call_count == 2
        
        # Order should be sorted by scene_id (1, then 2)
        # We can verify by looking at the output_clip_path passed to compose_scene_clip
        call1 = mock_compose.call_args_list[0][0] # args tuple for first call
        call2 = mock_compose.call_args_list[1][0] # args tuple for second call
        assert "scene_1" in call1[2]
        assert "scene_2" in call2[2]
        
        mock_concat.assert_called_once()
        # Verify the paths passed to concatenate_scenes are in the correct order
        concat_paths = mock_concat.call_args[0][1]
        assert "scene_1" in concat_paths[0]
        assert "scene_2" in concat_paths[1]

def test_build_video_from_assets_empty(compositor):
    with pytest.raises(VideoCompositionError, match="No scenes provided"):
        compositor.build_video_from_assets("job456", [])

def test_build_video_from_assets_missing_key(compositor):
    with pytest.raises(VideoCompositionError, match="Missing required key"):
        compositor.build_video_from_assets("job456", [{"image_path": "a", "audio_path": "b"}]) # missing scene_id
