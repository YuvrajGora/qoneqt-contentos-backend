from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
api_prefix = "/api/v1"

from unittest.mock import patch
import pytest

@pytest.fixture
def mock_orchestrator():
    with patch("app.api.routes.generation.run_generation_pipeline") as m, \
         patch("app.api.routes.generation.regenerate_scene_pipeline") as r:
        yield m, r

def test_generate_valid_request(mock_orchestrator):
    response = client.post(f"{api_prefix}/generate", json={
        "topic": "test topic",
        "duration": 45,
        "style": "educational"
    })
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "queued"
    mock_orchestrator[0].assert_called_once()

def test_generate_invalid_request(mock_orchestrator):
    response = client.post(f"{api_prefix}/generate", json={
        "topic": "",  # invalid: empty
        "duration": -5,  # invalid: negative
        "style": ""  # invalid: empty
    })
    assert response.status_code == 422
    mock_orchestrator[0].assert_not_called()

def test_get_status_existing_job(mock_orchestrator):
    # Create job first
    create_response = client.post(f"{api_prefix}/generate", json={
        "topic": "test topic",
        "duration": 45,
        "style": "educational"
    })
    job_id = create_response.json()["job_id"]

    # Check status
    response = client.get(f"{api_prefix}/status/{job_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["job_id"] == job_id
    assert data["status"] == "queued"
    assert data["stage"] == "queued"
    assert data["progress"] == 0

def test_get_status_unknown_job():
    response = client.get(f"{api_prefix}/status/unknown-123")
    assert response.status_code == 404

def test_get_result_not_ready(mock_orchestrator):
    # Create job first
    create_response = client.post(f"{api_prefix}/generate", json={
        "topic": "test topic",
        "duration": 45,
        "style": "educational"
    })
    job_id = create_response.json()["job_id"]

    # Check result
    response = client.get(f"{api_prefix}/result/{job_id}")
    assert response.status_code == 425
    assert response.json() == {"detail": "Result is not ready yet"}

def test_get_result_failed_job(mock_orchestrator):
    create_response = client.post(f"{api_prefix}/generate", json={
        "topic": "test topic",
        "duration": 45,
        "style": "educational"
    })
    job_id = create_response.json()["job_id"]
    from app.services.job_store import job_store
    job_store.update_job(job_id, status="failed", stage="planning", error="Provider API failed")

    response = client.get(f"{api_prefix}/result/{job_id}")
    assert response.status_code == 500
    data = response.json()
    assert data["job_id"] == job_id
    assert data["status"] == "failed"
    assert data["error"] == "Provider API failed"

def test_regenerate_scene(mock_orchestrator):
    # Setup completed job
    create_response = client.post(f"{api_prefix}/generate", json={
        "topic": "test topic",
        "duration": 45,
        "style": "educational"
    })
    job_id = create_response.json()["job_id"]
    from app.services.job_store import job_store
    job_store.update_job(job_id, status="completed")
    
    response = client.post(f"{api_prefix}/regenerate-scene", json={
        "job_id": job_id,
        "scene_id": 3
    })
    assert response.status_code == 202
    data = response.json()
    assert data["job_id"] == job_id
    assert data["status"] == "queued"
    assert data["message"] == "Regenerating scene 3"
    
    mock_orchestrator[1].assert_called_once_with(job_id, 3)
