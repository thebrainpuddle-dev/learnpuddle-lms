# Review Request — BE Follow-ups: RAG Service Error Field + TeacherProgress Docstring

**From:** backend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-22
**Re:** Non-blocking follow-ups from `REVIEW-VERDICT-BE-CALENDAR-CALLBACK-AND-COMPLETION-RATE-2026-04-22.md`

---

## Summary

Two non-blocking follow-ups addressed. No production behavior change beyond the `error` field
now being populated on search failure (which was already the case — see Finding A below).

---

## Follow-up A — chatbot rag_service exception swallow

**File:** `backend/apps/chatbot/rag_service.py`
**Status:** Already applied — no code changed in this session.

**What was found:** The fix was already present from a prior session:
- `RAGAnswer.error: Optional[str] = None` declared at line 74 with explanatory comment.
- `except Exception` block at line 196 returns `RAGAnswer(error="search_failed", ...)` and
  keeps `chunks=[]` intact so existing fallback behavior is preserved.
- `logger.exception(...)` at line 198 logs at WARN level with `tenant=` and `latency_ms=`
  (no question text per PII policy).
- The empty-index fast-path at line 229 correctly leaves `error=None` (not a failure).

No code modified. Verified by reading the file.

---

## Follow-up B — TeacherProgress course-vs-content convention docstring

**File:** `backend/apps/progress/models.py`
**Lines changed:** 31–33

**What changed:** Added two Python inline comments on `TeacherProgress.course` and
`TeacherProgress.content` fields making the null-content convention explicit:

```python
# course-level progress row: content=None (one row per teacher+course).
course = models.ForeignKey('courses.Course', ...)
# content=None → course-level aggregate row; content≠None → per-content progress row.
content = models.ForeignKey('courses.Content', ..., null=True, blank=True)
```

No model field attributes (`null`, `blank`, `related_name`, etc.) were changed.
`makemigrations --check` will produce no new migration (comment-only change).

---

## Production behavior impact

**No production behavior change** beyond the `error` field now being populated on search
failure — and that was already the case before this session. The `TeacherProgress` change
is a pure comment/documentation change with zero runtime impact.

---

**No git commits. No git add. No git push.**

— backend-engineer
