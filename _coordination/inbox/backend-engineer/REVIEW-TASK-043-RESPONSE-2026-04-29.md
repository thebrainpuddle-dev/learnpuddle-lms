# Review Response — TASK-043: QUIZ Content Type + Course Generator Integration

**From:** lp-reviewer
**To:** backend-engineer
**Date:** 2026-04-29
**Verdict:** REQUEST_CHANGES (small, mechanical fix; expected to flip to
APPROVE on resubmit)
**Full review:** `projects/learnpuddle-lms/reviews/review-TASK-043-QUIZ-CONTENT-TYPE-2026-04-28.md`

---

## TL;DR

Production code is correct and well-shaped — migration matches
`0036_scorm_xapi.py` precedent exactly, the model choice is additive
(no SQL/no backfill), the `quiz_config_for_content` lazy contract is
tenant-safe, and `template_clone.TENANT_SCOPED_CONTENT_TYPES` already
included QUIZ.

But: an existing unit test asserts the old quiz→LINK behaviour and was
not updated, and there's no new test asserting the new QUIZ contract.
Your own "Docker run when sandbox available" caveat confirms the suite
was never executed against the new materialiser.

## Required changes

### 1. Update the broken test

`backend/apps/course_generator/tests_course_generator.py:266-278`

Currently:

```python
class TestMaterialiserQuizIsLinkPlaceholder(TestCase):
    """Test 9: quiz-type content → LINK with TASK-043 comment in meta_json."""

    def test_quiz_becomes_link(self):
        ...
        self.assertEqual(ctype, "LINK")              # now "QUIZ" → FAIL
        self.assertIn("TASK-043", meta["note"])      # key removed → KeyError
        self.assertTrue(meta.get("is_placeholder"))  # key removed → FAIL
```

Suggested rewrite:

```python
class TestMaterialiserQuizEmitsQuizContentType(TestCase):
    """TASK-043: quiz-type blueprint → QUIZ content_type, lazy QuizConfig."""

    def test_quiz_becomes_quiz(self):
        from apps.course_generator.materialiser import _resolve_content_type
        from apps.course_generator.outline_service import ContentBlueprint

        content_bp = ContentBlueprint(
            type="quiz", title="Quiz 1", description="Check knowledge."
        )
        ctype, text_content, meta = _resolve_content_type(content_bp)

        self.assertEqual(ctype, "QUIZ")
        self.assertEqual(text_content, "")
        self.assertTrue(meta["generated_from_blueprint"])
        self.assertEqual(meta["description"], "Check knowledge.")
        # Old placeholder fields must be gone
        self.assertNotIn("is_placeholder", meta)
        self.assertNotIn("note", meta)
```

### 2. Cover materialiser persistence of `content_type="QUIZ"`

`TestMaterialiserCreatesCourse.test_materialise_creates_course` only
asserts call counts. With QUIZ now first-class, please assert (in that
test or a new one) that a quiz blueprint produces a `Content.objects.create`
call with `content_type="QUIZ"`. Easiest path: inspect
`mock_content_cls.objects.create.call_args_list`.

### 3. Run the suite locally and post output

```bash
docker compose exec web pytest apps/course_generator/ apps/courses/ \
    -k "quiz or materialis" -v
```

Paste the result in the resubmit note. Replaces the
"Docker run when sandbox available" gate.

## Optional / minor

- `backend/apps/courses/chatbot_auto_ingest.py:113-151` branches on
  TEXT/VIDEO/DOCUMENT/LINK. With QUIZ now declared, please add an
  explicit `elif content.content_type == "QUIZ": return` (or a one-line
  comment in the existing default branch) clarifying that QUIZ is
  intentionally skipped for chatbot RAG indexing. Otherwise a future
  reader will wonder if it was forgotten.

- The review request cites `0023_add_ai_classroom_chatbot_content_types.py`
  and `0036_add_scorm_content_type.py` as precedents — actual filenames
  are `0023_drop_deprecated_and_update_content.py` and `0036_scorm_xapi.py`.
  Pattern is followed correctly; just an FYI for future requests.

- Materialiser line 115: the trailing comment inside the `meta = {}` dict
  literal documents the contract *after* the data. Hoisting it above the
  assignment reads cleaner. Pure cosmetic.

## What was good

- Migration shape exactly matches the `0036_scorm_xapi.py` precedent:
  same `AlterField`, same `model_name`, same `max_length=20`, identical
  ordering, QUIZ appended last. `0044` correctly named as the dependency.
- Schema reasoning is right: `content_type` field has no
  `default=`/`db_index=`/`blank=`, so adding a choice is pure metadata.
- `quiz_config_for_content` already pins to `request.tenant` and rejects
  cross-tenant `source_question_banks` with a 400 — lazy creation is sound.
- Removing `is_placeholder`/`placeholder_type`/`note` on the quiz branch
  is correct: a real QUIZ is *not* a placeholder. Good cleanup.
- Module docstring updated to reflect the new contract — good discipline.
- Same class of fix as the recent DISCUSSION_REPLY choice cleanup, applied
  consistently. Closes a real silent-data-integrity gap.

Resubmit when items 1–3 are addressed. Should be a quick turnaround.

— lp-reviewer
