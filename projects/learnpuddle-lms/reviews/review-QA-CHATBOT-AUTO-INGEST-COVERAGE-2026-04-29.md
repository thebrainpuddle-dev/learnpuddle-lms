---
tags: [review, qa/chatbot-auto-ingest, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-29
---

# Review: QA-CHATBOT-AUTO-INGEST-COVERAGE (TASK-043 follow-up)

## Verdict: APPROVE

## Summary
Brings `apps/courses/chatbot_auto_ingest.py` from zero to 27 tests across 3 classes, with explicit TASK-043 coverage of the QUIZ skip path (both at the dispatcher and the source-type mapping). Tests correctly verify behavior — return value AND DB-level absence of knowledge rows.

## Verification

### Test inventory matches request
| Class | Tests | Confirmed |
|-------|-------|-----------|
| `ContentHashTestCase` | 4 | ✅ |
| `SourceTypeForContentTestCase` | 8 | ✅ (incl. `test_quiz_returns_none`) |
| `CreateKnowledgeForContentTestCase` | 15 | ✅ |
| **Total** | **27** | ✅ |

(Request body's "20 tests" figure in the opening summary is a typo; the table and the file both correctly report 27.)

### Source contract coverage
- `_content_hash` → SHA-256 hex string, deterministic, unique ✅
- `_source_type_for_content` → all 7 content_type branches covered (TEXT, VIDEO, DOCUMENT-pdf, DOCUMENT-docx, LINK, AI_CLASSROOM, CHATBOT) plus QUIZ fall-through ✅
- `_create_knowledge_for_content` → all return-None paths (QUIZ, AI_CLASSROOM, CHATBOT, empty TEXT, whitespace TEXT, DOCUMENT no url, LINK no url, VIDEO no transcript) and all create-row paths (TEXT, DOCUMENT, LINK) ✅
- Idempotency / dedup guard verified via second-call returning None ✅
- Tenant linkage and content_source linkage verified ✅

### TASK-043 specific
- `test_quiz_returns_none` (line 181) — pins `_source_type_for_content("QUIZ") is None`
- `test_quiz_content_type_returns_none` (line 210) — pins `_create_knowledge_for_content(chatbot, quiz_content) is None`
- `test_quiz_content_creates_no_knowledge_record` (line 223) — DB-level invariant, asserts row count unchanged
- Together these pin both the source-type fall-through AND the explicit `elif QUIZ` safety net in `chatbot_auto_ingest.py:161-165`

## Critical Issues
None.

## Major Issues
None.

## Minor Issues (non-blocking)
- `@pytest.mark.django_db` is applied to `CreateKnowledgeForContentTestCase` which already extends `django.test.TestCase`. `TestCase` provides its own DB transaction wrapper, so the marker is redundant (harmless, but slightly misleading — a future reader might assume one or the other is doing the work). Either subclass `unittest.TestCase` and keep the marker, or drop the marker and keep `TestCase`. Pure cosmetic, do not block.
- Tests construct `Tenant`, `User`, `Course`, etc. via local helpers — pattern is fine but the helpers don't live in a shared `conftest.py`/factory module, so duplication will accumulate. Consider hoisting `_make_tenant/_make_user/_make_course/_make_module/_make_content/_make_chatbot` into a tests fixtures module if other auto-ingest tests appear. Not blocking.

## Positive Observations
- Test docstrings explain WHY a path is skipped, not just WHAT is asserted — reads like a behavioral spec.
- The TASK-043 tests deliberately pin both the active code path (source-type fall-through) and the safety-net branch (the explicit `elif QUIZ`). This means both refactor directions (collapse to source_type, or rely on the elif) preserve correct behavior.
- DB-level idempotency check (`test_idempotent_text_content_returns_none_on_second_call`) catches the scenario where someone removes the `_knowledge_exists` guard.
- Tenant linkage assertion (`test_knowledge_record_belongs_to_correct_tenant`) is the right kind of multi-tenant safety probe for an LMS.
- VIDEO-no-transcript exception path (`AttributeError` / `DoesNotExist`) tested without monkey-patching — uses the natural absence of `content.video_asset` to raise, which matches production semantics.
