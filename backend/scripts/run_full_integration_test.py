import time
import json
import re
import subprocess
from pathlib import Path
import httpx
import imageio_ffmpeg

BASE_URL = "http://127.0.0.1:8000/api"
FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

def get_mp4_metadata(file_path: str):
    cmd = [FFMPEG_EXE, "-i", str(file_path)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    stderr = p.stderr
    
    # Duration
    m_dur = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
    dur = 0.0
    if m_dur:
        h, mn, s = map(float, m_dur.groups())
        dur = h * 3600.0 + mn * 60.0 + s
        
    # Resolution
    m_res = re.search(r"(\d{3,4})x(\d{3,4})", stderr)
    res = f"{m_res.group(1)}x{m_res.group(2)}" if m_res else "unknown"
    
    # Audio
    has_audio = "Audio: aac" in stderr or "Audio:" in stderr
    
    return {
        "duration": round(dur, 2),
        "resolution": res,
        "has_audio": has_audio,
        "size_bytes": Path(file_path).stat().st_size if Path(file_path).exists() else 0
    }

def main():
    print("=" * 60)
    print("PHASE 7 & 8: REAL GENERATION + FRONTEND SIMULATION RETEST")
    print("=" * 60)
    
    client = httpx.Client(timeout=30.0)
    
    # 1. POST /api/generate
    gen_payload = {
        "topic": "How AI agents are changing the future of software development",
        "duration": 30,
        "style": "cinematic"
    }
    print(f"\n[1] Sending POST {BASE_URL}/generate ...")
    r = client.post(f"{BASE_URL}/generate", json=gen_payload)
    print(f"Status: {r.status_code}")
    res_data = r.json()
    print("Response:", json.dumps(res_data, indent=2))
    
    assert r.status_code == 202, f"Expected 202, got {r.status_code}"
    assert "jobId" in res_data and "job_id" in res_data
    assert res_data["jobId"] == res_data["job_id"]
    job_id = res_data["jobId"]
    
    # 2. Poll GET /api/status/{job_id}
    print(f"\n[2] Polling GET {BASE_URL}/status/{job_id} ...")
    start_time = time.time()
    last_stage = None
    last_log_count = 0
    final_status_data = None
    
    while True:
        elapsed = round(time.time() - start_time, 1)
        sr = client.get(f"{BASE_URL}/status/{job_id}")
        assert sr.status_code == 200, f"Status check failed: {sr.status_code}"
        sdata = sr.json()
        
        # Verify contract fields on every poll
        assert "jobId" in sdata and "job_id" in sdata
        assert "currentStage" in sdata
        assert "stages" in sdata and len(sdata["stages"]) == 8
        assert "completedStages" in sdata
        assert "activityLogs" in sdata
        
        stage = sdata.get("stage")
        current_stage = sdata.get("currentStage")
        status = sdata.get("status")
        progress = sdata.get("progress")
        logs = sdata.get("activityLogs", [])
        
        if current_stage != last_stage or len(logs) > last_log_count:
            new_logs = logs[last_log_count:]
            for log_entry in new_logs:
                msg = log_entry.get("message") if isinstance(log_entry, dict) else str(log_entry)
                print(f"[{elapsed}s] [LOG] {msg}")
            print(f"[{elapsed}s] Status: {status} | Stage: {stage} | CurrentStage: {current_stage} | Progress: {progress}% | Completed: {sdata['completedStages']}")
            last_stage = current_stage
            last_log_count = len(logs)
            
        if status in ("completed", "failed"):
            final_status_data = sdata
            break
            
        time.sleep(3.0)
        if elapsed > 300:
            raise TimeoutError("Pipeline timed out after 300 seconds")
            
    print(f"\nJob reached terminal state: {final_status_data.get('status')} in {round(time.time() - start_time, 1)}s")
    if final_status_data.get("status") == "failed":
        print("ERROR:", final_status_data.get("error"))
        return
        
    # 3. GET /api/result/{job_id}
    print(f"\n[3] Fetching GET {BASE_URL}/result/{job_id} ...")
    rr = client.get(f"{BASE_URL}/result/{job_id}")
    print(f"Result Status: {rr.status_code}")
    assert rr.status_code == 200, f"Result endpoint returned {rr.status_code}"
    result = rr.json()
    
    print("\n--- RESULT PAYLOAD SUMMARY ---")
    print("jobId:", result.get("jobId"))
    print("job_id:", result.get("job_id"))
    print("title:", result.get("title"))
    print("hook:", result.get("hook"))
    print("script words count:", len(result.get("script", "").split()))
    print("reported duration:", result.get("duration"))
    print("videoUrl:", result.get("videoUrl"))
    print("video_url:", result.get("video_url"))
    print("scene count:", len(result.get("scenes", [])))
    for s in result.get("scenes", []):
        print(f"  Scene {s.get('scene_id')} (id={s.get('id')}, order={s.get('order')}): dur={s.get('duration')}s | nar words={len(s.get('narration','').split())} | img={s.get('imageUrl')} | aud={s.get('audioUrl')}")
        
    print("\nqualityStatus:")
    print(json.dumps(result.get("qualityStatus"), indent=2))
    
    # 4. Probe MP4 on disk
    mp4_path = Path("temp_assets") / f"{job_id}_final.mp4"
    if mp4_path.exists():
        meta = get_mp4_metadata(str(mp4_path))
        print("\n--- FFPROBE METADATA ---")
        print("File:", mp4_path.name)
        print("Size:", f"{meta['size_bytes'] / 1024:.1f} KB")
        print("Resolution:", meta["resolution"])
        print("Audio:", meta["has_audio"])
        print("Actual FFmpeg Duration:", f"{meta['duration']}s")
    else:
        print("WARNING: Final MP4 file not found at", mp4_path)

    # 5. Scene Regeneration with frontend camelCase: POST /api/regenerate-scene
    print(f"\n[4] Testing POST {BASE_URL}/regenerate-scene with camelCase (sceneId='3') ...")
    regen_payload = {
        "jobId": job_id,
        "sceneId": "3"
    }
    re_r = client.post(f"{BASE_URL}/regenerate-scene", json=regen_payload)
    print(f"Regen Status: {re_r.status_code}")
    regen_res = re_r.json()
    print("Regen Response:", json.dumps(regen_res, indent=2))
    assert re_r.status_code == 202
    assert regen_res.get("scene_id") == 3
    
    # Poll regeneration
    print("\nPolling status for regeneration...")
    regen_start = time.time()
    while True:
        elapsed = round(time.time() - regen_start, 1)
        sr = client.get(f"{BASE_URL}/status/{job_id}")
        sdata = sr.json()
        st = sdata.get("status")
        stage = sdata.get("stage")
        if stage != "regenerating_scene" and st == "completed":
            print(f"[{elapsed}s] Regeneration completed!")
            break
        time.sleep(2.0)
        if elapsed > 120:
            print("Regen timeout")
            break
            
    # Fetch final result again
    rr2 = client.get(f"{BASE_URL}/result/{job_id}")
    res2 = rr2.json()
    print("\nUpdated Result reported duration:", res2.get("duration"))
    if mp4_path.exists():
        meta2 = get_mp4_metadata(str(mp4_path))
        print("Updated FFmpeg Duration:", f"{meta2['duration']}s")
        print("Updated File Size:", f"{meta2['size_bytes'] / 1024:.1f} KB")

if __name__ == "__main__":
    main()
