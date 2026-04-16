"""Azure en-IN neural voice roster for MAIC agents.

Data-only module. No business logic. Consumed by:
- maic_generation_service.generate_agent_profiles_json (for voice assignment)
- maic_views.maic_list_voices (surfaced to frontend)
- maic_views.teacher_maic_tts_preview (voice validation)
"""

AZURE_IN_VOICES = [
    {"id": "en-IN-PrabhatNeural",   "gender": "male",   "tone": "authoritative", "age": "adult",       "suits": ["professor"]},
    {"id": "en-IN-NeerjaNeural",    "gender": "female", "tone": "warm",          "age": "adult",       "suits": ["teaching_assistant", "professor"]},
    {"id": "en-IN-AaravNeural",     "gender": "male",   "tone": "friendly",      "age": "young adult", "suits": ["student"]},
    {"id": "en-IN-AashiNeural",     "gender": "female", "tone": "youthful",      "age": "young adult", "suits": ["student"]},
    {"id": "en-IN-KavyaNeural",     "gender": "female", "tone": "energetic",     "age": "adult",       "suits": ["teaching_assistant", "moderator"]},
    {"id": "en-IN-KunalNeural",     "gender": "male",   "tone": "thoughtful",    "age": "adult",       "suits": ["moderator", "student"]},
    {"id": "en-IN-RehaanNeural",    "gender": "male",   "tone": "playful",       "age": "young adult", "suits": ["student"]},
]

VOICE_BY_ID = {v["id"]: v for v in AZURE_IN_VOICES}


def voices_for_role(role: str) -> list[dict]:
    """All voices whose `suits` list contains the given role."""
    return [v for v in AZURE_IN_VOICES if role in v["suits"]]


def is_valid_voice(voice_id: str) -> bool:
    return voice_id in VOICE_BY_ID


def voice_matches_role(voice_id: str, role: str) -> bool:
    v = VOICE_BY_ID.get(voice_id)
    return v is not None and role in v["suits"]
