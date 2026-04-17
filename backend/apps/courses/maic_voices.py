"""Azure en-IN neural voice roster for MAIC agents.

Data-only module. No business logic. Consumed by:
- maic_generation_service.generate_agent_profiles_json (for voice assignment)
- maic_views.maic_list_voices (surfaced to frontend)
- maic_views.teacher_maic_tts_preview (voice validation)
- maic_generation_service.validate_agents (enforces name↔voice gender match)
"""

from typing import Literal

Gender = Literal["male", "female", "unknown"]

AZURE_IN_VOICES = [
    # Suits lists are intentionally broad so at least one voice of each
    # gender covers every role — otherwise the validator deadlocks on
    # roles with only one gender available (e.g. "Mr. Kunal" as TA used
    # to have zero male voice candidates and the auto-fixer had nothing
    # to swap in).
    {"id": "en-IN-PrabhatNeural",   "gender": "male",   "tone": "authoritative", "age": "adult",       "suits": ["professor", "moderator"]},
    {"id": "en-IN-NeerjaNeural",    "gender": "female", "tone": "warm",          "age": "adult",       "suits": ["teaching_assistant", "professor"]},
    {"id": "en-IN-AaravNeural",     "gender": "male",   "tone": "friendly",      "age": "young adult", "suits": ["student", "teaching_assistant"]},
    {"id": "en-IN-AashiNeural",     "gender": "female", "tone": "youthful",      "age": "young adult", "suits": ["student", "teaching_assistant"]},
    {"id": "en-IN-KavyaNeural",     "gender": "female", "tone": "energetic",     "age": "adult",       "suits": ["teaching_assistant", "moderator", "professor"]},
    {"id": "en-IN-KunalNeural",     "gender": "male",   "tone": "thoughtful",    "age": "adult",       "suits": ["moderator", "student", "teaching_assistant"]},
    {"id": "en-IN-RehaanNeural",    "gender": "male",   "tone": "playful",       "age": "young adult", "suits": ["student"]},
]

VOICE_BY_ID = {v["id"]: v for v in AZURE_IN_VOICES}


# ─── First-name → gender heuristic ───────────────────────────────────────────
#
# Conservative lookup table of common Indian first names. Used only to catch
# obvious voice/name mismatches (e.g. "Dr. Priya Reddy" assigned a male voice).
# Names not in this table fall back to `unknown`, which skips the validation.
# Honorifics (Dr./Prof./Ms./Mr./Mrs.) are stripped before lookup.

_FEMALE_NAMES: frozenset[str] = frozenset({
    # Pan-Indian common femme names
    "priya", "anjali", "neha", "kavya", "meera", "ritu", "aashi", "aditi",
    "ananya", "divya", "pooja", "sneha", "shreya", "kriti", "swati", "nisha",
    "deepa", "lakshmi", "sunita", "asha", "vidya", "kamala", "seema",
    "rashmi", "preeti", "anita", "geeta", "radha", "sita", "lalita",
    "aisha", "fatima", "zara", "maya", "riya", "tanya", "isha", "ira",
    "saanvi", "mira", "tara", "uma", "indira", "kiran", "padma", "rekha",
    "rupa", "shanti", "sonia", "sophia", "sara", "amrita", "jaya", "jyoti",
    "leela", "malini", "nalini", "nandini", "naina", "nithya", "parvati",
    "rani", "roshni", "sangeeta", "savita", "shakuntala", "shilpa",
    "shubha", "simran", "smita", "sudha", "sushma", "usha", "vandana",
    "veena", "yamini",
})

_MALE_NAMES: frozenset[str] = frozenset({
    # Pan-Indian common masc names
    "arjun", "rahul", "vikram", "prabhat", "aarav", "kunal", "rehaan",
    "karan", "rohan", "aditya", "siddharth", "akash", "varun", "raj",
    "ravi", "amit", "sanjay", "anil", "suresh", "rakesh", "ramesh", "mohan",
    "vijay", "ashok", "ajay", "manish", "nikhil", "abhishek", "sameer",
    "pranav", "abhay", "arun", "deepak", "gopal", "harish", "jagdish",
    "kamal", "kishore", "krishna", "mahesh", "mukesh", "naveen", "nitin",
    "pawan", "prakash", "rajesh", "rajiv", "sachin", "sandeep", "sohan",
    "sunil", "tarun", "uday", "venkat", "vinay", "vishal", "vivek",
    "yash", "zubin", "imran", "farhan", "arjit", "dev", "shiv", "surya",
    "reyansh", "vihaan", "kabir", "ishaan", "dhruv", "advait", "rishabh",
    "shaan", "kartik", "ayush", "harsh",
})

_HONORIFICS: frozenset[str] = frozenset({"dr", "dr.", "prof", "prof.", "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "miss", "shri", "smt", "smt."})


def voices_for_role(role: str) -> list[dict]:
    """All voices whose `suits` list contains the given role."""
    return [v for v in AZURE_IN_VOICES if role in v["suits"]]


def voices_for_gender(gender: str) -> list[dict]:
    """All voices matching the given gender ('male' or 'female').

    Other values (e.g. 'unknown') return an empty list — callers should
    not filter on unknown gender.
    """
    if gender not in {"male", "female"}:
        return []
    return [v for v in AZURE_IN_VOICES if v["gender"] == gender]


def is_valid_voice(voice_id: str) -> bool:
    return voice_id in VOICE_BY_ID


def voice_matches_role(voice_id: str, role: str) -> bool:
    v = VOICE_BY_ID.get(voice_id)
    return v is not None and role in v["suits"]


def infer_gender_from_name(name: str) -> Gender:
    """Best-effort gender inference from an Indian first name.

    Strips honorifics (Dr./Prof./Mr./Ms./Mrs./Shri/Smt.), takes the first
    remaining token, lowercases, and looks it up in the curated tables.
    Returns 'unknown' for names we can't confidently classify — callers
    should skip the gender check in that case rather than guessing.
    """
    if not name:
        return "unknown"
    tokens = [t for t in name.strip().split() if t]
    # Drop leading honorifics (may be more than one, e.g. "Dr. Prof. Priya")
    while tokens and tokens[0].lower() in _HONORIFICS:
        tokens.pop(0)
    if not tokens:
        return "unknown"
    first = tokens[0].lower().strip(".,-")
    if first in _FEMALE_NAMES:
        return "female"
    if first in _MALE_NAMES:
        return "male"
    return "unknown"
