---
tags: [review, task/TASK-008, verdict/request-changes, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: TASK-008 — Standardize Error Response Format

## Verdict: REQUEST_CHANGES

## Summary

The custom exception handler in `backend/utils/exception_handler.py` is
implemented correctly and registered properly. However, the change ships
without any tests for the handler itself, and the task claims
"zero-risk change" while in practice it's a **cross-surface contract change**
affecting every DRF error response the frontend has ever read. Before
landing this we need (a) regression tests for the handler, and (b) evidence
that the frontend's error-reading code is safe under the new
`{"error": ...}` shape — because several files still read
`response.data.detail` without a fallback.

## Critical Issues

None (the logic is correct, no security/data-loss risk).

## Major Issues

### M1 — No tests for the exception handler

**File**: no `backend/tests/test_exception_handler.py` exists

This is an EXCEPTION_HANDLER — every 401/403/404/405 response in the API
funnels through it. It needs targeted tests. Minimum coverage:

1. Unauthenticated request → `{"error": "..."}` with 401 (not `{"detail": ...}`)
2. `NotFound` raised in a view → `{"error": "..."}` with 404
3. `PermissionDenied` → `{"error": "..."}` with 403
4. `MethodNotAllowed` (e.g. PUT on a GET-only endpoint) → `{"error": "..."}` with 405
5. Serializer validation error with a per-field dict → **unchanged** `{"field": ["msg"]}` shape with 400
6. `APIException(detail={"non_field_errors": [...]})` → behaviour documented
7. Non-DRF exception (e.g. raw `ValueError`) → handler returns `None` → DRF falls back to Django's 500 handler (confirm this path doesn't regress)

Without these tests, the next developer to touch the handler has no way to
know what contracts they're preserving.

### M2 — Frontend compatibility is not actually verified

The task note says "Frontend error handling — pending TASK-012". That's
fine as a future cleanup, but the **current** frontend has 50+ sites that
read `error.response.data.detail`. Most use a fallback chain
(`.error || .detail`), but at least one file reads `.detail` only:

- `frontend/src/pages/auth/VerifyEmailPage.tsx:31`
- (plus any others — please grep and enumerate)

Until TASK-012 lands, any page reading `.detail` only will silently show
"undefined" or fall through to a generic error. Action required **one of**:

1. Land the small frontend patch in this PR to change `.detail`-only sites to `.error || .detail`, OR
2. Temporarily have the handler emit BOTH keys (`{"error": "...", "detail": "..."}`) during the transition period, and remove `detail` once TASK-012 ships, OR
3. Delay merge until TASK-012 is ready so both land together.

Option 2 is my recommendation — it's the zero-risk path and makes the
handler genuinely backward-compatible.

## Minor Issues

### m1 — No logging / observability

**File**: `backend/utils/exception_handler.py`

The handler is the single chokepoint for every DRF error on the platform.
It's a perfect place to add a `logger.warning(...)` with request_id,
tenant, user, and status code for 5xx responses. Not required for this
task, but worth a TODO or a follow-up ticket — errors are currently
invisible unless Sentry is configured.

### m2 — Inconsistency between handler output and `utils/responses.py::error_response()`

**File**: `backend/utils/responses.py`

`error_response()` emits `{"error": {"message": "...", "code": "..."}}` —
an object — whereas the new handler emits `{"error": "..."}` — a string.
The frontend now has to handle both shapes (string *and* object under
`.error`). This is a consistency bug, not a correctness bug, but it makes
TASK-012's frontend consolidation harder. Consider either:

- Making the handler emit `{"error": {"message": "..."}}` to match, OR
- Updating `error_response()` to emit `{"error": "..."}` (breaking; more work).

No action required in this PR but flag it as a design question.

## Positive Observations

- **Correct delegation**: handler calls `exception_handler(exc, context)` first, so DRF's default conversions (Http404 → NotFound, etc.) still run.
- **Serializer-error preservation**: the `"detail" in response.data` check correctly skips per-field validation dicts. Good.
- **`ErrorDetail` → `str` coercion** (`str(detail_value)`) is the right move — avoids leaking DRF's internal type into JSON.
- **Settings registration** in `config/settings.py` `REST_FRAMEWORK` dict is correctly placed.
- **Status code and headers** are preserved (handler only mutates `response.data`).

## Ready to Merge

No — address M1 (tests) and M2 (frontend compatibility strategy) first.
m1 and m2 can be follow-ups.
