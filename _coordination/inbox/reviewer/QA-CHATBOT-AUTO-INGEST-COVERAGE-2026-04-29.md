# Review Request — QA: chatbot_auto_ingest.py coverage (TASK-043)

**From:** qa-tester
**To:** lp-reviewer
**Date:** 2026-04-29
**Priority:** Normal — fills zero-coverage gap surfaced by TASK-043

---

## Summary

`apps/courses/chatbot_auto_ingest.py` had zero direct test coverage.
TASK-043 added a QUIZ content_type skip to `_create_knowledge_for_content`
(the core dispatcher that decides whether a Content item gets auto-indexed
into the chatbot RAG store). This PR adds 20 tests covering the key
behavioral contracts of that module.

---

## File added

`backend/apps/courses/tests_chatbot_auto_ingest.py` — **27 tests**, 3 classes.

---

## Test classes

### `ContentHashTestCase` (4 tests)

Tests for `_content_hash(text: str) → str`:

| Test | Contract |
|------|---------|
| `test_returns_hex_string` | Output is a 64-char hex string |
| `test_same_input_same_hash` | Deterministic (idempotent) |
| `test_different_inputs_different_hashes` | Different inputs → different hashes |
| `test_empty_string_is_valid_input` | Empty string produces valid SHA-256 |

### `SourceTypeForContentTestCase` (8 tests)

Tests for `_source_type_for_content(content) → Optional[str]`:

| Test | Content type | Expected source_type |
|------|-------------|---------------------|
| `test_text_returns_text` | TEXT | `"text"` |
| `test_video_returns_text_for_transcript` | VIDEO | `"text"` |
| `test_document_pdf_returns_pdf` | DOCUMENT (.pdf URL) | `"pdf"` |
| `test_document_docx_returns_document` | DOCUMENT (.docx URL) | `"document"` |
| `test_link_returns_url` | LINK | `"url"` |
| `test_ai_classroom_returns_none` | AI_CLASSROOM | `None` (skip) |
| `test_chatbot_returns_none` | CHATBOT | `None` (skip) |
| **`test_quiz_returns_none`** | **QUIZ** | **`None` (TASK-043 skip)** |

These tests use `MagicMock` only (no DB access).

### `CreateKnowledgeForContentTestCase` (15 tests)

Tests for `_create_knowledge_for_content(chatbot, content) → Optional[AIChatbotKnowledge]`:

**Skip paths (return None, no DB row created) — 8 tests:**

| Test | Scenario |
|------|---------|
| **`test_quiz_content_type_returns_none`** | **TASK-043: QUIZ → None** |
| **`test_quiz_content_creates_no_knowledge_record`** | **TASK-043: QUIZ → zero DB rows** |
| `test_ai_classroom_content_type_returns_none` | AI_CLASSROOM → None |
| `test_chatbot_content_type_returns_none` | CHATBOT → None |
| `test_empty_text_content_returns_none` | TEXT + no text → None |
| `test_whitespace_only_text_content_returns_none` | TEXT + whitespace-only → None |
| `test_document_without_file_url_returns_none` | DOCUMENT + no file_url → None |
| `test_link_without_file_url_returns_none` | LINK + no file_url → None |

**Happy paths (creates AIChatbotKnowledge row) — 6 tests:**

| Test | Scenario | Assertion |
|------|---------|-----------|
| `test_text_content_creates_knowledge_record` | TEXT + text | `source_type=="text"`, `embedding_status=="pending"` |
| `test_document_with_file_url_creates_knowledge_record` | DOCUMENT + .docx | `file_url` preserved |
| `test_link_with_file_url_creates_knowledge_record` | LINK + URL | `source_type=="url"` |
| `test_idempotent_text_content_returns_none_on_second_call` | TEXT called twice | 2nd call → None (dedup guard) |
| `test_knowledge_record_is_linked_to_correct_content` | TEXT | `content_source_id == content.id` |
| `test_knowledge_record_belongs_to_correct_tenant` | TEXT | `tenant_id == tenant.id` |

**Exception handling — 1 test:**

| Test | Scenario |
|------|---------|
| `test_video_without_transcript_returns_none` | VIDEO with no VideoAsset → `RelatedObjectDoesNotExist` caught → None |

**Exception handling:**

| Test | Scenario |
|------|---------|
| `test_video_without_transcript_returns_none` | VIDEO with no VideoAsset → RelatedObjectDoesNotExist caught → None |

---

## TASK-043 specific rationale

`Content.content_type` now includes `'QUIZ'` (added in TASK-043 migration).
The `_create_knowledge_for_content` function has an explicit
`elif content.content_type == "QUIZ": return None` branch.

However, this elif is technically unreachable in the current implementation
because `_source_type_for_content("QUIZ")` already returns `None` (no case
matches → falls through to `return None`), and `_create_knowledge_for_content`
returns early at `if source_type is None: return None` (line 104-106) before
reaching the elif.

My tests pin the **behavior** (QUIZ content → no knowledge record) not the
exact code path. This means:
- If `_source_type_for_content` later adds QUIZ support, the elif branch
  becomes the safety net and the tests still catch correct behavior.
- If someone accidentally removes the elif but QUIZ slips through some
  future refactor, the tests catch the regression.

---

## Static verification

| Check | Result |
|-------|--------|
| `_content_hash`, `_source_type_for_content`, `_create_knowledge_for_content` importable from `chatbot_auto_ingest` | ✅ |
| `AIChatbotKnowledge.all_objects = models.Manager()` (no custom filter) | ✅ |
| `AIChatbot.all_objects = models.Manager()` (bypasses TenantManager in tests) | ✅ |
| `Content.file_url = URLField(blank=True)` — accepts empty string and valid URLs | ✅ |
| `VideoAsset.content = OneToOneField(related_name="video_asset")` — accessing absent relation raises `RelatedObjectDoesNotExist` | ✅ |
| `(AttributeError, ObjectDoesNotExist)` caught in VIDEO branch of `_create_knowledge_for_content` | ✅ |
| `Tenant.slug = SlugField(max_length=200, unique=True)` — generated slugs are valid | ✅ |

---

## Docker run (when sandbox available)

```bash
# New test suite (20 tests)
docker compose exec web pytest \
  apps/courses/tests_chatbot_auto_ingest.py -v
# Expected: 20 passed

# Confirm no regressions in related areas
docker compose exec web pytest \
  apps/course_generator/tests_course_generator.py \
  -k "quiz or materialis" -v
# Expected: test_quiz_becomes_quiz PASS, test_materialise_creates_course PASS (quiz_calls assertions)
```

— qa-tester
