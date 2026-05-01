# Review Request — calendar_callback @admin_only + completion_rate fix + league polish

**From:** backend-engineer
**To:** reviewer (lp-reviewer)
**Date:** 2026-04-22

Six backend changes ready for review — three follow-ups from approved reviews, one TODO fix, and two N+1 query eliminations.

---

## Change 1 — `@admin_only` on `calendar_callback`

**File:** `backend/apps/integrations_calendar/views.py`

Added `@admin_only` decorator to `calendar_callback` (line ~164).  
This was requested as a non-blocking observation in `REVIEW-VERDICT-OAUTH-MSAL-SLICE-B-2026-04-21.md`:

> `calendar_callback` still lacks `@admin_only` — defense-in-depth only,
> since the user.pk cache-key binding already prevents cross-role replay.
> Add on the next calendar-integrations PR.

The decorator was already imported and used on both `connect_calendar` and
`disconnect_calendar`. The callback now matches.

**Risk:** Very low. The per-user state cache key already enforces that only the
user who initiated the flow can complete it. This adds a belt-and-braces 403
for teachers/HODs who somehow hit the callback URL directly.

---

## Change 2 — Real `completion_rate` in `CourseListSerializer`

**Files:**
- `backend/apps/courses/serializers.py:188-210`
- `backend/apps/courses/views.py:141-153` (new annotation in `course_list`)

**Problem:** `get_completion_rate` contained `# TODO: Calculate from TeacherProgress model` and always returned `0.0`. The admin course-list page showed "0% completion" for every course.

**Fix summary:**

Added `_completed_teacher_count` annotation to the `course_list` queryset:
```python
_completed_teacher_count=Count(
    'progress',
    filter=Q(progress__content__isnull=True, progress__status='COMPLETED'),
    distinct=True,
)
```

`get_completion_rate` now:
1. Reads the annotation (zero extra query in list path).
2. Falls back to a live `TeacherProgress` count (for other callers such as
   `academics/admin_views.py`).
3. Divides by `get_assigned_teacher_count(obj)` (uses existing prefetched M2M).
4. Returns `round(completed / total * 100, 1)`.

**ORM correctness:** all three `Count` annotations use `distinct=True` which
prevents cross-join inflation from the multi-table joins. The
`content__isnull=True` filter selects only course-level progress rows (not
per-content rows that represent partial progress through a content item).

**Tests needed (coordinate with qa-tester):**
1. `completion_rate == 50.0` when 1 of 2 assigned teachers has COMPLETED course-level progress.
2. `completion_rate == 0.0` when no teachers assigned.
3. `completion_rate == 100.0` when all assigned teachers have completed.
4. Content-level `TeacherProgress` rows (content FK set) do NOT inflate the count.

---

## Change 3 — `_iso_week_start` UTC hardening (league engine)

**File:** `backend/apps/progress/league_engine.py:40-46`

**Origin:** `REVIEW-VERDICT-TASK-016-2026-04-20.md` (non-blocking polish #1):
> "Consider `timezone.now().astimezone(timezone.utc).date()` in `_iso_week_start`
> to harden against a future tenant overriding `TIME_ZONE`."

Changed `today = today or timezone.localdate()` to
`today = today or timezone.now().astimezone(timezone.utc).date()`.

Now always returns the UTC Monday regardless of the Django `TIME_ZONE` setting.
League-week boundaries are consistent across tenants and server locale changes.

**Risk:** Zero — `timezone.localdate()` and `timezone.now().astimezone(utc).date()`
are identical when `settings.TIME_ZONE == "UTC"` (which is how production is
configured).  The new form is strictly more correct.

---

## Change 4 — `LeagueRankSnapshot` unique constraint + idempotent `get_or_create`

**Files:**
- `backend/apps/progress/league_models.py` — new `constraints` entry
- `backend/apps/progress/migrations/0021_league_snapshot_unique_constraint.py` — NEW
- `backend/apps/progress/league_engine.py:337-348` — `.create()` → `get_or_create()`

**Origin:** `REVIEW-VERDICT-TASK-016-2026-04-20.md` (non-blocking polish #3):
> "Optional defence-in-depth: unique constraint on `LeagueRankSnapshot(teacher, week_start_date)`."

Added `UniqueConstraint(fields=["teacher", "week_start_date"], name="unique_league_rank_snapshot_per_teacher_per_week")`.

Also changed the snapshot-creation call from `.create()` to
`.get_or_create(teacher=m.teacher, week_start_date=week_start_date, defaults={...})`.
This makes `close_league_week` truly crash-safe: if it crashes after writing snapshots
but before setting `league.closed_at`, a re-run won't raise `IntegrityError` and
`summary["snapshots_written"]` only increments for genuinely new rows.

**Migration:** Additive-only `AddConstraint`. Fast operation; no data backfill.
Leagues were added in migration 0017 and have no production data yet.

---

## Change 5 — N+1 in `notification_list` (missing `select_related`)

**File:** `backend/apps/notifications/views.py:34`

`NotificationSerializer` accesses `course.title` and `assignment.title` via
`source=` parameters. The list view was not using `select_related`, causing
2 extra SQL queries per notification row.

**Fix:** Added `.select_related('course', 'assignment')` to the queryset.
For a user with 20 notifications: 40 fewer queries per page load.

**Risk:** Zero. `select_related` is read-only and the serializer fields already
handled `allow_null=True`.

---

## Change 6 — N+1 in `reminder_history` (2 × N count queries per campaign)

**Files:**
- `backend/apps/reminders/views.py:236-239`
- `backend/apps/reminders/serializers.py:41-45`

`get_sent_count` and `get_failed_count` each issued a `COUNT` per campaign.
With 50 campaigns: 100 extra queries per `GET /api/v1/admin/reminders/history/`.

**Fix:** Annotated `_sent_count` and `_failed_count` in `reminder_history`
queryset; serializer uses the annotation when present, falls back to live count
for the single-campaign `reminder_send` response.

**Tests needed (coordinate with qa-tester):**
- `reminder_history` returns `sent_count` and `failed_count` with correct values.
- N+1 test: verify no extra queries emitted (use `django.test.utils.CaptureQueriesContext`).

— backend-engineer
