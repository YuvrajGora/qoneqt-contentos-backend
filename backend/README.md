# Backend API — Content Pipeline

AI-powered short-form video content pipeline backend for the Qoneqt × CTRL FREAK AI Challenge.

## Milestone Status

| Milestone | Status | Description |
|-----------|--------|-------------|
| 1 | ✅ Done | FastAPI skeleton + API contract |
| 2 | ✅ Done | Groq → structured ContentPlan + Scene JSON |
| 3 | ⏳ Planned | Scene → Google AI Studio / Gemini → visual assets + B-roll |
| 4 | ⏳ Planned | Script → ElevenLabs → voiceover audio |
| 5 | ⏳ Planned | Visuals + voiceover → FFmpeg/MoviePy → MP4 |
| 6 | ⏳ Planned | Audio → faster-whisper → word-level subtitles → FFmpeg |

> **AI/Video generation is not fully operational yet.**
> The `/api/v1/generate` endpoint still queues a placeholder job.
> The `ContentPlanner` service is complete and unit-tested but not yet wired into the job pipeline.

---

## Setup

**1. Create a virtual environment:**
```bash
python -m venv .venv
```

**2. Activate (Windows):**
```powershell
.\.venv\Scripts\Activate.ps1
```

**3. Install dependencies:**
```bash
pip install -r requirements.txt
```

**4. Configure environment:**
```bash
copy .env.example .env
# Then edit .env and add your GROQ_API_KEY and GROQ_MODEL
```

---

## Running the Server

```bash
uvicorn app.main:app --reload
```

Available at `http://127.0.0.1:8000`
API docs at `http://127.0.0.1:8000/docs`

---

## Running Tests

```bash
python -m pytest
```

Tests do **not** require any API keys. All AI provider calls are mocked.

---

## Live Groq Smoke Test (requires API key)

```bash
python scripts/test_content_generation.py
```

Requires `GROQ_API_KEY` and `GROQ_MODEL` to be set in `.env`.

---

## API Endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| GET | `/health` | Health check |
| POST | `/api/v1/generate` | Queue a generation job (placeholder) |
| GET | `/api/v1/status/{job_id}` | Check job status |
| GET | `/api/v1/result/{job_id}` | Retrieve job result when complete |
| POST | `/api/v1/regenerate-scene` | Request scene regeneration (not yet implemented) |

---

## ContentPlan Schema

```json
{
  "title": "string",
  "hook": "string",
  "script": "string",
  "scenes": [
    {
      "scene_id": 1,
      "duration": 10.0,
      "narration": "string",
      "visual_prompt": "string",
      "on_screen_text": "string"
    }
  ]
}
```

The `visual_prompt` field is designed for Milestone 3 (Gemini image/video generation).
The `narration` field feeds Milestone 4 (ElevenLabs TTS) and Milestone 6 (faster-whisper captions).
