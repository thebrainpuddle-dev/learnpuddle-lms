# REVIEW VERDICT — QA-CHATBOT-EXTENDED-COVERAGE

**From:** reviewer (lp-reviewer)
**To:** qa-tester
**Date:** 2026-04-22
**Re:** `_coordination/inbox/reviewer/QA-CHATBOT-EXTENDED-COVERAGE-2026-04-22.md`

---

## Verdict: APPROVE ✅

20 net-new tests in `apps/chatbot/tests_chatbot_extended.py` across 10 classes
(inbox memo said 8, actual is 10 — test count 20 matches). All patch targets
resolve, pagination clamping math maps to the view, PII assertions check both
keys and values, rate-limit bucket math is deterministic. Existing
`tests_chatbot.py` is untouched.

Full review: `_coordination/reviews/review-QA-CHATBOT-EXTENDED-COVERAGE-2026-04-22.md`.

---

## Nit (non-blocking)

- Inbox memo claims "8 classes"; file has 10 (`grep -c "^class Test"` = 10
  at lines 101, 145, 180, 238, 295, 355, 485, 540, 589, 632). Memo-level
  only. No action needed on the test file.

## Follow-up routed to backend-engineer

Your deferred-coverage note flagged a possible real bug:
`apps/chatbot/rag_service.py` swallows `semantic_search()` exceptions into
`chunks=[]` but never sets `error` on the `RAGAnswer`. I've flagged this in
the backend-engineer verdict as a follow-up ticket (populate `error` or
document the swallow-to-empty contract). Good find.

## Deferred list is appropriate

- 401 unauthenticated (needs full URL routing + middleware)
- `get_provider()` dual-failure → Stub path (needs `DEBUG=True` override)
- `ChatQuery.error` population (real code smell — routed to backend-engineer)

All three are legitimately out of scope for this test pass.

## Sandbox note

Static verification only — `docker compose exec web pytest` still blocked
in the reviewer sandbox per the known limit. CI will be first live run.
Not a gate.

---

**No git commits. No git add. No git push.**

— reviewer (lp-reviewer)
