# Review Request — BE-SEC-002 m1/m2 follow-up: `_student_can_view_classroom` helper

**From:** backend-engineer
**To:** reviewer
**Date:** 2026-04-19
**Closes:** BE-SEC-002 m1/m2 (non-blocking follow-ups from `review-BE-SEC-002-maic-chat-idor.md`)

---

## What changed

**File:** `backend/apps/courses/maic_views.py`

Extracted `_student_can_view_classroom(user, classroom) -> bool` as the single
canonical visibility gate, replacing duplicated inline logic in two views.

### The problem (m1 + m2)

Two views shared the same visibility rules but with a divergence:

| View | Status gate | Manifest gate | Section/public gate |
|------|-------------|---------------|---------------------|
| `student_maic_classroom_detail` | ✅ checked | ✅ checked | ✅ checked |
| `student_maic_chat` (pre-fix) | ❌ missing | ❌ missing | ✅ checked |

This parity gap meant a classroom in `GENERATING` or `FAILED` status (or with
a not-ready audio manifest) could be used to seed chat context via the chat
endpoint, even though the detail endpoint correctly blocked it.

### The fix

```python
def _student_can_view_classroom(user, classroom) -> bool:
    """Single canonical gate — see docstring for full rules."""
    if classroom.status != "READY":
        return False
    manifest_status = (classroom.content or {}).get("audioManifest", {}).get("status")
    if manifest_status not in ("ready", "partial"):
        return False
    assigned = classroom.assigned_sections.all()
    student_section = getattr(user, "section_fk", None)
    if assigned.exists():
        return bool(student_section) and student_section in assigned
    return classroom.is_public
```

Both `student_maic_classroom_detail` and `student_maic_chat` now call this helper.
Old inline code fully removed (zero occurrences of the `can_view` variable in either view).

## Tests

New file: `backend/apps/courses/tests_maic_classroom_visibility.py` (13 unit tests)

- Status gate: DRAFT/GENERATING/FAILED/ARCHIVED → False (4 tests)
- Manifest gate: generating/pending/missing → False, ready/partial → True (5 tests)
- Section gate: no-section/wrong-section → False, correct-section → True (3 tests)
- Public gate: private/unassigned → False, public/unassigned → True (2 tests)

Tests are DB-free (no Django/Docker needed for import-level unit tests).

Existing regression tests (`tests/courses/test_maic_student_chat.py`) unaffected —
all fixtures already use `status="READY"` + `audioManifest.status="ready"`.

## Verification commands

```bash
# Unit tests (DB-free)
docker compose exec web pytest apps/courses/tests_maic_classroom_visibility.py -v

# Regression suite (DB required)
docker compose exec web pytest tests/courses/test_maic_student_chat.py -v
```

## Diff summary

| File | Change |
|------|--------|
| `apps/courses/maic_views.py` | +helper, simplified 2 views |
| `apps/courses/tests_maic_classroom_visibility.py` | new, 13 unit tests |

— backend-engineer
