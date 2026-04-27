# TASK-017 — Daily / Weekly Challenges (Phase 4 Gamification)

**Owner:** backend-engineer
**Status:** done
**Phase:** 4 — Gamification
**Strategy line:** Master strategy line 118 — "Daily / weekly challenges."

## Goal

Add a tenant-scoped **challenge system** that lets school admins author
short-lived, goal-based activities for their teachers (e.g. "Complete 5
lessons today", "Earn 300 XP this week", "Finish course X", "Maintain a
5-day streak"). Teachers see active challenges + live progress; on
completion, the teacher earns XP and optionally a badge — re-using the
existing XP ledger + badge engine so no parallel reward path is needed.

## Models

Added to `backend/apps/progress/challenge_models.py`:

### Challenge

- `id` UUIDv4
- `tenant` FK → `tenants.Tenant` (via `TenantManager` + `all_objects`)
- `title`, `description`
- `challenge_type` — `DAILY` or `WEEKLY`
- `goal_type` — enumerated (see below)
- `goal_target` — positive integer count/amount
- `goal_reference_id` — nullable UUID (e.g. course for `finish_course`)
- `start_at`, `end_at` — active window (tz-aware)
- `reward_xp` — non-negative integer (default 0)
- `reward_badge` — optional FK → `BadgeDefinition`
- `is_active` — manual kill switch
- `created_at`, `updated_at`, `created_by`

Indexes on `(tenant, is_active, end_at)` and `(tenant, challenge_type)`.

### ChallengeParticipation

- `id` UUIDv4
- `tenant` FK
- `challenge` FK → `Challenge`
- `teacher` FK → `users.User`
- `progress_value` — int (default 0)
- `completed_at` — nullable datetime
- `last_reference_key` — last reference_type/reference_id key used to
  increment progress (enables idempotency across retries)
- `increments_log` — JSONField list of `{ref_key, value, ts}` entries,
  bounded to the last ~50 events (idempotency + audit)
- `reward_issued` — bool (prevents double-reward)
- `created_at`, `updated_at`
- Unique constraint on `(challenge, teacher)`.

## Supported goal types

1. `complete_lessons` — increment by 1 per unique `Content` completion.
2. `earn_xp` — increment by xp delta on `XPTransaction` creation.
3. `finish_course` — increment to target (1) when `goal_reference_id`
   course is completed.
4. `maintain_streak` — evaluated on-demand from `TeacherStreak.current_streak`
   vs target (reaches target → complete).
5. `submit_assignments` — increment by 1 per new `AssignmentSubmission`.

All goal types use a per-event `(reference_type, reference_id)` dedup key
stored in `last_reference_key` + `increments_log` for idempotency.

## Engine

`backend/apps/progress/challenge_engine.py` exposes:

- `active_challenges(tenant, now=None, challenge_type=None)`
- `get_or_create_participation(teacher, challenge)`
- `record_event(teacher, event_type, reference_id=None, reference_type='', amount=1)`
  — the single entry-point used by signals. Walks every active challenge
  matching the event type, increments participation progress if the
  event is not a duplicate, and fires reward issuance when the target
  is first reached.
- `issue_challenge_rewards(participation)` — idempotent reward path that
  awards XP via `award_xp(..., reason='challenge_reward', reference_type='challenge', reference_id=challenge.id)`
  and awards the optional badge.
- `serialize_challenge_for_teacher(challenge, teacher)` — shape for
  teacher-facing list (title, description, type, window, progress, target,
  percent, completed_at, reward summary).

## Signals

New `challenge_signals.py` wires into three existing signal paths:

- `progress.TeacherProgress.post_save` — on `COMPLETED` with `content_id`,
  emits `record_event(event_type='content_completion', reference_id=content.id, reference_type='content')`.
  If the whole course finished, additionally emits `event_type='course_completion'`.
- `progress.AssignmentSubmission.post_save` — on new SUBMITTED, emits
  `event_type='assignment_submission'`.
- XP award hook — we piggy-back inside `gamification_engine.award_xp` by
  calling `record_event(event_type='earn_xp', reference_id=txn.id, reference_type='xp_transaction', amount=txn.xp_amount)`
  after the XPTransaction is written. The dedup key is the transaction id
  so a resaved txn cannot double-count.

`maintain_streak` challenges are evaluated inline on `TeacherProgress.post_save`
(and via the engine when listing) so a long-running streak ticks the bar
the next time the teacher does anything.

## API endpoints

Teacher (role: `TEACHER`, `HOD`, `IB_COORDINATOR`):

- `GET /api/v1/gamification/challenges/` — list active challenges with
  progress for the current user.
- `GET /api/v1/gamification/challenges/completed/` — list recently
  completed challenges (last 30 days).

Admin (`SCHOOL_ADMIN`, `SUPER_ADMIN`):

- `GET    /api/v1/gamification/admin/challenges/`
- `POST   /api/v1/gamification/admin/challenges/`
- `PATCH  /api/v1/gamification/admin/challenges/<uuid:id>/`
- `DELETE /api/v1/gamification/admin/challenges/<uuid:id>/` (soft disable via `is_active=False`)

All admin endpoints use `@admin_only + @tenant_required` and set `tenant`
from `request.tenant`. Cross-tenant IDs are not resolvable (404).

## Idempotency guarantees

- **XP events:** dedup on `XPTransaction.id`.
- **Lesson events:** dedup on `Content.id` per participation — re-saving a
  TeacherProgress row from COMPLETED → COMPLETED will not double-count.
- **Assignment events:** dedup on `AssignmentSubmission.id`.
- **Course finish:** dedup on `Course.id` per participation.
- Reward issuance is guarded by `participation.reward_issued` — even if
  the target is crossed twice (e.g. an admin later bumps the target down),
  no duplicate reward is awarded.

## Migration

`0018_challenges.py` — additive only. Two new tables, no backfill. Active
challenges only appear once admins create them.

## Non-goals

- Frontend admin authoring UI — handed to frontend-engineer after review.
- Cross-tenant/global challenges — intentionally excluded by the
  multi-tenant rules.
- Recurring auto-challenges (e.g. "new daily challenge every morning") —
  future work; admins create each challenge explicitly for now.

## Test plan

See `backend/apps/progress/tests_challenges.py`. Coverage includes:

- **Models:** tenant FK + `TenantManager`, choice validation, active-window
  helper, unique `(challenge, teacher)` constraint.
- **Engine:** progress increment, idempotency dedup, completion detection
  with boundary/over-shoot, reward issuance (XP + badge), opt-out
  suppression, cross-tenant isolation.
- **Signals:** creating a `TeacherProgress` COMPLETED row bumps a
  `complete_lessons` challenge; an `AssignmentSubmission` bumps a
  `submit_assignments` challenge; an XP transaction bumps an `earn_xp`
  challenge; a second save of the same row is a no-op.
- **API:** admin CRUD round-trip, teacher list shape, cross-tenant 404,
  non-admin forbidden.
