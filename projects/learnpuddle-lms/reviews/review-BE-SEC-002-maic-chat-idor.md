---
tags: [review, task/BE-SEC-002, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-19
---

# Review: BE-SEC-002 — IDOR in `student_maic_chat` direct-LLM fallback

## Verdict: APPROVE (with one minor follow-up and a scope observation)

## Summary

Single-file security fix is correct, minimal, and mirrors the proven
visibility pattern from the sibling detail endpoint line-for-line. The
IDOR (within-tenant cross-section leakage of classroom title / agent
roster / scene-title outline via the direct-LLM fallback) is closed.
Legitimate-user behavior preserved; unauthorized callers now get a
chat stream with no classroom context seeded rather than a 403 — which
matches the prior author's "silent-no-context" UX for bad ids.

One minor parity gap vs. the detail endpoint (status / manifest gating)
is noted below — low severity, not blocking. The same diff also adds
two **unrelated** director-turn endpoints (P3.1 porting) that are not
part of BE-SEC-002's stated scope; they look correctly wired but should
be tracked as a separate item so security sign-off isn't conflated with
feature work.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

### m1 (low) — Visibility check omits `status="READY"` / audio-manifest gate

`student_maic_classroom_detail` at `maic_views.py:1032-1041` filters by
`status="READY"` and additionally hides classrooms whose
`content.audioManifest.status` is not in `("ready", "partial")`. The new
check in `student_maic_chat` (lines 1094-1121) only mirrors the *section*
/ `is_public` part, not the status/manifest gate.

Net effect: a student in an assigned section can still seed chat context
(title, agents, scene titles) from a classroom that is mid-generation,
even though the detail endpoint would 404 on it. Because the student is
in the assigned section, this is not a cross-section leak — they'd see
the same data via the detail endpoint once generation completed. Severity
is low, but for strict parity with the detail endpoint, consider gating
on `status="READY"` and manifest readiness as well, or factoring the
visibility logic into a single helper used by both endpoints so drift
cannot creep in. Not a merge blocker.

### m2 (low) — Visibility logic duplicated instead of extracted

The visibility block at 1104-1112 is a line-by-line copy of 1043-1050.
Backend-security explicitly called out "mirrors the proven pattern line
by line" — correct for this fix — but as this is now the second copy of
the same assigned-section-or-public rule, a shared helper
(`_student_can_view_classroom(user, classroom) -> bool`) would prevent
future divergence. Extract on the next touch.

### m3 (non-blocking) — Regression test still outstanding

Per the review request, the regression test is handed off to qa-tester
at `tests/courses/test_maic_student_chat.py::
test_student_cannot_seed_chat_from_foreign_section_classroom`. It does
not yet exist in the tree (`grep -r 'test_student_cannot_seed' backend/
tests/` returns no match). The fix is correct on inspection but should
not ship without a behavioral test that actually iterates the SSE
`streaming_content` and asserts the foreign classroom's title / agent
names / scene titles are absent. Flagging as required before merge;
approving the code change so qa-tester can write the test against the
patched surface.

## Positive Observations

- **DoesNotExist branch handled cleanly**: the `except` sets
  `classroom = None`, and the subsequent `if classroom is not None` guard
  means the visibility block only runs on hits. Prior code would skip the
  whole seeding block on miss — behavior preserved.
- **Mirrors detail-endpoint semantics exactly**: `assigned.exists()` →
  student must be in an assigned section; else the classroom must be
  public. Same truth table as `student_maic_classroom_detail`, so a
  student whose access status flips gets consistent enforcement from
  both endpoints.
- **Sidecar path untouched**: the fix correctly isolates the change to
  the direct-LLM fallback (`_proxy_sse` result.status_code == 502
  branch). The sidecar path forwards the raw body and does not touch
  classroom rows server-side — no IDOR surface there, and leaving it
  alone keeps blast radius minimal.
- **Teacher variant correctly left alone**: `teacher_maic_chat` (lines
  279-336) is intentionally cross-section within a tenant; BE-SEC-002
  correctly does not touch it. Confirmed the teacher decorator stack is
  `teacher_or_admin + tenant_required`, so the tenant boundary is still
  the only trust boundary for teachers.
- **Inline SECURITY comment**: the block header (lines 1099-1103)
  documents *why* the check exists and references the companion
  endpoint. Future maintainers won't accidentally optimize it away.
- **Silent fallback preserved for bad IDs**: `classroom = None` → no
  seeding, chat still works with an empty context. Matches the prior
  author's "generic response for bad ids" UX and doesn't open a new
  discovery oracle via 403/404 differentials.

## Scope observation

The same diff adds `teacher_maic_director_turn` and
`student_maic_director_turn` plus `_director_turn_impl` (maic_views.py
lines 905-948, 1600-1608) and two URL routes (`maic_urls.py` added
`director/turn/` for both teacher and student). These are P3.1
multi-agent-director feature work, **not** part of BE-SEC-002. Code
looks fine on a glance — proper decorator stack
(`@teacher_or_admin` / `@student_or_admin` + `@tenant_required` +
`@check_feature("feature_maic")`), JSON body parsed defensively, 204
fallback on LLM decline — but they should not ride along under a
security-review sign-off. Track as a separate `FE/BE-MAIC-DIRECTOR` item
with its own tests.

The `maic_list_voices` comment addition ("No @tenant_required: returns a
static platform-wide list …") is fine and improves auditability — no
behavior change.

## Observations deferred to other agents (as flagged in request)

- **OBS-1 / OBS-2** (un-throttled student gen, removed topic guardrails):
  documented product decisions, out of scope.
- **OBS-3** (`image_service.py` tempfile leak): correctly handed off to
  backend-engineer; not a security review item.
- **OBS-4** (Stripe webhook exception granularity): handed off.

## Recommended next steps

1. **Do not merge until** qa-tester lands the handoff regression test at
   `tests/courses/test_maic_student_chat.py`. The fix is correct but an
   unprotected test surface invites regression.
2. Open a follow-up ticket to extract the shared visibility helper (m2)
   and add the status/manifest parity check (m1).
3. Split the director-turn endpoints out of this security branch into
   their own PR for product review.

## Test run

Pytest could not be executed in this sandbox (Docker unavailable). The
behavioral regression test is not yet written (handoff). Review is
static-inspection only. Before ship:

```bash
docker compose exec web pytest \
  tests/courses/test_maic_student_chat.py \
  apps/courses/tests_scorm_xapi.py
```

— lp-reviewer
