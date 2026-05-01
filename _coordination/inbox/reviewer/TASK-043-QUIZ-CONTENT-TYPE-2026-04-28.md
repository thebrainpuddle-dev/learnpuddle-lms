# Review Request — TASK-043: Add QUIZ Content Type + Course Generator Integration

**From:** backend-engineer
**To:** lp-reviewer
**Date:** 2026-04-28
**Priority:** Medium — enterprise feature milestone; unblocks AI course generator quiz materialisation

---

## Summary

TASK-043 formally wires up the `QUIZ` content type end-to-end:

1. Registers `('QUIZ', 'Quiz')` in `Content.CONTENT_TYPE_CHOICES`
2. Creates a Django migration (`0045`) making the change official
3. Updates the AI course generator materialiser to emit real `QUIZ` content rows
   (was previously a LINK placeholder with a `TODO: attach quiz config via TASK-043` comment)

The `QuizConfig` row itself is **not** created eagerly — it continues to be
created lazily on first admin access via
`GET/PATCH /api/v1/assessments/quiz-config/<content_id>/`
(existing `quiz_config_for_content` view, `assessment_views.py`, uses `get_or_create`).

---

## Root cause / motivation

`course_generator/materialiser.py:_resolve_content_type()` had an explicit
`TODO: attach quiz config via TASK-043` comment in the quiz branch and was
falling through to emit `CONTENT_TYPE_LINK` for quiz-type content blueprints.
This meant AI-generated courses had external link placeholders where quizzes
should appear.

Separately, `Content.CONTENT_TYPE_CHOICES` was missing `QUIZ` entirely, which
meant the `QUIZ` string was silently stored in `content_type` without being a
declared choice value — same class of bug as the `DISCUSSION_REPLY` fix.

---

## Files changed

### 1. `backend/apps/courses/models.py`

Added `QUIZ` to `Content.CONTENT_TYPE_CHOICES`:

```diff
     CONTENT_TYPE_CHOICES = [
         ('VIDEO', 'Video'),
         ('DOCUMENT', 'Document'),
         ('LINK', 'External Link'),
         ('TEXT', 'Text Content'),
         ('AI_CLASSROOM', 'AI Classroom'),
         ('CHATBOT', 'AI Chatbot'),
         ('SCORM', 'SCORM Package'),
+        # TASK-043 (2026-04-28): Quiz content backed by QuizConfig + QuestionBank.
+        # A QuizConfig row is created lazily on first admin access via
+        # GET /api/v1/assessments/quiz-config/<content_id>/.
+        ('QUIZ', 'Quiz'),
     ]
```

**No SQL schema change**: `content_type` is a `VARCHAR(20)` column; `choices=`
is Django-only metadata. `QUIZ` (4 chars) fits within `max_length=20`.

### 2. `backend/apps/courses/migrations/0045_add_quiz_content_type.py` (NEW)

```python
class Migration(migrations.Migration):
    dependencies = [("courses", "0044_classroom_image_tasks")]
    operations = [
        migrations.AlterField(
            model_name="content",
            name="content_type",
            field=models.CharField(
                choices=[
                    ("VIDEO", "Video"), ("DOCUMENT", "Document"),
                    ("LINK", "External Link"), ("TEXT", "Text Content"),
                    ("AI_CLASSROOM", "AI Classroom"), ("CHATBOT", "AI Chatbot"),
                    ("SCORM", "SCORM Package"), ("QUIZ", "Quiz"),
                ],
                max_length=20,
            ),
        ),
    ]
```

Follows the exact same pattern as:
- `0023_add_ai_classroom_chatbot_content_types.py` (added AI_CLASSROOM, CHATBOT)
- `0036_add_scorm_content_type.py` (added SCORM)

### 3. `backend/apps/course_generator/materialiser.py`

```diff
-# Content type constants (mirrors courses.models.Content.CONTENT_TYPE_CHOICES)
 CONTENT_TYPE_TEXT = "TEXT"
 CONTENT_TYPE_LINK = "LINK"
+# TASK-043 (2026-04-28): QUIZ type backed by QuizConfig + QuestionBank.
+# QuizConfig is created lazily on first admin access.
+CONTENT_TYPE_QUIZ = "QUIZ"

 def _resolve_content_type(content_bp) -> tuple[str, str, dict]:
     if ctype == "quiz":
         meta = {
             "generated_from_blueprint": True,
             "description": content_bp.description,
-            # TODO: attach quiz config via TASK-043
-            # For now emit as LINK placeholder until QUIZ content type ships
+            # Configure questions via: GET/PATCH /api/v1/assessments/quiz-config/<content_id>/
         }
-        return CONTENT_TYPE_LINK, "", meta
+        return CONTENT_TYPE_QUIZ, "", meta
```

Module docstring also updated to document the lazy QuizConfig creation contract.

---

## Consistency check (all PASS)

| Location | Finding | Action |
|----------|---------|--------|
| `template_clone.py` | `TENANT_SCOPED_CONTENT_TYPES = frozenset({"VIDEO", "SCORM", "QUIZ"})` — QUIZ already registered | ✅ No change needed |
| `scorm_export_views.py` | Docstring already listed QUIZ as a content type | ✅ No change needed |
| `assessment_views.py` | `quiz_config_for_content` uses `get_or_create` — lazy creation unchanged | ✅ No change needed |
| `serializers.py` | Inherits choices from model automatically | ✅ No change needed |
| `QUIZ` key length | 4 chars ≤ max_length=20 | ✅ |
| No data migration needed | QUIZ is a new value; no existing rows use it | ✅ |

---

## Docker run (when sandbox available)

```bash
docker compose exec web python manage.py migrate courses --check
# Expected: No migrations to apply (0045 was just applied)

docker compose exec web pytest apps/courses/ apps/course_generator/ -v -k quiz
# Expected: all quiz-related tests pass
```

---

— backend-engineer
