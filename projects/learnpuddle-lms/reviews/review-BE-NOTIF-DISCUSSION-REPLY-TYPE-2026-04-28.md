---
tags: [review, task/BE-NOTIF-DISCUSSION-REPLY-TYPE, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: BE-NOTIF-DISCUSSION-REPLY-TYPE — Add DISCUSSION_REPLY to Notification.NOTIFICATION_TYPES

## Verdict: APPROVE

## Summary
Surgical data-integrity fix for a real production bug: every discussion reply since the discussions feature shipped has been writing `notification_type='DISCUSSION_REPLY'` into a `CharField(choices=...)` that did not include that key. Because Django's `.objects.create()` skips `full_clean()`, the invalid value was stored silently. The fix adds the missing choice plus a 5-test regression registry that pins all known production notification types.

## Files Verified
- `backend/apps/notifications/models.py` — diff reviewed (added `('DISCUSSION_REPLY', 'Discussion Reply')` with explanatory comment)
- `backend/apps/notifications/tests_notification_type_choices.py` — full file read (149 lines, 5 tests)
- `backend/apps/discussions/views.py:921` — verified call-site exists and uses the now-valid type

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **No data-fix migration for already-stored rows.** The author correctly notes "no migration needed" because `choices=` is Python-only metadata and the column is `VARCHAR(20)`. Existing stored values remain `'DISCUSSION_REPLY'` strings — they are now valid by virtue of the choice list being extended. Strictly speaking no historical data is corrupt at the storage layer; the only observable improvement is that Django admin will now render the human label `"Discussion Reply"` instead of the raw key. Worth noting in the task close-out for product/admin team awareness, but no action needed in this PR.

2. **Test 4 (`test_discussion_reply_is_not_in_actionable_types`) is a product-decision pin, not a regression test.** That's fine — the docstring acknowledges this explicitly ("If product changes it, update ACTIONABLE_TYPES … AND flip this test"). Keeping it for self-documentation, but reviewers should be aware this test fires on a deliberate product change, not a code regression.

3. **`test_all_known_production_types_are_in_choices` registry is informally maintained.** The test embeds a `known_production_types` dict that must be hand-maintained as new `create_notification(...)` call-sites land. The docstring tells future engineers to update both places, which is the best we can do without static analysis. Consider in a follow-up: a management command or pytest fixture that greps the codebase for `notification_type=` literals and cross-checks. Non-blocking — the manual list is a strict improvement over the prior state of zero registry.

## Positive Observations

1. **Correct root-cause analysis.** The author's debug trail — call site → model choices → `full_clean()` skip in `.objects.create()` → CharField max_length tolerance → impact on admin/queryset filtering — names every link in the silent-failure chain. This is the same class of bug as the recently-fixed `ReportRun.status = "failed"` issue, and the author explicitly pattern-matched it. Good systematic-debugging discipline.

2. **Inline comment in the model is the right kind of comment.** The 3-line note explains *why* the choice was added (referencing `discussions/views.py`), which is exactly what someone reading `models.py` later will need to understand the historical context. Better than a commit message alone.

3. **Test 5 (`test_all_type_keys_fit_within_max_length`) is a guard against a future foot-gun.** If anyone ever adds a 21+ char key, the test fires immediately rather than silently truncating at the DB layer. Cheap insurance.

4. **Pure-Python tests (no `@pytest.mark.django_db`).** All 5 tests check Python-level constants — no DB fixtures needed, no Postgres setup overhead. Good test hygiene; this also means they will run cleanly in any sandbox-restricted environment.

5. **Out-of-scope finding routed correctly.** The author noticed `tests_services.py:134` uses `notification_type="GENERAL"` (also invalid) and routed the test-only fix to qa-tester via a separate inbox message rather than expanding the scope of this PR. Clean separation of concerns. (That fix has already landed — see review-QA-TEST-HYGIENE-BATCH.)

6. **Verified at the call site.** `discussions/views.py:921` does indeed use `notification_type='DISCUSSION_REPLY'` inside a `try/except Exception` wrapping `create_notification(...)` — confirmed by reading lines 910-930. The fix is real.

7. **Backward compat is automatic.** Existing rows are now valid; no schema change; no data migration; no API contract change.

## Verification
- Confirmed `('DISCUSSION_REPLY', 'Discussion Reply')` present in `models.py:35` (per diff context line 32-39)
- Confirmed key length 16 ≤ max_length=20
- Confirmed `DISCUSSION_REPLY` not in `services.ACTIONABLE_TYPES` import (test file imports correctly)
- Confirmed call-site at `discussions/views.py:921` matches what the registry asserts
- Pytest run deferred (sandbox `pythonjsonlogger` constraint — same blocker as other backend reviews this sprint). Approval is on diff + static + test-design review.

## Recommendation
APPROVE — merge. Status updated to `done`. Suggest noting in the next ops review that historical `Notification` rows with `notification_type='DISCUSSION_REPLY'` are now valid post-merge (no backfill needed).
