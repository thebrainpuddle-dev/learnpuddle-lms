# QA — Chatbot App Extended Test Coverage (20 tests)

**From:** qa-tester
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-22
**File:** `backend/apps/chatbot/tests_chatbot_extended.py` (new)

---

## Summary

Added 20 new tests in 8 `TestCase` classes to `tests_chatbot_extended.py`,
filling gaps identified against the existing `tests_chatbot.py` (25 tests).
The existing file is unmodified.

---

## Gap coverage table

| Class | Count | Gap filled |
|---|---|---|
| `TestAskViewValidationResponses` | 3 | Full HTTP 400 body has `error="QUESTION_TOO_LONG"`; `top_k=0` → 400; `top_k=11` → 400 |
| `TestCourseScopeGuardNotFound` | 1 | `_check_course_scope` with non-existent course → 404 `NOT_FOUND` |
| `TestSuperAdminCourseScopeBypass` | 2 | `SUPER_ADMIN` skips course DB query; `SUPER_ADMIN` can delete other user's row |
| `TestAskViewPIIInAuditLog` | 1 | `log_audit` `changes` dict has no `question` key and no question text value |
| `TestAskViewPIIInLogger` | 1 | `apps.chatbot.views` logger never emits question text (separate from rag_service logger test) |
| `TestHistoryListViewAccess` | 3 | Teacher sees only own rows; admin `?user_id=` filter applied; teacher `?user_id=` silently ignored |
| `TestHistoryListViewPagination` | 4 | `page_size=0` → 1; `page_size=200` → 100; non-int page → 1; non-int page_size → 20 |
| `TestHistoryListView30DayWindow` | 1 | Base queryset has `created_at__gte` (30d cutoff) filter |
| `TestChatQueryHistorySerializerNoPII` | 1 | Serializer output has no `"question"` key |
| `TestRateLimitKeyBucketing` | 3 | Same-window = same key; different windows = different key; per-user isolation |

**Total: 20 tests, 8 classes**

---

## Key design choices

- All view functions called directly with `MagicMock(spec=DRFRequest)` following
  the pattern established in `tests_chatbot.py`.
- All DB / LLM calls mocked via `@patch` on `apps.chatbot.views.*`.
- PII tests use sentinel strings (`"SUPER-SECRET-..."`) — zero false-negative risk.
- Rate limit key tests use a fixed epoch (`1_700_000_000.0`) and `patch("apps.chatbot.views.time")`.

---

## What remains NOT tested (deferred)

- Unauthenticated requests → 401 (requires full Django test client + running middleware stack; can be added via pytest-django `@pytest.mark.django_db` + URL routing in a future pass).
- `get_provider()` fallback chain when both OpenRouter and Ollama fail → Stub (requires `DEBUG=True` override; straightforward extension).
- `ChatQuery.error` field population when `semantic_search()` raises (possible bug: `rag_service.py` swallows the exception into `chunks=[]` but never sets `error` on the RAGAnswer — recommend backend-engineer review).

---

## Verification (static — Docker unavailable in sandbox)

- `grep -c "def test_"` = 20 ✅
- All patch targets resolve (`apps.chatbot.views.*`, `apps.chatbot.views.Course`) ✅
- View logic for pagination clamping traced: `max(1, min(100, int(param)))` matches assertions ✅
- PII log assertions check both dict keys and values ✅
- Rate limit bucket math verified with fixed epoch values ✅

---

**No git commits. No git add. No git push.**

— qa-tester
