---
tags: [review, task/TASK-008, verdict/approve, reviewer/lp-reviewer, rereview]
created: 2026-04-20
---

# Re-review (r2): TASK-008 — Standardize Error Response Format

## Verdict: APPROVE

## Summary
Both blocking items from the r1 review are fully resolved.

- **M1 (tests)** — `backend/tests/test_exception_handler.py` now has ~26 tests
  across `TestSystemErrors`, `TestValidationErrors`, `TestNonDRFException`, and
  `TestFlattenDRFErrors`. Coverage is comprehensive (happy path + legacy-key
  transition + edge shapes + helper unit tests).
- **M2 (frontend back-compat)** — The handler now emits **both** `error` and
  `detail` as identical plain strings across all four response cases. This is
  exactly option 2 from r1's recommended fixes — the zero-risk transition path.
  `# TASK-012 transition: drop once frontend cleanup is done` markers on every
  `detail` line make future cleanup mechanical.

The handler is a cross-surface contract change, but with dual-key emission plus
dedicated regression tests that explicitly assert `"detail" in data and
data["detail"] == data["error"]`, the risk to existing frontend pages
(`SkillRadarPage`, `GamificationPage`, `VerifyEmailPage`, etc.) is now zero.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

**m1 — Case 1b can overwrite an existing `code` key (edge case, unlikely)**

`backend/utils/exception_handler.py:158-160` — when `response.data` is a dict
containing `"detail"` *and* other keys, the handler extracts the ErrorDetail's
`code` and writes it to `data["code"]`. If DRF (or a custom exception) had
already populated a different `data["code"]`, this would silently overwrite it.
In practice DRF doesn't do this, but worth a one-line guard:

```python
if code and code not in ("invalid", "error") and "code" not in data:
    data["code"] = str(code)
```

Not blocking — the scenario doesn't occur in stock DRF.

**m2 — `str(data)` on non-dict/non-list fallback (Case 4)**

`exception_handler.py:187` — if `response.data` is `None` this produces
`"None"` as the error string. Extremely unlikely (DRF doesn't emit `None`
responses), but a `response.data if response.data is not None else "Error"`
would be sturdier. Not blocking.

**m3 — Inconsistency with `utils/responses.py::error_response()` still open**

Carried over from r1. `error_response()` emits `{"error": {"message": ..., "code": ...}}`
(object) whereas this handler emits `{"error": "..."}` (string). Two different
`.error` shapes across the API. Recommend tracking under TASK-012 when the
frontend cleanup pass harmonises the consumer side.

## Positive Observations

- **Dual-key emission is the right choice.** Both keys present and equal string
  means every existing `.detail` consumer keeps working *and* new `.error`
  consumers work. True zero-risk transition.
- **Transition markers.** `# TASK-012 transition: drop once frontend cleanup is done`
  on every `detail` line makes the cleanup step a literal delete-pass. Excellent
  forward-planning.
- **Test coverage is strong.** 26 tests, organized by response category, with
  dedicated `*_legacy_detail_key` and `*_detail_is_plain_string` tests verifying
  the transition contract. `TestFlattenDRFErrors` also covers nested serializer
  errors (`address.city`) and scalar fallback — those are easy to forget.
- **Docstring clarity.** The module docstring now documents the four response
  cases with expected shapes *and* explains the transition. A new dev can
  understand the contract without reading the tests.
- **`ErrorDetail` → `str` coercion preserved.** Still correctly avoids leaking
  DRF's internal type into JSON.
- **Status code and headers preserved.** Handler only mutates `response.data`.

## Decision
**APPROVE.** Ready to merge. The minor issues (m1–m3) are all small follow-ups
that don't block this ship. Good re-work — the response to the first review was
thoughtful and complete.

---

Reviewer: lp-reviewer
