"""
Unit tests for Orchestrator Service.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.orchestrator import run_generation_pipeline, regenerate_scene_pipeline
from app.services.job_store import job_store


@pytest.fixture
def clean_job_store():
    # Clear internal dict for tests
    job_store._jobs.clear()
    yield
    job_store._jobs.clear()

@pytest.fixture
def mock_services():
    with patch("app.services.orchestrator.generate_content_plan") as planner, \
         patch("app.services.orchestrator.image_generator") as imgen, \
         patch("app.services.orchestrator.tts_generator") as ttsgen, \
         patch("app.services.orchestrator.transcription_service") as transgen, \
         patch("app.services.orchestrator.video_compositor") as vidcomp, \
         patch("app.services.orchestrator.StorageClient") as storage:
         
        # Mock planner
        class DummyScene:
            def __init__(self, id, nar, prompt, dur):
                self.scene_id = id
                self.narration = nar
                self.visual_prompt = prompt
                self.duration = dur
                
        class DummyPlan:
            title = "Test"
            hook = "Hook"
            script = "Script"
            scenes = [
                DummyScene(1, "Nar1", "Prom1", 3),
                DummyScene(2, "Nar2", "Prom2", 4),
            ]
            
        planner.return_value = DummyPlan()
        
        # Mock other services
        imgen.generate_scene_image = MagicMock(return_value="/tmp/img.png")
        ttsgen.generate_scene_audio = AsyncMock(return_value="/tmp/aud.mp3")
        transgen.generate_scene_srt = MagicMock(return_value="/tmp/sub.srt")
        vidcomp.build_video_from_assets = MagicMock(return_value="/tmp/final.mp4")
        
        mock_storage_instance = MagicMock()
        mock_storage_instance.upload_video.return_value = "https://s3.url/final.mp4"
        storage.return_value = mock_storage_instance
        
        yield {
            "planner": planner,
            "imgen": imgen,
            "ttsgen": ttsgen,
            "transgen": transgen,
            "vidcomp": vidcomp,
            "storage": storage,
            "storage_instance": mock_storage_instance
        }

@pytest.mark.asyncio
async def test_run_generation_pipeline_success(clean_job_store, mock_services):
    job_id = job_store.create_job()
    
    await run_generation_pipeline(job_id, "topic", 30, "style")
    
    job = job_store.get_job(job_id)
    assert job["status"] == "completed"
    assert job["stage"] == "completed"
    assert job["progress"] == 100
    assert job["video_url"] == "https://s3.url/final.mp4"
    assert len(job["scenes"]) == 2
    assert job["scenes"][0]["narration"] == "Nar1"
    
    # Assert services were called
    planner = mock_services["planner"]
    planner.assert_called_once()
    assert mock_services["imgen"].generate_scene_image.call_count == 2
    assert mock_services["ttsgen"].generate_scene_audio.call_count == 2
    assert mock_services["transgen"].generate_scene_srt.call_count == 2
    mock_services["vidcomp"].build_video_from_assets.assert_called_once()
    mock_services["storage_instance"].upload_video.assert_called_once_with(job_id, "/tmp/final.mp4")

@pytest.mark.asyncio
async def test_run_generation_pipeline_failure(clean_job_store, mock_services):
    job_id = job_store.create_job()
    
    # Force failure in planner
    mock_services["planner"].side_effect = Exception("Planner failed")
    
    await run_generation_pipeline(job_id, "topic", 30, "style")
    
    job = job_store.get_job(job_id)
    assert job["status"] == "failed"
    assert job["error"] == "Planner failed"
    # Never reached completion
    assert job["progress"] == 10
    
    # Ensure downstream services weren't called
    mock_services["imgen"].generate_scene_image.assert_not_called()
    mock_services["vidcomp"].build_video_from_assets.assert_not_called()
    mock_services["storage_instance"].upload_video.assert_not_called()


@pytest.mark.asyncio
async def test_regenerate_scene_pipeline_success(clean_job_store, mock_services):
    job_id = job_store.create_job()
    job_store.update_job(
        job_id, 
        status="completed", 
        scenes=[{"scene_id": 1, "visual_prompt": "test prompt 1"}]
    )
    
    await regenerate_scene_pipeline(job_id, 1)
    
    job = job_store.get_job(job_id)
    assert job["status"] == "completed"
    assert job["stage"] == "completed"
    
    # Assert LLM and TTS were NOT called
    mock_services["planner"].assert_not_called()
    mock_services["ttsgen"].generate_scene_audio.assert_not_called()
    
    # Assert ImageGen and VideoComp WERE called
    mock_services["imgen"].generate_scene_image.assert_called_once_with(job_id, 1, "test prompt 1")
    mock_services["vidcomp"].build_video_from_assets.assert_called_once()
    mock_services["storage_instance"].upload_video.assert_called_once()

