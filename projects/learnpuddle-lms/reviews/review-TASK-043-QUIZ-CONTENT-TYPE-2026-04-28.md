---
tags: [review, task/TASK-043, verdict/request-changes, reviewer/lp-reviewer]
created: 2026-04-28
---

# Review: TASK-043 — Add QUIZ Content Type + Course Generator Integration

## Verdict: REQUEST_CHANGES

## Summary

Production code is correct and well-shaped: the migration, model choice
addition, and materialiser change all follow established precedent (mirrors
`0036_scorm_xapi.py` exactly). However, an existing unit test that asserts
the **old** quiz→LINK contract was not updated, and no new test asserts the
new QUIZ contract. Tests will fail on the next run and there is no
behavioural coverage of the new branch.

Author's own "Docker run (when sandbox available)" caveat in the request
makes the gap clear — the test suite was never executed against the new
materialiser. This is a small, mechanical fix.

## Critical Issues

None — no security, tenancy, or data‑integrity risk. Migration is additive
(no SQL schema change, no data backfill needed). `QuizConfig` lazy creation
through `quiz_config_for_content` (`assessment_views.py:265`) keeps tenant
isolation intact via `get_or_create(content=..., defaults={"tenant": ...})`
and the cross‑tenant question‑bank guard.

## Major Issues

### 1. Existing test will fail and was not updated

`backend/apps/course_generator/tests_course_generator.py:266-278`

```python
class TestMaterialiserQuizIsLinkPlaceholder(TestCase):
    """Test 9: quiz-type content → LINK with TASK-043 comment in meta_json."""

    def test_quiz_becomes_link(self):
        ...
        ctype, text_content, meta = _resolve_content_type(content_bp)
        self.assertEqual(ctype, "LINK")              # now "QUIZ" → FAIL
        self.assertIn("TASK-043", meta["note"])      # key removed → KeyError
        self.assertTrue(meta.get("is_placeholder")) # key removed → FAIL
```

After this change `_resolve_content_type` returns `("QUIZ", "", {"generated_from_blueprint": True, "description": ...})`, so all three assertions will fail (the second raises `KeyError` before assertion).

**Required fix:** rewrite the test to lock in the new contract. Suggested:

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
        # Negative assertions — old placeholder fields must be gone
        self.assertNotIn("is_placeholder", meta)
        self.assertNotIn("note", meta)
```

### 2. No coverage that the materialiser persists `content_type="QUIZ"`

`TestMaterialiserCreatesCourse.test_materialise_creates_course`
(line ~196) mocks the model classes and only asserts call counts; it does
not introspect the `content_type` keyword passed to
`Content.objects.create`. With the choice now declared, a mini integration
test (or even an inspection of `mock_content_cls.objects.create.call_args_list`)
should assert that a quiz blueprint produces a row whose
`content_type == "QUIZ"`. Without it the wiring between `_resolve_content_type`
and `Content` creation is uncovered for the new branch.

## Minor Issues

### 1. `chatbot_auto_ingest.py` does not handle `QUIZ`

`backend/apps/courses/chatbot_auto_ingest.py:113-151` branches on
TEXT/VIDEO/DOCUMENT/LINK and silently no-ops for any other type. With QUIZ
now a first-class content type, that no-op is almost certainly the *correct*
behaviour (you don't index quiz questions for chatbot RAG retrieval), but it
should be explicit — either an `elif content.content_type == "QUIZ": return`
with a one‑line comment or a TASK‑043 note in the existing default branch.
Otherwise a future reader will wonder whether QUIZ was simply forgotten.

### 2. Review request references migration filenames that don't exist

The request cites `0023_add_ai_classroom_chatbot_content_types.py` and
`0036_add_scorm_content_type.py` as precedent. Actual filenames are
`0023_drop_deprecated_and_update_content.py` and `0036_scorm_xapi.py`. The
*pattern* is followed correctly (verified) — but the cite-to-file mismatch
in the request is misleading. Cosmetic.

### 3. Comment in materialiser line 115 is end-of-block

```python
meta = {
    "generated_from_blueprint": True,
    "description": content_bp.description,
    # Configure questions via: GET/PATCH /api/v1/assessments/quiz-config/<content_id>/
}
```

The trailing comment inside the dict literal reads awkwardly on quick
inspection. Consider hoisting it above the `meta = {` assignment so the
contract is documented before, not after, the data.

## Positive Observations

- **Migration is shape-perfect** vs precedent (`0036_scorm_xapi.py`):
  same `AlterField` form, same `model_name`, same `max_length=20`,
  identical choice ordering preserved for the prior values, QUIZ appended
  last. `0044` is correctly named as the dependency.
- **Schema reasoning is correct**: `content_type` is `CharField(max_length=20)`
  with no `default=`/`db_index=`/`blank=`, so adding a choice is purely
  Django-side metadata. No SQL DDL, no data backfill — both correctly
  asserted.
- **Tenant isolation preserved**: `quiz_config_for_content` already pins
  to `request.tenant` and rejects cross-tenant `source_question_banks`
  with a 400 (lines 285-296). The lazy-creation contract is sound.
- **`template_clone.TENANT_SCOPED_CONTENT_TYPES` already includes QUIZ**
  (line 36) — confirmed; no orphan reference debt.
- **Same class of fix** as the recent DISCUSSION_REPLY choice cleanup,
  applied consistently. Closes a real silent-data-integrity gap.
- **Module docstring updated** to reflect the new contract — good
  discipline.
- Removing the old placeholder fields (`is_placeholder`, `placeholder_type`,
  `note`) on the quiz branch is correct: a real QUIZ is *not* a placeholder.

## Action items for author

1. **Update** `tests_course_generator.py:266-278` to assert the new
   QUIZ contract (suggested implementation above).
2. **Add** an assertion (in `test_materialise_creates_course` or a new test)
   that a quiz blueprint produces `content_type="QUIZ"` on the `Content`
   row.
3. **Run** `pytest apps/course_generator/ apps/courses/ -k "quiz or materialis"`
   locally and paste the result in the resubmit note — the original request
   left this gated on a sandbox.
4. *(Optional, minor)* Add an explicit `QUIZ` no-op branch + comment in
   `chatbot_auto_ingest.py`.

Resubmit when items 1–3 are done. Expected to flip to APPROVE on rereview.

— lp-reviewer
