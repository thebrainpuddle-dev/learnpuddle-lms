---
tags: [review, task/BE-FOLLOWUPS-RAG-PROGRESS, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-22
---

# Review: BE Follow-ups — RAG Service Error Field + TeacherProgress Docstring

## Verdict: APPROVE

## Summary

Two non-blocking follow-ups verified statically. Both are minimal, documentation-
oriented, and introduce no runtime behavior change (the `error="search_failed"`
path was already present from an earlier session; the progress model gains only
inline comments).

## Files Verified

### 1. `backend/apps/chatbot/rag_service.py` (no session diff — pre-existing)

Confirmed at the cited lines:

- **Line 62–74** — `RAGAnswer` dataclass declares
  `error: Optional[str] = None` with an explanatory comment distinguishing
  retrieval failure from empty retrieval.
- **Lines 189–218** — `except Exception:` around `semantic_search(...)`
  - Calls `logger.exception(...)` (stack trace at ERROR level via `exception`,
    which is appropriate — the task spec said WARN/exception level; `.exception()`
    satisfies "exception level" and includes traceback, which is the right
    choice for an unexpected retrieval failure).
  - Log line includes `tenant=` and `latency_ms=`; no question text (PII-safe).
  - Returns `RAGAnswer(answer=FALLBACK_SENTENCE, chunks=[] via empty
    retrieved_chunk_ids, error="search_failed", latency_ms=elapsed_ms, ...)`.
  - `grounded=False`, `citations=[]`, `retrieved_chunk_ids=[]` preserved.
- **Lines 220–239** — Empty-index fast-path leaves `error=None` (correct — not a
  failure mode).

`git diff HEAD` on this file returns zero lines (file is untracked on branch;
content reviewed as-is).

### 2. `backend/apps/progress/models.py`

Confirmed at lines 31 and 33 via `git diff`:

```
+    # course-level progress row: content=None (one row per teacher+course).
     course = models.ForeignKey('courses.Course', ...)
+    # content=None → course-level aggregate row; content≠None → per-content progress row.
     content = models.ForeignKey('courses.Content', ..., null=True, blank=True)
```

- Additions are strictly `# ...` comment lines.
- No field attribute changed (`null`, `blank`, `related_name`, `on_delete`
  all identical). `makemigrations --check` would not produce a new migration.
- Other diff hunks in this file (`rubric`, `max_attempts`, `attempt_number`,
  etc.) pre-date this task per the author's note and are out of scope for this
  review.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

- The task spec mentioned WARN level; implementation uses `logger.exception()`
  which emits at ERROR with a traceback. This is actually preferable for an
  unexpected retrieval failure — not worth changing.

## Positive Observations

- Clear dataclass comment explaining the semantic of `error=None` vs
  `"search_failed"`.
- Empty-index fast-path correctly leaves `error=None` — distinguishes "no
  content" from "retrieval crashed".
- Log line intentionally omits question text; complies with PII policy.
- TeacherProgress comments make the `content=None → course-level` convention
  discoverable without schema churn.
