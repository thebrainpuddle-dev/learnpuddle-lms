"""CG-P1-8 (2026-04-28): regression — every role in `AZURE_IN_VOICES` MUST
have at least one MALE and one FEMALE candidate.

Why: `_auto_fix_voice_gender_mismatches` triggers when the LLM picks a
voice whose gender doesn't match the assigned agent's first-name gender
(e.g. "Mr. Kunal Reddy" with `en-IN-NeerjaExpressiveNeural`). The fixer
walks `voices_for_role(role)` filtered by the inferred gender, looking
for an unused match. If the role pool is missing that gender entirely
(as `teaching_assistant` was after the CG-P1-1 trim), there's nothing
to swap to → 3 retries → 500 on `/agent-profiles/`.

Test guards the contract: every role used by the LLM (i.e. every role
that appears in any voice's `suits` list) MUST have ≥1 male and ≥1
female candidate.
"""
from collections import defaultdict

from apps.courses.maic_voices import AZURE_IN_VOICES, voices_for_role


def _all_roles() -> set[str]:
    roles: set[str] = set()
    for v in AZURE_IN_VOICES:
        roles.update(v["suits"])
    return roles


def test_every_role_has_male_and_female_voice():
    """Every role advertised in `suits` lists MUST have both genders covered.

    Failure here means a future trim regressed the auto-fixer's ability to
    swap on gender mismatch. The fix is to add the missing gender to that
    role's `suits` (NOT to silently drop the role from the catalog).
    """
    matrix: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {"male": [], "female": []}
    )
    for v in AZURE_IN_VOICES:
        for role in v["suits"]:
            matrix[role][v["gender"]].append(v["id"])

    missing: list[str] = []
    for role, by_gender in matrix.items():
        if not by_gender["male"]:
            missing.append(f"role {role!r}: NO male voice")
        if not by_gender["female"]:
            missing.append(f"role {role!r}: NO female voice")

    assert not missing, "Voice coverage regressed:\n  - " + "\n  - ".join(missing)


def test_voices_for_role_returns_at_least_one_per_known_role():
    """`voices_for_role(role)` must never return an empty list for a role
    that appears in `AZURE_IN_VOICES[*].suits`."""
    for role in _all_roles():
        candidates = voices_for_role(role)
        assert candidates, f"voices_for_role({role!r}) returned empty"


def test_known_failure_replay_kunal_reddy_male_TA():
    """Replays the 2026-04-28 prod failure shape: a male first-name
    assigned the TA role must have at least one male candidate available
    after the gender filter — otherwise auto-fix is impossible."""
    male_TA = [v for v in voices_for_role("teaching_assistant") if v["gender"] == "male"]
    assert male_TA, (
        "No male voice available for teaching_assistant role. "
        "This is the exact CG-P1-1 regression that broke /agent-profiles/."
    )


def test_known_failure_replay_priya_female_student_rep():
    """Symmetric guard: female first-name as student_rep needs ≥1 female
    candidate."""
    female_rep = [v for v in voices_for_role("student_rep") if v["gender"] == "female"]
    assert female_rep, "No female voice available for student_rep role."
