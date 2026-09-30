"""
JobStore Service.

Stores asynchronous video generation job state.
NOTE: This is an in-memory, thread-safe, single-process store designed for
hackathon development and single-container deployments. Jobs are ephemeral and
will be reset if the server restarts.
"""

import threading
import uuid
from typing import Dict, Optional, Any


from datetime import datetime, timezone

class JobStore:
    """Thread-safe in-memory job state store."""

    def __init__(self):
        self._lock = threading.RLock()
        self._jobs: Dict[str, Dict[str, Any]] = {}

    def create_job(self, **kwargs) -> str:
        job_id = str(uuid.uuid4())
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "status": "queued",
                "stage": "queued",
                "progress": 0,
                "error": None,
                "title": None,
                "hook": None,
                "script": None,
                "scenes": [],
                "video_url": None,
                "created_at": now_iso,
                "activity_logs": [
                    {
                        "id": "log-init",
                        "timestamp": now_iso,
                        "message": "Job queued for generation",
                        "stage": "topic_analysis"
                    }
                ],
                **kwargs
            }
        return job_id

    def add_activity_log(self, job_id: str, message: str, stage: Optional[str] = None) -> None:
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._lock:
            if job_id in self._jobs:
                logs = self._jobs[job_id].setdefault("activity_logs", [])
                logs.append({
                    "id": f"log-{len(logs) + 1}",
                    "timestamp": now_iso,
                    "message": message,
                    "stage": stage
                })

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return dict(job)

    def update_job(self, job_id: str, **kwargs) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(kwargs)

    def clear(self) -> None:
        """Utility method to reset store during testing."""
        with self._lock:
            self._jobs.clear()



job_store = JobStore()
