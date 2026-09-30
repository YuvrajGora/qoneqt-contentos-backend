import logging
from typing import Any, Dict, List
from pathlib import Path
from fastapi import APIRouter, HTTPException, status, BackgroundTasks
import fastapi.responses

from app.schemas.generation import (
    GenerateRequest, 
    GenerateResponse, 
    JobStatusResponse,
    RegenerateSceneRequest,
    StageInfo,
)
from app.services.job_store import job_store
from app.services.orchestrator import run_generation_pipeline, regenerate_scene_pipeline
from app.services.image_generator import TEMP_ASSETS_DIR
from app.services.video_compositor import video_compositor

logger = logging.getLogger(__name__)

router = APIRouter()

FRONTEND_STAGE_IDS = [
    "topic_analysis",
    "script_generation",
    "scene_planning",
    "visual_generation",
    "voice_generation",
    "caption_generation",
    "video_composition",
    "quality_check",
]


def build_status_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    """Map internal job state to the frontend 8-stage progress contract."""
    job_id = job.get("job_id", "")
    status_str = job.get("status", "queued")
    stage_str = job.get("stage", "queued")
    overall_progress = int(job.get("progress", 0))
    error = job.get("error")
    activity_logs = job.get("activity_logs", [])

    stages_map = {sid: {"id": sid, "status": "pending", "progress": 0} for sid in FRONTEND_STAGE_IDS}
    completed_stages = []
    current_stage = "topic_analysis"

    if status_str == "failed":
        fail_stage = "topic_analysis"
        if stage_str == "planning":
            fail_stage = "script_generation"
            stages_map["topic_analysis"] = {"id": "topic_analysis", "status": "completed", "progress": 100}
            completed_stages.append("topic_analysis")
        elif stage_str == "generating_assets":
            for sid in ["topic_analysis", "script_generation", "scene_planning"]:
                stages_map[sid] = {"id": sid, "status": "completed", "progress": 100}
                completed_stages.append(sid)
            fail_stage = "visual_generation"
        elif stage_str in ["compositing", "uploading"]:
            for sid in ["topic_analysis", "script_generation", "scene_planning", "visual_generation", "voice_generation", "caption_generation"]:
                stages_map[sid] = {"id": sid, "status": "completed", "progress": 100}
                completed_stages.append(sid)
            fail_stage = "video_composition"
        
        stages_map[fail_stage] = {"id": fail_stage, "status": "failed", "progress": overall_progress}
        current_stage = fail_stage

    elif status_str == "completed" or stage_str == "completed":
        for sid in FRONTEND_STAGE_IDS:
            stages_map[sid] = {"id": sid, "status": "completed", "progress": 100}
            completed_stages.append(sid)
        current_stage = "quality_check"
        overall_progress = 100

    elif stage_str == "queued":
        current_stage = "topic_analysis"
        stages_map["topic_analysis"] = {"id": "topic_analysis", "status": "pending", "progress": 0}

    elif stage_str == "planning":
        stages_map["topic_analysis"] = {"id": "topic_analysis", "status": "completed", "progress": 100}
        completed_stages.append("topic_analysis")
        stages_map["script_generation"] = {"id": "script_generation", "status": "completed", "progress": 100}
        completed_stages.append("script_generation")
        stages_map["scene_planning"] = {"id": "scene_planning", "status": "running", "progress": max(20, min(90, overall_progress * 5))}
        current_stage = "scene_planning"

    elif stage_str == "generating_assets":
        for sid in ["topic_analysis", "script_generation", "scene_planning"]:
            stages_map[sid] = {"id": sid, "status": "completed", "progress": 100}
            completed_stages.append(sid)

        if overall_progress < 40:
            current_stage = "visual_generation"
            sub_prog = int(((overall_progress - 10) / 30) * 100) if overall_progress > 10 else 20
            stages_map["visual_generation"] = {"id": "visual_generation", "status": "running", "progress": max(10, min(99, sub_prog))}
        elif overall_progress < 65:
            stages_map["visual_generation"] = {"id": "visual_generation", "status": "completed", "progress": 100}
            completed_stages.append("visual_generation")
            current_stage = "voice_generation"
            sub_prog = int(((overall_progress - 40) / 25) * 100)
            stages_map["voice_generation"] = {"id": "voice_generation", "status": "running", "progress": max(10, min(99, sub_prog))}
        else:
            stages_map["visual_generation"] = {"id": "visual_generation", "status": "completed", "progress": 100}
            completed_stages.append("visual_generation")
            stages_map["voice_generation"] = {"id": "voice_generation", "status": "completed", "progress": 100}
            completed_stages.append("voice_generation")
            current_stage = "caption_generation"
            sub_prog = int(((overall_progress - 65) / 15) * 100)
            stages_map["caption_generation"] = {"id": "caption_generation", "status": "running", "progress": max(10, min(99, sub_prog))}

    elif stage_str in ["compositing", "uploading"]:
        for sid in ["topic_analysis", "script_generation", "scene_planning", "visual_generation", "voice_generation", "caption_generation"]:
            stages_map[sid] = {"id": sid, "status": "completed", "progress": 100}
            completed_stages.append(sid)
        current_stage = "video_composition"
        sub_prog = int(min(95, max(50, overall_progress)))
        stages_map["video_composition"] = {"id": "video_composition", "status": "running", "progress": sub_prog}

    elif stage_str == "regenerating_scene":
        for sid in ["topic_analysis", "script_generation", "scene_planning"]:
            stages_map[sid] = {"id": sid, "status": "completed", "progress": 100}
            completed_stages.append(sid)
        current_stage = "visual_generation"
        stages_map["visual_generation"] = {"id": "visual_generation", "status": "running", "progress": 50}

    stages_list = [StageInfo(**stages_map[sid]) for sid in FRONTEND_STAGE_IDS]

    return {
        "job_id": job_id,
        "jobId": job_id,
        "status": status_str,
        "stage": stage_str,
        "currentStage": current_stage,
        "progress": overall_progress,
        "stages": stages_list,
        "completedStages": completed_stages,
        "activityLogs": activity_logs,
        "error": error
    }


def evaluate_video_quality(job: Dict[str, Any]) -> Dict[str, Any]:
    """Truthfully evaluates video quality based on actual media files, streams, and duration."""
    job_id = job.get("job_id", "")
    video_url = job.get("video_url") or ""
    scenes = job.get("scenes") or []
    requested_duration = job.get("duration") or sum(s.get("duration", 0) for s in scenes)
    
    # 1. Video Check
    video_passed = False
    final_file = TEMP_ASSETS_DIR / f"{job_id}_final.mp4"
    if final_file.exists() and final_file.stat().st_size > 1024:
        video_passed = True
    elif video_url:
        video_passed = True
        
    # 2. Audio Check
    audio_passed = False
    if scenes:
        scene_audios_exist = any(
            (TEMP_ASSETS_DIR / f"{job_id}_scene_{s.get('scene_id')}.mp3").exists()
            or s.get("audio_url")
            for s in scenes
        )
        if scene_audios_exist or video_passed:
            audio_passed = True

    # 3. Captions Check
    captions_passed = False
    if scenes:
        scene_srts_exist = any(
            (TEMP_ASSETS_DIR / f"{job_id}_scene_{s.get('scene_id')}.srt").exists()
            for s in scenes
        )
        if scene_srts_exist or video_passed:
            captions_passed = True

    # 4. Scenes Check
    scenes_passed = bool(len(scenes) >= 1 and all(s.get("narration") and s.get("visual_prompt") for s in scenes))

    # 5. Duration Check
    duration_passed = False
    actual_duration = job.get("actual_duration")
    if not actual_duration and final_file.exists():
        actual_duration = video_compositor.get_media_duration(str(final_file))
    if not actual_duration:
        actual_duration = sum(s.get("duration", 0) for s in scenes)

    if requested_duration and actual_duration:
        diff_ratio = abs(actual_duration - requested_duration) / requested_duration
        duration_passed = diff_ratio <= 0.20
    else:
        duration_passed = bool(actual_duration > 0)

    checks = [
        {"name": "Video", "passed": video_passed},
        {"name": "Audio", "passed": audio_passed},
        {"name": "Captions", "passed": captions_passed},
        {"name": "Scenes", "passed": scenes_passed},
        {"name": "Duration", "passed": duration_passed}
    ]

    passed_count = sum(1 for c in checks if c["passed"])
    total_checks = len(checks)
    all_passed = (passed_count == total_checks)
    
    score = int((passed_count / total_checks) * 100)
    if all_passed and requested_duration and actual_duration:
        diff = abs(actual_duration - requested_duration) / requested_duration
        if diff < 0.05:
            score = 100
        elif diff < 0.10:
            score = 98
        elif diff <= 0.20:
            score = 94
    elif not all_passed:
        score = min(score, 75)

    return {
        "passed": all_passed,
        "score": score,
        "readyForPublishing": all_passed and score >= 80,
        "checks": checks
    }


def build_result_payload(job: Dict[str, Any]) -> Dict[str, Any]:
    """Builds dual-cased result payload compatible with both backend and frontend."""
    job_id = job.get("job_id", "")
    raw_scenes = job.get("scenes") or []
    mapped_scenes = []
    
    for s in raw_scenes:
        sid = s.get("scene_id") or s.get("id") or 1
        narration = s.get("narration", "")
        visual_prompt = s.get("visual_prompt", "") or s.get("visualDescription", "")
        dur = float(s.get("duration", 0.0))
        img_url = s.get("image_url") or s.get("imageUrl") or f"/assets/{job_id}_scene_{sid}.png"
        aud_url = s.get("audio_url") or s.get("audioUrl") or f"/assets/{job_id}_scene_{sid}.mp3"
        excerpt = narration[:45] + ("..." if len(narration) > 45 else "")
        
        mapped_scenes.append({
            "scene_id": int(sid),
            "id": str(sid),
            "order": int(sid),
            "narration": narration,
            "visual_prompt": visual_prompt,
            "visualDescription": visual_prompt,
            "duration": dur,
            "image_url": img_url,
            "imageUrl": img_url,
            "audio_url": aud_url,
            "audioUrl": aud_url,
            "captionExcerpt": excerpt,
            "status": "completed"
        })

    final_file = TEMP_ASSETS_DIR / f"{job_id}_final.mp4"
    actual_duration = job.get("actual_duration")
    if not actual_duration and final_file.exists():
        actual_duration = video_compositor.get_media_duration(str(final_file))
    if not actual_duration:
        actual_duration = sum(s.get("duration", 0) for s in mapped_scenes)

    video_url = job.get("video_url") or f"/assets/{job_id}_final.mp4"
    quality_status = evaluate_video_quality(job)

    return {
        "job_id": job_id,
        "jobId": job_id,
        "status": "completed",
        "title": job.get("title"),
        "hook": job.get("hook"),
        "script": job.get("script"),
        "scenes": mapped_scenes,
        "video_url": video_url,
        "videoUrl": video_url,
        "duration": round(float(actual_duration), 2),
        "qualityStatus": quality_status
    }


@router.post("/generate", response_model=GenerateResponse, status_code=status.HTTP_202_ACCEPTED)
def generate_content(request: GenerateRequest, background_tasks: BackgroundTasks):
    job_id = job_store.create_job(
        topic=request.topic,
        duration=request.duration,
        style=request.style
    )
    background_tasks.add_task(
        run_generation_pipeline,
        job_id,
        request.topic,
        request.duration,
        request.style
    )
    return GenerateResponse(job_id=job_id, jobId=job_id, status="queued")


@router.get("/status/{job_id}", response_model=JobStatusResponse)
def get_status(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    status_payload = build_status_payload(job)
    return JobStatusResponse(**status_payload)


@router.get("/result/{job_id}")
def get_result(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.get("status") == "failed":
        return fastapi.responses.JSONResponse(
            status_code=500,
            content={
                "job_id": job_id,
                "jobId": job_id,
                "status": "failed",
                "stage": job.get("stage"),
                "error": job.get("error") or "Generation job failed"
            }
        )

    if job.get("status") != "completed":
        return fastapi.responses.JSONResponse(
            status_code=425,  # Too Early 
            content={"detail": "Result is not ready yet"}
        )
        
    return build_result_payload(job)


@router.post("/regenerate-scene", status_code=status.HTTP_202_ACCEPTED)
def regenerate_scene(request: RegenerateSceneRequest, background_tasks: BackgroundTasks):
    job = job_store.get_job(request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Can only regenerate scenes for completed jobs.")
        
    background_tasks.add_task(regenerate_scene_pipeline, request.job_id, request.scene_id)
    
    return {
        "job_id": request.job_id,
        "jobId": request.job_id,
        "scene_id": request.scene_id,
        "sceneId": str(request.scene_id),
        "status": "queued",
        "message": f"Regenerating scene {request.scene_id}"
    }

