---
tags: [review, task/BE-CALENDAR-CALLBACK-ADMIN-ONLY-AND-COMPLETION-RATE, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-22
---

# Review: BE-CALENDAR-CALLBACK-ADMIN-ONLY-AND-COMPLETION-RATE — Calendar callback admin gate, real completion_rate, league polish, 2 × N+1 eliminations

## Verdict: APPROVE

## Summary
Six targeted backend changes, all either closing non-blocking follow-ups from
prior approved reviews or fixing latent TODO/N+1 issues. Every change was
verified against the actual source; no regressions spotted. Safe to merge.

## Critical Issues
None.

## Major Issues
None.

## Minor Issues

1. **Change 2 (`get_completion_rate`) — live-count fallback path is not
   tenant-scoped.** In `apps/courses/serializers.py:200-205`:

   ```python
   from apps.progress.models import TeacherProgress
   completed = TeacherProgress.objects.filter(
       course=obj,
       content__isnull=True,
       status='COMPLETED',
   ).count()
   ```

   `TeacherProgress.objects` is a `TenantManager`, so it relies on the
   thread-local tenant being set when this branch runs outside the
   `course_list` path (e.g. unit tests, `academics/admin_views.py`). This
   is consistent with the rest of the codebase — not a defect, but callers
   that instantiate the serializer without a `TenantMiddleware`-set tenant
   will get an empty count. Non-blocking; note for qa-tester when writing
   the fallback-path test (Change 2 test #1–3): either use
   `set_current_tenant(...)` or prefer the annotated queryset path.

2. **Change 2 — count query filter relies on `progress__content__isnull=True`
   convention.** The annotation counts *course-level* `TeacherProgress` rows
   (content FK null). This is correct per the existing model semantics
   (course-level progress is the "has teacher completed the whole course"
   marker), but the convention lives only in the `TeacherProgress` usages,
   not in the model's docstring. Recommend adding a one-line comment on
   `TeacherProgress.course` / `TeacherProgress.content` to codify "null
   content = course-level progress row" so future changes don't break this
   accidentally. Non-blocking.

3. **Change 4 — migration description claims "no production data yet" but
   `unique_league_rank_snapshot_per_teacher_per_week` will still fail the
   migration if any dev/staging env has duplicate rows.** For production
   this is fine (leagues 0017 is new), but recommend documenting a
   one-liner that devops should run `python manage.py dbshell` and drop
   duplicates before applying on any env that ran `close_league_week`
   twice under the old code. Non-blocking; comment-level improvement.

## Positive Observations

- **Change 1 (`@admin_only` on `calendar_callback`)** — verified at
  `apps/integrations_calendar/views.py:162-164`. Defense-in-depth matches
  `connect_calendar` / `disconnect_calendar`; cache-key binding to
  `user.pk` already prevented cross-role replay but this closes the
  surface cleanly. Closes the non-blocking ask in
  `REVIEW-VERDICT-OAUTH-MSAL-SLICE-B-2026-04-21.md`.

- **Change 2 (`_completed_teacher_count` annotation)** — the three
  `Count(..., distinct=True)` annotations on the list queryset are
  correctly composed. `related_name='progress'` on
  `TeacherProgress.course` (`apps/progress/models.py:31`) confirms the
  reverse relation is wired. `distinct=True` is essential here because
  of the `modules` + `modules__contents` prefetch that would otherwise
  cross-join and inflate the `progress` count — good instinct.

- **Change 3 (UTC hardening)** — `_iso_week_start` at
  `league_engine.py:40-47` now always returns UTC Monday. Tenant-safe
  even if `settings.TIME_ZONE` is ever overridden. Doc comment updated
  to reflect the new guarantee.

- **Change 4 (unique constraint + get_or_create)** — constraint landed
  both in `league_models.py:227-235` and migration
  `0021_league_snapshot_unique_constraint.py`. `close_league_week`
  updated to `LeagueRankSnapshot.all_objects.get_or_create(...)` at
  `league_engine.py:340-352`, and the `snapshots_written` summary
  counter correctly only increments on `_snap_created=True`. Crash-safe
  retry pattern is now real.

- **Change 5 (`notification_list` select_related)** — `.select_related('course', 'assignment')`
  at `notifications/views.py:37-39`. `NotificationSerializer` fields
  `course_title` / `assignment_title` already handle the null-FK case,
  so zero behaviour change, 40 fewer queries per 20-notification page.

- **Change 6 (`reminder_history` annotation)** — annotation at
  `reminders/views.py:240-247` + `hasattr` fallback in
  `reminders/serializers.py:41-53`. The fallback preserves the
  single-campaign `reminder_send` response path. Saves 100 queries on a
  50-campaign admin page.

## Tests Required (for qa-tester)

- **Change 2:** completion_rate correctness matrix (1/2 = 50%, 0/0 = 0%,
  all-done = 100%, content-level progress does NOT inflate). Both paths:
  annotated and live-count fallback.
- **Change 6:** `reminder_history` returns correct sent/failed counts;
  `CaptureQueriesContext` asserts no N+1.
- **Change 1, 3, 4, 5:** static-only changes; existing tests suffice,
  no new tests strictly required (but Change 4's unique-constraint
  could get a "double close_league_week" regression test).

## Merge Recommendation

Ship as one commit. All six changes are independently additive and low-risk.
backend-engineer should:

1. Run `python manage.py migrate progress` in staging first to confirm
   migration 0021 applies cleanly (should be instant on empty table).
2. Run `python manage.py makemigrations --check --dry-run` after rebase
   to confirm no further migration is needed for `LeagueRankSnapshot.Meta.constraints`.
3. Coordinate with qa-tester on the 6 tests listed above.

— reviewer (lp-reviewer)
