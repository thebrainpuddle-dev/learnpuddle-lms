---
tags: [review, task/TASK-043, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-29
---

# Review: TASK-043 — QUIZ Content Type (Resubmit)

## Verdict: APPROVE

## Summary
All three required changes from `REVIEW-TASK-043-RESPONSE-2026-04-29` are correctly applied. The test now matches the materialiser contract exactly, the persistence assertion in `test_materialise_creates_course` is precise, and the `elif QUIZ: return None` safety net in `chatbot_auto_ingest._create_knowledge_for_content` is in place.

## Required Items Verified

### #1 — Test rewritten ✅
`tests_course_generator.py:275-293`:
- Class is now `TestMaterialiserQuizEmitsQuizContentType`
- Method is `test_quiz_becomes_quiz`
- Assertions exactly match `materialiser._resolve_content_type` for `type="quiz"` (returns `(CONTENT_TYPE_QUIZ="QUIZ", "", {generated_from_blueprint, description})`)
- Stale `is_placeholder` / `note` assertions removed and explicitly negated via `assertNotIn`

### #2 — Quiz persistence assertion ✅
`tests_course_generator.py:265-272`:
- Filters `mock_content_cls.objects.create.call_args_list` for `content_type == "QUIZ"`
- Asserts exactly one such call (matches the single quiz item in the blueprint)
- Verifies `text_content == ""` and `meta_json["generated_from_blueprint"] is True`
- This now pins the blueprint→QUIZ persistence wiring, not just the resolver

### #3 — Chatbot QUIZ skip implemented ✅
`apps/courses/chatbot_auto_ingest.py:161-165`:
- Explicit `elif content.content_type == "QUIZ":` branch with explanatory comment
- Returns `None`, preventing any AIChatbotKnowledge row creation
- Defense-in-depth: even though `_source_type_for_content("QUIZ")` already falls through to `None` at line 82 (so the elif is unreachable today), this is the right place for the safety net if `_source_type_for_content` ever gains a QUIZ branch

## Critical Issues
None.

## Major Issues
None.

## Minor Issues (non-blocking, FYI)
- The QUIZ branch in `chatbot_auto_ingest._create_knowledge_for_content` is dead code as written today — the early `if source_type is None: return None` at line 105-106 already short-circuits QUIZ. This is acknowledged in the qa-tester's coverage submission and is intentional belt-and-suspenders, so leaving it as-is is the right call. If a future refactor adds a `source_type` for QUIZ, this branch becomes the active gate.

## Positive Observations
- Test 8 quiz-persistence assertion uses kwarg-shape filtering (`call.kwargs`) which is robust to argument-order refactors.
- `assertNotIn("is_placeholder", meta)` and `assertNotIn("note", meta)` actively negate the old contract — good regression hygiene.
- Resubmit narrative explicitly maps each new assertion back to a specific source line.
- Optional QUIZ skip was implemented even though it was not required, removing future ambiguity.

## Test Run
Static verification only (Docker unavailable in agent sandbox). All assertions trace 1:1 to the source contract; safe to merge once tests pass under CI/local Docker.

```bash
docker compose exec web pytest \
  apps/course_generator/tests_course_generator.py \
  -k "quiz or materialis" -v
```
