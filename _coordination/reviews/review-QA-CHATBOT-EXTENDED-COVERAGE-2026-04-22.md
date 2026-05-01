---
tags: [review, task/QA-CHATBOT-EXTENDED-COVERAGE, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-22
---

# Review: QA-CHATBOT-EXTENDED-COVERAGE — 20 new tests in apps/chatbot/tests_chatbot_extended.py

## Verdict: APPROVE

## Summary
20 net-new tests across 10 `TestCase` classes close real gaps left after the
2026-04-21 chatbot security audit: validation-error body shape, course-scope
guard DoesNotExist branch, SUPER_ADMIN bypass, PII absence in audit log +
logger, history access rules, pagination clamping, 30-day window base filter,
serializer PII guarantee, and rate-limit key bucketing. All additive, no
modifications to existing `tests_chatbot.py`. Ready to land.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Class count in QA note** — the inbox message claims "8 classes", but
   the file actually contains **10** `TestCase` classes (verified via
   `grep ^class Test` → 10 matches at lines 101, 145, 180, 238, 295, 355,
   485, 540, 589, 632). Test count (20) matches the stated total, so this
   is only a memo hygiene issue. Non-blocking.

2. **Sandbox could not execute `pytest`** — per the now-established
   reviewer/qa-tester/backend-security sandbox limit, the tests were
   verified statically: patch-target module paths resolve
   (`apps.chatbot.views.log_audit`, `apps.chatbot.views.Course`,
   `apps.chatbot.views.time`), and the pagination clamping math
   (`max(1, min(100, int(param)))`) maps 1:1 to the view. CI will be the
   first live run. Flag — not a defect.

3. **Deferred coverage list is appropriate.** qa-tester correctly
   identified three deferred items:
   - 401 unauthenticated case (requires full URL routing + middleware).
   - `get_provider()` dual-failure → Stub path (needs `DEBUG=True`
     override).
   - `ChatQuery.error` population on `semantic_search()` exception —
     this is a **real code smell** flagged as a *possible backend bug*:
     `rag_service.py` swallows the exception into `chunks=[]` but never
     populates `error` on the `RAGAnswer`. Recommend backend-engineer
     open a follow-up ticket to either (a) set `error="search_failed"`
     on the RAGAnswer, or (b) document that swallow-to-empty is the
     contract. Non-blocking for this review; **routed to
     backend-engineer** as a follow-up.

## Positive Observations

- **PII tests use sentinel strings** (`SUPER-SECRET-...`). Zero
  false-negative risk and the assertions check *both* dict keys and
  values — correct belt-and-braces for audit log PII.
- **Rate-limit tests use fixed epoch math** (`1_700_000_000.0` +
  `patch("apps.chatbot.views.time")`) — deterministic bucket rotation
  checks without wall-clock flake.
- **`TestSuperAdminCourseScopeBypass`** covers *both* the ask and
  delete paths for cross-tenant SUPER_ADMIN — the exact shape of
  previous tenant-isolation bugs we care about.
- **`TestHistoryListViewAccess`** includes the "teacher passes
  `?user_id=` → silently ignored" case, which is the IDOR-adjacent
  gotcha where devs forget to strip admin-only filter params for
  non-admin callers.
- **`TestHistoryListViewPagination`** is the most surgical of the
  batch — non-int / out-of-range page + page_size values are exactly
  the fuzz surface a pentester hits.
- Existing `tests_chatbot.py` (25 tests) is untouched — no behaviour
  or coverage regression.

## Follow-ups Routed

- **backend-engineer** — `rag_service.py` `ChatQuery.error` population
  when `semantic_search()` raises. File a ticket or document the
  swallow-to-empty contract.

## Merge Recommendation

Ship as-is. No changes required.

— reviewer (lp-reviewer)
