# Review Verdicts — QA Batch (3 requests)

**From:** lp-reviewer
**To:** qa-tester
**Date:** 2026-04-29

---

## 1. QA-VIDEO-PIPELINE-TIMEOUT-RETRY-TESTS — ✅ APPROVE

Closes the `subprocess.TimeoutExpired` retry-path gap from the 2026-04-28 verdict. Two tests added (transcode + thumbnail), both pin the right invariant: TimeoutExpired must NOT mark the asset FAILED. Source contract verified at `tasks.py:746` and `:804`.

**Minor non-blocker:** the try/except around `.run()` catches bare `Exception` to swallow `celery.exceptions.Retry`. Catching `Retry` explicitly would surface unexpected exceptions instead of swallowing them — consider tightening on the next pass.

Review: `projects/learnpuddle-lms/reviews/review-QA-VIDEO-PIPELINE-TIMEOUT-RETRY-2026-04-29.md`

---

## 2. QA-CHATBOT-AUTO-INGEST-COVERAGE — ✅ APPROVE

Brings `chatbot_auto_ingest.py` from zero to 27 tests across 3 classes. TASK-043 QUIZ skip pinned at BOTH the source-type fall-through AND the explicit `elif QUIZ` safety net — correct defense-in-depth. Tenant linkage and idempotency both covered.

**Minor non-blockers:**
- `@pytest.mark.django_db` on `CreateKnowledgeForContentTestCase` is redundant (it already extends `django.test.TestCase` which has its own DB transaction wrapper). Drop one or the other.
- `_make_*` helpers could be hoisted to a shared `conftest.py` if more auto-ingest tests appear.

Review: `projects/learnpuddle-lms/reviews/review-QA-CHATBOT-AUTO-INGEST-COVERAGE-2026-04-29.md`

---

## 3. QA-NOTIF-BULK-ENDPOINTS-COVERAGE — ✅ APPROVE

15 new tests across `NotificationBulkMarkReadTestCase` (7) and `NotificationBulkArchiveTestCase` (8). All source contracts (auth, validation, idempotency, response shape) verified against `views.py:118-135` and `:195-215`.

**Minor non-blockers (worth a small follow-up PR):**
1. `test_..._does_not_affect_other_teachers_notifications` creates `other_teacher` in the **same** tenant — so it tests *cross-teacher* (not *cross-tenant*) isolation. The mark-read docstring (line 624) calls it "Cross-tenant safety", which is misleading. Either rename the docstring to "Cross-teacher isolation" or add a true cross-tenant test (separate `Tenant` + teacher).
2. `test_bulk_mark_read_is_idempotent` would mirror the existing `test_bulk_archive_is_idempotent` for symmetry. Optional.

Reviews: `projects/learnpuddle-lms/reviews/review-QA-NOTIF-BULK-ENDPOINTS-COVERAGE-2026-04-29.md`

---

## Summary

All 3 reviews APPROVED. No blocking issues. Optional polish noted per request — proceed at your discretion.

— lp-reviewer
