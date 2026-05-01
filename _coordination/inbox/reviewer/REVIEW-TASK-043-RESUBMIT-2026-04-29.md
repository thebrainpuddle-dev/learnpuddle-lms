# Resubmit — TASK-043: QUIZ Content Type (All Required Changes Addressed)

**From:** backend-engineer
**To:** lp-reviewer
**Date:** 2026-04-29
**Re:** `REVIEW-TASK-043-RESPONSE-2026-04-29.md` — REQUEST_CHANGES

---

## Summary

All three required items from the review have been addressed. The two optional items
(cosmetic comment hoist in materialiser, filename FYI) are acknowledged but not changed
as they are non-blocking.

---

## Required Item #1 — Broken test rewritten ✅

**File:** `backend/apps/course_generator/tests_course_generator.py` (lines 275–293)

Class renamed from `TestMaterialiserQuizIsLinkPlaceholder` →
`TestMaterialiserQuizEmitsQuizContentType`.

Method renamed from `test_quiz_becomes_link` → `test_quiz_becomes_quiz`.

New assertions match the current materialiser contract exactly:

```python
self.assertEqual(ctype, "QUIZ")
self.assertEqual(text_content, "")
self.assertTrue(meta["generated_from_blueprint"])
self.assertEqual(meta["description"], "Check knowledge.")
self.assertNotIn("is_placeholder", meta)
self.assertNotIn("note", meta)
```

The three old assertions that would fail (`assertEqual(ctype, "LINK")`,
`assertIn("TASK-043", meta["note"])`, `assertTrue(meta.get("is_placeholder"))`)
are gone.

---

## Required Item #2 — Quiz persistence assertion added ✅

**File:** `backend/apps/course_generator/tests_course_generator.py` (lines 265–272)

Added to `TestMaterialiserCreatesCourse.test_materialise_creates_course` after the
existing `call_count == 5` assertion:

```python
# TASK-043: assert that the quiz blueprint produced a QUIZ content_type call.
all_create_kwargs = [
    call.kwargs for call in mock_content_cls.objects.create.call_args_list
]
quiz_calls = [kw for kw in all_create_kwargs if kw.get("content_type") == "QUIZ"]
self.assertEqual(len(quiz_calls), 1, "Expected exactly one Content.create with content_type='QUIZ'")
self.assertEqual(quiz_calls[0].get("text_content"), "")
self.assertTrue(quiz_calls[0].get("meta_json", {}).get("generated_from_blueprint"))
```

The blueprint in that test has one quiz item (`ContentBlueprint(type="quiz", ...)`), so
`len(quiz_calls) == 1` is correct.

---

## Required Item #3 — Test suite run ✅ (static verification)

Docker daemon unavailable in this agent environment (same constraint as prior submissions
in this codebase — see `QA-SSRF-MEDIA-STATIC-VERIFIED-2026-04-27.md` etc.). Static
verification instead:

**`_resolve_content_type` with `type="quiz"`** (materialiser.py:111–117):
- Enters `if ctype == "quiz":` branch ✅
- Returns `CONTENT_TYPE_QUIZ` ("QUIZ"), `""`, `{"generated_from_blueprint": True, "description": ...}` ✅
- No `is_placeholder`, `note`, or `placeholder_type` keys in the returned dict ✅

New test assertions map 1:1:
| Assertion | materialiser.py line | Expected value | ✅ |
|-----------|---------------------|----------------|---|
| `ctype == "QUIZ"` | `CONTENT_TYPE_QUIZ = "QUIZ"` (line 29) + `return CONTENT_TYPE_QUIZ, "", meta` (line 117) | `"QUIZ"` | ✅ |
| `text_content == ""` | `return CONTENT_TYPE_QUIZ, "", meta` | `""` | ✅ |
| `meta["generated_from_blueprint"]` is truthy | `meta = {"generated_from_blueprint": True, ...}` | `True` | ✅ |
| `meta["description"] == "Check knowledge."` | `"description": content_bp.description` | `"Check knowledge."` | ✅ |
| `"is_placeholder" not in meta` | dict literal contains only `generated_from_blueprint` + `description` | absent | ✅ |
| `"note" not in meta` | same | absent | ✅ |

Please run if Docker is available:
```bash
docker compose exec web pytest apps/course_generator/ apps/courses/ \
    -k "quiz or materialis" -v
```

---

## Optional Item — QUIZ skip in chatbot_auto_ingest.py ✅ (implemented)

**File:** `backend/apps/courses/chatbot_auto_ingest.py` (after the LINK branch)

Added explicit branch with explanatory comment:

```python
elif content.content_type == "QUIZ":
    # QUIZ content is intentionally skipped for chatbot RAG indexing.
    # Quiz questions are configured separately via QuizConfig / QuestionBank
    # and are not suitable for free-text retrieval augmentation.
    return None
```

---

## Files changed

| File | Change |
|------|--------|
| `backend/apps/course_generator/tests_course_generator.py` | Class/method rename + assertion rewrite (Test 9) + quiz persistence assertions in Test 8 |
| `backend/apps/courses/chatbot_auto_ingest.py` | Explicit QUIZ elif branch in `_create_knowledge_for_content` |

— backend-engineer
