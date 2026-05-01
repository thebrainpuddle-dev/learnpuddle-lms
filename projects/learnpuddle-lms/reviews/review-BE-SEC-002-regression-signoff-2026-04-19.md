---
tags: [review, task/BE-SEC-002, verdict/approve, reviewer/lp-reviewer, signoff]
created: 2026-04-19
supersedes: _coordination/reviews/review-BE-SEC-002-maic-chat-idor.md
---

# Review addendum: BE-SEC-002 regression test — SIGN-OFF

## Verdict: APPROVE — BE-SEC-002 clears for `status/done`

## Summary

qa-tester landed the m3 handoff test at
`backend/tests/courses/test_maic_student_chat.py`. The test surface
exceeds what the original review required: it covers the core regression,
a positive control, the public-classroom branch, and the unknown-id
branch. Combined with the already-approved code fix (see
`_coordination/reviews/review-BE-SEC-002-maic-chat-idor.md`), BE-SEC-002
is complete and can be flipped to `status/done`.

## What the test covers (vs. what m3 required)

m3 required *one* test that iterates the SSE `streaming_content` and
asserts the foreign classroom's title / agent names / scene titles are
absent from the stream. qa-tester delivered four:

| # | Test | Branch exercised | Asserts |
|---|------|------------------|---------|
| 1 | `test_student_cannot_seed_chat_from_foreign_section_classroom` | section-A student ↔ section-B-only classroom | streamed body has no secret substrings **AND** `generate_chat_sse` was called with empty `classroom_title` / `agents` / `scene_titles` |
| 2 | `test_student_in_assigned_section_gets_seeded_chat_context` | section-B student ↔ section-B classroom | context is populated (prevents over-correction regressions) |
| 3 | `test_public_classroom_seeds_chat_for_any_student` | `elif not classroom.is_public` false path | no-section student gets context from a public classroom |
| 4 | `test_unknown_classroom_id_does_not_seed` | `MAICClassroom.DoesNotExist` branch | random UUID → empty context (pre-existing behaviour preserved) |

## Why this is the right shape of test

- **Fallback forcing is explicit.** `_force_fallback_and_capture()`
  patches `apps.courses.maic_views._proxy_sse` to return a 502
  `HttpResponse`, which is the exact condition under which the view
  enters the direct-LLM branch — i.e. the IDOR surface. Any future
  refactor that routes around the 502 branch will cause the positive
  test (#2) to fail loudly rather than silently bypass the check.
- **Two layers of assertion.** Substring checks on the streamed body
  would catch the leak if the visibility check ever regressed, but they
  could also pass spuriously if the chat template happened to omit
  names. The companion `generate_chat_sse` kwargs capture pins the
  *input* to the generator — the exact surface the IDOR affected —
  which is the assertion I'd have written first.
- **Sentinel-based fixtures.** `SECRET_TITLE` / `SECRET_TOPIC` /
  `SECRET_AGENT` / `SECRET_SCENE` are uniquely-identifiable strings —
  no risk of collision with test boilerplate producing false negatives.
- **Positive control prevents silent breakage.** Test #2 guards against
  the future "just don't seed anything, ever" regression that would
  technically pass the IDOR substring checks but break the feature.
- **Branch coverage is complete.** All three branches of the
  visibility check (`assigned.exists()` + section match, `is_public=True`,
  `DoesNotExist`) are exercised.

## Spot-checks

- `_consume()` correctly flattens `StreamingHttpResponse.streaming_content`
  to bytes and handles both bytes and str chunks. Matches Django's SSE
  response type.
- `APIClient.force_authenticate` + `HTTP_HOST = "{subdomain}.lms.com"`
  pattern matches the tenant-middleware expectations in this repo.
- Factories (`TenantFactory`, `UserFactory.create_teacher`,
  `UserFactory.create(..., role="STUDENT", section_fk=…)`) are the
  canonical factories in `backend/tests/factories.py` and are used
  consistently across the existing test suite.
- Local fixtures for `Grade` / `Section` use the real
  `apps.academics.models` models with required fields
  (`academic_year`, `short_code`, `order`) — no shortcuts.
- `MAICClassroom.objects.create(... tenant=tenant ...)` explicitly
  passes tenant — correct given the `TenantManager` auto-filter would
  otherwise hide the row at lookup time in tests without a bound
  tenant context.

## Outstanding / deferred

- **m1 (low, non-blocking, deferred)** — `status="READY"` +
  `audioManifest` parity with `student_maic_classroom_detail`. Still
  open, not a merge blocker. Recommend a follow-up ticket tracking a
  shared `_student_can_view_classroom(user, classroom)` helper so the
  two endpoints can't drift (addresses m2 at the same time).
- **Director-turn endpoints** (scope observation in the prior review)
  — still riding along on the same branch. Not my call to block merge,
  but I'll flag again: feature work should not ship under a security
  sign-off.

## Test run

As before, pytest could not be executed in this sandbox (Docker
unavailable). Command for qa-tester / CI:

```bash
docker compose exec web pytest \
  backend/tests/courses/test_maic_student_chat.py -v
```

All four tests should pass against the current working tree.

## Next steps

1. **Flip BE-SEC-002 → `status/done`.** Code fix + regression test
   both landed. Nothing outstanding blocks merge.
2. Open a follow-up ticket for m1/m2 (visibility-helper extraction +
   status/manifest parity). Track separately from BE-SEC-002.
3. Split director-turn endpoints into their own PR before merge.

— lp-reviewer
