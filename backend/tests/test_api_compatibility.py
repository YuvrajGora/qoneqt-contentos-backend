import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.job_store import job_store
from app.services.video_compositor import VideoCompositor

client = TestClient(app)

@pytest.fixture
def mock_orchestrator():
    with patch("app.api.routes.generation.run_generation_pipeline") as m, \
         patch("app.api.routes.generation.regenerate_scene_pipeline") as r:
        yield m, r


def test_api_generate_route_and_dual_casing(mock_orchestrator):
    """Verify POST /api/generate works and returns both job_id and jobId."""
    response = client.post("/api/generate", json={
        "topic": "Future of AI Agents",
        "duration": 30,
        "style": "cinematic"
    })
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert "jobId" in data
    assert data["job_id"] == data["jobId"]
    assert data["status"] == "queued"
    mock_orchestrator[0].assert_called_once()


def test_api_status_route_and_8_stages(mock_orchestrator):
    """Verify GET /api/status/{job_id} returns 8 stages, currentStage, completedStages, and activityLogs."""
    job_id = job_store.create_job(topic="Test", duration=30, style="cinematic")
    job_store.update_job(job_id, status="processing", stage="generating_assets", progress=45)

    response = client.get(f"/api/status/{job_id}")
    assert response.status_code == 200
    data = response.json()

    # Dual casing
    assert data["job_id"] == job_id
    assert data["jobId"] == job_id
    assert data["status"] == "processing"
    assert data["stage"] == "generating_assets"
    assert data["currentStage"] == "voice_generation"
    assert data["progress"] == 45

    # 8 stages
    stages = data["stages"]
    assert len(stages) == 8
    stage_ids = [s["id"] for s in stages]
    assert stage_ids == [
        "topic_analysis",
        "script_generation",
        "scene_planning",
        "visual_generation",
        "voice_generation",
        "caption_generation",
        "video_composition",
        "quality_check",
    ]

    # Completed stages
    assert "topic_analysis" in data["completedStages"]
    assert "script_generation" in data["completedStages"]
    assert "scene_planning" in data["completedStages"]
    assert "visual_generation" in data["completedStages"]

    # Activity logs
    assert isinstance(data["activityLogs"], list)
    assert len(data["activityLogs"]) >= 1


def test_api_result_route_and_field_mapping(mock_orchestrator):
    """Verify GET /api/result/{job_id} returns camelCase + snake_case fields and qualityStatus."""
    job_id = job_store.create_job(topic="AI", duration=30, style="cinematic")
    job_store.update_job(
        job_id,
        status="completed",
        stage="completed",
        progress=100,
        title="AI Revolution",
        hook="AI is everywhere.",
        script="AI agents are building software.",
        video_url=f"/assets/{job_id}_final.mp4",
        actual_duration=29.8,
        scenes=[
            {
                "scene_id": 1,
                "narration": "AI agents are transforming code.",
                "visual_prompt": "Futuristic developer terminal with glowing holographic code",
                "duration": 7.5,
                "image_url": f"/assets/{job_id}_scene_1.png",
                "audio_url": f"/assets/{job_id}_scene_1.mp3"
            },
            {
                "scene_id": 2,
                "narration": "Autonomous workflows handle deployments.",
                "visual_prompt": "Server farm humming with blue LED streams",
                "duration": 7.5,
                "image_url": f"/assets/{job_id}_scene_2.png",
                "audio_url": f"/assets/{job_id}_scene_2.mp3"
            }
        ]
    )

    response = client.get(f"/api/result/{job_id}")
    assert response.status_code == 200
    data = response.json()

    # Dual keys on root
    assert data["job_id"] == job_id
    assert data["jobId"] == job_id
    assert data["video_url"] == f"/assets/{job_id}_final.mp4"
    assert data["videoUrl"] == f"/assets/{job_id}_final.mp4"
    assert data["duration"] == 29.8

    # Scene field mapping
    scenes = data["scenes"]
    assert len(scenes) == 2
    s1 = scenes[0]
    assert s1["scene_id"] == 1
    assert s1["id"] == "1"
    assert s1["order"] == 1
    assert s1["visual_prompt"] == "Futuristic developer terminal with glowing holographic code"
    assert s1["visualDescription"] == "Futuristic developer terminal with glowing holographic code"
    assert s1["image_url"] == f"/assets/{job_id}_scene_1.png"
    assert s1["imageUrl"] == f"/assets/{job_id}_scene_1.png"
    assert s1["audio_url"] == f"/assets/{job_id}_scene_1.mp3"
    assert s1["audioUrl"] == f"/assets/{job_id}_scene_1.mp3"
    assert "captionExcerpt" in s1
    assert s1["status"] == "completed"

    # Quality status
    qs = data["qualityStatus"]
    assert "passed" in qs
    assert "score" in qs
    assert "readyForPublishing" in qs
    assert "checks" in qs
    check_names = [c["name"] for c in qs["checks"]]
    assert "Video" in check_names
    assert "Audio" in check_names
    assert "Captions" in check_names
    assert "Scenes" in check_names
    assert "Duration" in check_names


def test_api_regenerate_scene_camel_case_and_string_id(mock_orchestrator):
    """Verify POST /api/regenerate-scene accepts camelCase jobId and string sceneId."""
    job_id = job_store.create_job()
    job_store.update_job(job_id, status="completed")

    # Call with frontend camelCase format: {"jobId": "...", "sceneId": "3"}
    response = client.post("/api/regenerate-scene", json={
        "jobId": job_id,
        "sceneId": "3"
    })
    assert response.status_code == 202
    data = response.json()
    assert data["job_id"] == job_id
    assert data["jobId"] == job_id
    assert data["scene_id"] == 3
    assert data["sceneId"] == "3"
    assert data["status"] == "queued"
    mock_orchestrator[1].assert_called_once_with(job_id, 3)


def test_video_compositor_target_duration_and_warning():
    """Verify VideoCompositor accepts target_duration and computes padding."""
    with patch("imageio_ffmpeg.get_ffmpeg_exe", return_value="ffmpeg"), \
         patch("subprocess.run") as mock_run, \
         patch.object(VideoCompositor, "get_media_duration", return_value=5.0):
        
        comp = VideoCompositor()
        
        # Test compose_scene_clip with target_duration
        with patch("pathlib.Path.exists", return_value=True):
            comp.compose_scene_clip(
                image_path="/tmp/img.png",
                audio_path="/tmp/aud.mp3",
                output_clip_path="/tmp/out.mp4",
                target_duration=7.5
            )
            
            cmd = mock_run.call_args[0][0]
            assert "-af" in cmd
            assert "apad" in cmd
            assert "-t" in cmd
            assert "7.50" in cmd
            assert "-shortest" not in cmd
