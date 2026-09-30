from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List


class Scene(BaseModel):
    """A single visually coherent segment of the video."""
    scene_id: int = Field(..., ge=1, description="Unique positive scene identifier")
    duration: float = Field(..., ge=0.0, description="Duration of this scene in seconds")
    narration: str = Field(..., min_length=1, description="Spoken narration for this scene")
    visual_prompt: str = Field(..., min_length=1, description="Detailed visual-generation prompt for Gemini")
    on_screen_text: str = Field(..., min_length=1, description="Short text shown on screen during this scene")


class ContentPlan(BaseModel):
    """
    Structured content plan produced by the Gemini content planner.
    Designed to feed downstream pipeline stages:
      - visual_prompt  → Milestone 3: Google AI Studio / Gemini image/video generation
      - narration      → Milestone 4: ElevenLabs TTS
      - scenes         → Milestone 5: FFmpeg / MoviePy video assembly
      - narration      → Milestone 6: faster-whisper word-level captions
    """
    title: str = Field(..., min_length=1, description="Compelling video title")
    hook: str = Field(..., min_length=1, description="Attention-grabbing opening line for the first few seconds")
    script: str = Field(..., min_length=1, description="Full spoken script for the video")
    scenes: List[Scene] = Field(..., min_length=1, description="Ordered list of visual scenes")

    @field_validator("scenes")
    @classmethod
    def scenes_must_have_unique_ids(cls, scenes: List[Scene]) -> List[Scene]:
        ids = [s.scene_id for s in scenes]
        if len(ids) != len(set(ids)):
            raise ValueError("All scene_id values must be unique")
        return scenes

    @model_validator(mode="after")
    def validate_duration_coverage(self) -> "ContentPlan":
        """
        Scenes must collectively produce a non-zero total duration.
        The caller (ContentPlanner) checks proximity to requested duration.
        """
        total = sum(s.duration for s in self.scenes)
        if total <= 0:
            raise ValueError("Total scene duration must be greater than zero")
        return self

    def total_duration(self) -> float:
        return sum(s.duration for s in self.scenes)
