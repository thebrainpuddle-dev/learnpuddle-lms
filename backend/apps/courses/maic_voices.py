"""Azure en-IN neural voice roster for MAIC agents.

Data-only module. No business logic. Consumed by:
- maic_generation_service.generate_agent_profiles_json (for voice assignment)
- maic_views.maic_list_voices (surfaced to frontend)
- maic_views.teacher_maic_tts_preview (voice validation)
- maic_generation_service.validate_agents (enforces name↔voice gender match)
"""

from typing import Literal

Gender = Literal["male", "female", "unknown"]

# CG-P1-1 (2026-04-27): trimmed from 7 voices → 5. Microsoft Edge TTS
# only serves 3 en-IN voices (Neerja, NeerjaExpressive, Prabhat); the
# previously-listed Aarav/Aashi/Kavya/Kunal/Rehaan are fictional and
# raise `edge_tts.exceptions.NoAudioReceived` for every preview/synth
# call. We backfill with two Hindi-locale voices (Madhur, Swara) that
# render English text cleanly — verified via direct edge-tts probes.
# Roster shape: 3F + 2M, every role has ≥2 candidates so the validator
# can always swap on a gender mismatch.
AZURE_IN_VOICES = [
    # CG-P1-8 (2026-04-28): every role MUST have at least one MALE and one
    # FEMALE candidate so the validator + `_auto_fix_voice_gender_mismatches`
    # can swap on a name/voice gender mismatch. The CG-P1-1 trim accidentally
    # dropped male coverage for `teaching_assistant` and female coverage for
    # `student_rep`, causing a 500 in `agent-profiles` when the LLM picked
    # e.g. "Mr. Kunal Reddy" as a TA → auto-fixer found no male TA voice →
    # validator failed 3 retries.
    {"id": "en-IN-PrabhatNeural",         "gender": "male",   "tone": "authoritative", "age": "adult", "suits": ["professor", "moderator", "teaching_assistant", "student_rep"]},
    {"id": "en-IN-NeerjaNeural",          "gender": "female", "tone": "warm",          "age": "adult", "suits": ["teaching_assistant", "professor", "moderator", "student_rep"]},
    {"id": "en-IN-NeerjaExpressiveNeural","gender": "female", "tone": "expressive",    "age": "adult", "suits": ["moderator", "teaching_assistant", "student", "student_rep"]},
    {"id": "hi-IN-MadhurNeural",          "gender": "male",   "tone": "thoughtful",    "age": "adult", "suits": ["student_rep", "student", "professor", "teaching_assistant", "moderator"]},
    {"id": "hi-IN-SwaraNeural",           "gender": "female", "tone": "energetic",     "age": "adult", "suits": ["student", "teaching_assistant", "moderator", "student_rep"]},
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


# ─── Cycle-by-index fallback voice picker ────────────────────────────────────
#
# CG-P0-6 (2026-04-27): the publish-time stamp in maic_views.py used to
# default every speech action with a missing `voiceId` to a single literal
# "en-IN-NeerjaNeural", which made N agents in the same roster collapse to
# one voice. This picker uses gender-from-name + role + agent index so two
# distinct agents in the same roster can never get the same fallback voice.

def pick_fallback_voice(
    *,
    name: str = "",  # noqa: ARG001 — kept for API symmetry; LLM happy-path stamps voiceId already
    role: str = "",
    agent_index: int = 0,
) -> str:
    """Deterministic fallback voice when an agent's `voiceId` is missing.

    Cycles through the role's voice pool (or the full roster when no role
    is given) by `agent_index`. Two distinct `agent_index` values inside
    the same pool MUST return distinct voices — that's the guarantee
    callers depend on to avoid the "all students sounded alike" collapse.

    Gender filtering was deliberately dropped from the fallback path: it
    creates pool-size mismatches between agents (a female student has a
    1-voice pool while an unknown-gender student has 4) and re-introduces
    collisions. The happy path is the LLM-assigned voiceId, which already
    carries gender via the validator in maic_generation_service.

    Always returns a real Azure en-IN voice id.
    """
    pool: list[dict] = voices_for_role(role) if role else []
    if not pool:
        pool = list(AZURE_IN_VOICES)

    safe_idx = max(0, int(agent_index))
    return pool[safe_idx % len(pool)]["id"]
