from typing import Any, List, Optional
from pydantic import BaseModel, Field, model_validator

class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1)
    duration: int = Field(..., gt=0)
    style: str = Field(..., min_length=1)

class GenerateResponse(BaseModel):
    job_id: str
    jobId: str
    status: str

    @model_validator(mode="before")
    @classmethod
    def populate_job_ids(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "job_id" in data and "jobId" not in data:
                data["jobId"] = data["job_id"]
            elif "jobId" in data and "job_id" not in data:
                data["job_id"] = data["jobId"]
        return data

class StageInfo(BaseModel):
    id: str
    status: str
    progress: int

class JobStatusResponse(BaseModel):
    job_id: str
    jobId: str
    status: str
    stage: str
    currentStage: str
    progress: int
    stages: List[StageInfo] = []
    completedStages: List[str] = []
    activityLogs: List[Any] = []
    error: Optional[str] = None

class RegenerateSceneRequest(BaseModel):
    job_id: str = Field(..., min_length=1)
    scene_id: int = Field(..., gt=0)

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "job_id" not in data and "jobId" in data:
                data["job_id"] = str(data["jobId"])
            elif "job_id" in data:
                data["job_id"] = str(data["job_id"])
            if "scene_id" not in data and "sceneId" in data:
                data["scene_id"] = data["sceneId"]
            if "scene_id" in data:
                try:
                    data["scene_id"] = int(data["scene_id"])
                except (ValueError, TypeError):
                    pass
        return data

