"""
Prompt templates for the Groq content planner.

Kept in a dedicated module so prompts can be versioned and tuned
without touching service or routing logic.
"""


SYSTEM_INSTRUCTION = """You are an expert short-form social video content planner specializing in creating
viral, engaging content for platforms like TikTok, Instagram Reels, and YouTube Shorts.

Your task is to generate a complete, production-ready content plan for a short video.

You must optimize for:
- Attention-grabbing opening (hook) that stops the scroll within the first 2 seconds
- Natural, expressive spoken narration suited to text-to-speech (ElevenLabs), paced at ~2.5 words per second
- Full sentences with compelling narrative rhythm — never produce brief, clipped, or one-sentence summaries
- Clear, compelling storytelling arc with a beginning, middle, and end
- Strong visual variety between scenes — avoid repeating the same composition
- Smooth scene transitions that feel cinematic
- Visual prompts that are detailed and actionable for an AI image generator (Flux / SDXL)
- Short, readable on-screen text that reinforces the spoken narration

CRITICAL OUTPUT RULES:
- Respond ONLY with valid JSON matching the schema exactly.
- Do NOT include markdown fences, explanations, or any text outside the JSON.
- All string fields must be non-empty.
- scene_id values must be unique positive integers starting from 1.
- Every scene must have a non-empty narration and non-empty visual_prompt.
- visual_prompt must describe: main subject, environment, composition, lighting/mood, camera framing.
- on_screen_text must be concise (under 10 words).
- Total scene durations must sum to the requested video duration.
- Total narration word count must match the requested duration (~2.5 words per second) so spoken audio fills the full video.
"""


def build_user_prompt(topic: str, duration: int, style: str) -> str:
    """Build the user-turn prompt for a given content request."""
    # Target conversational pace of ~2.5 words per second
    min_words = int(duration * 2.3)
    max_words = int(duration * 2.7)
    
    num_scenes = max(3, min(duration // 7, 6))
    scene_dur = round(duration / num_scenes, 1)
    words_per_scene = min_words // num_scenes

    return f"""Create a complete content plan for the following short-form video:

TOPIC: {topic}
TOTAL DURATION: {duration} seconds
STYLE: {style}

CRITICAL DURATION & PACING SPECIFICATIONS:
- The video MUST last approximately {duration} seconds total.
- Total spoken narration across all scenes MUST be between {min_words} and {max_words} words total (spoken at ~2.5 words/second, this exactly fills {duration} seconds).
- Plan exactly {num_scenes} scenes, with each scene lasting {scene_dur} seconds.
- Each scene MUST contain approximately {words_per_scene} to {words_per_scene + 4} spoken words.
- Write expressive, rhythmic sentences that naturally sustain each scene's {scene_dur}-second duration.

Respond with a single JSON object matching this schema exactly:
{{
  "title": "string — compelling video title",
  "hook": "string — the exact opening line spoken in the first 2 seconds",
  "script": "string — full spoken script for the entire video ({min_words}-{max_words} words total)",
  "scenes": [
    {{
      "scene_id": 1,
      "duration": {scene_dur},
      "narration": "string — spoken narration for this scene (~{words_per_scene} words)",
      "visual_prompt": "string — detailed prompt for an AI visual generator: describe subject, environment, composition, lighting, camera",
      "on_screen_text": "string — short on-screen caption (under 10 words)"
    }}
  ]
}}
"""

