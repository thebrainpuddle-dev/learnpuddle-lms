# TASK-018 — Mastery Points (Phase 4 Gamification)

**Owner:** backend-engineer
**Status:** done
**Phase:** 4 — Gamification
**Strategy line:** Master strategy line 113 — "Dual points: XP (effort) +
**Mastery Points** (competence)".

## Goal

Introduce a second gamification currency — **Mastery Points (MP)** —
that tracks demonstrated competence, in parallel to XP which tracks
effort. MP is awarded only when a teacher clears a configurable score
threshold on assessed work (high-scoring quiz, graded assignment) or on
course-level mastery (average quiz score across the course). MP lives in
its own immutable ledger and denormalized summary so the two currencies
stay independent and can evolve / be displayed separately.

## Design decision — new summary vs. extending XP summary

Chose **`TeacherMasterySummary`** (new model) rather than adding
`mastery_points_total` to `TeacherXPSummary`.

Rationale:

1. **Separation of semantics.** XP drives levels + weekly league
   standings + streak bonuses. MP is a competence indicator; its
   aggregation axes (per-skill, per-course) differ and should not
   contaminate the XP summary.
2. **Future per-skill hooks.** `MasteryPointTransaction.skill_code`
   exists today (nullable, no migration needed) so a future
   per-skill rollup can aggregate directly from the ledger without
   touching XP.
3. **Independent lifecycle.** Admins may later want to reset MP (e.g.
   year boundary) without disturbing XP history.
4. **Mirrors the existing pattern.** `XPTransaction` →
   `TeacherXPSummary`. Keeping `MasteryPointTransaction` →
   `TeacherMasterySummary` parallel is easier to maintain.

Opt-out is **shared** with XP (`TeacherXPSummary.opted_out`): teachers
never have to opt out of two separate gamification systems.

## Models (new)

`apps/progress/gamification_models.py`:

### `MasteryPointTransaction`

- `tenant` FK (`TenantManager`)
- `teacher` FK
- `amount` Decimal(10, 2) — signed; negatives allowed for
  admin adjustments
- `reason` — one of `quiz_mastery`, `assignment_mastery`,
  `course_mastery_bonus`, `admin_adjust`
- `description`, `reference_id`, `reference_type`
- `skill_code` — nullable, future per-skill rollup hook
- Unique partial index on
  `(teacher, reason, reference_type, reference_id)` when
  `reference_id IS NOT NULL` — enforces dedup at the DB level.

### `TeacherMasterySummary`

- `tenant` FK, `teacher` OneToOne
- `total_mastery_points`, `mp_this_month`, `mp_this_week` — Decimal(12, 2)
- `last_mp_at`
- `refresh_from_transactions()` recomputes all three totals from the
  ledger, clamped to zero.

## `GamificationConfig` additions

| Field | Default | Meaning |
|-------|---------|---------|
| `mp_quiz_threshold_percent` | 80 | Min quiz score % for MP |
| `mp_quiz_weight` | 1.0 | MP = round(score% * weight) |
| `mp_assignment_threshold_percent` | 80 | Min assignment score % for MP |
| `mp_assignment_weight` | 1.0 | MP = round(raw_score * weight) |
| `mp_course_bonus` | 50 | Flat bonus on course mastery |

## Source weights / formulas

1. **Quiz Mastery** — `score_percent = score / max_score * 100`; awarded
   `round(score_percent * mp_quiz_weight)` when
   `score_percent >= mp_quiz_threshold_percent`.
2. **Assignment Mastery** — `score_percent = score / max_score * 100`;
   awarded `round(score * mp_assignment_weight)` when
   `score_percent >= mp_assignment_threshold_percent`. The raw score
   (not percent) is used so weighted assignments naturally yield more
   MP.
3. **Course Mastery Bonus** — average of all graded quiz submissions
   in the course; awarded flat `mp_course_bonus` when average ≥ quiz
   threshold. Idempotent on `(teacher, course)`.

## Signal hook points

Wired into existing `apps/progress/gamification_signals.py` (no new
signals module — keeps related handlers discoverable):

- **Quiz submission** — `on_quiz_submission` post-save handler
  appends a call to `award_quiz_mastery(instance)` after the XP award
  path. Exceptions are caught + logged so MP errors never break XP.
- **Assignment grade** — new `on_assignment_submission_mastery`
  handler fires on `status=GRADED, score IS NOT NULL` (separate from
  the existing XP handler which is `created`-only). Re-grades are
  safe: the unique constraint on the MP ledger blocks double-award.
- **Course completion** — inside the existing `TeacherProgress`
  handler, right after the course_completion XP is awarded
  (i.e. when the last content is completed), we call
  `award_course_mastery_bonus(teacher, course)`. Dedup is again
  enforced at the DB level.

## Engine (`mastery_engine.py`)

- `award_mastery_points(teacher, reason, amount, …)` — the single
  write path. Returns the new transaction or `None` (no-tenant,
  opt-out, inactive, non-positive amount for non-admin reasons,
  duplicate reference).
- `award_quiz_mastery(submission)` — source adapter for
  `QuizSubmission`.
- `award_assignment_mastery(submission)` — source adapter for
  `AssignmentSubmission` (only acts when `status='GRADED'`).
- `award_course_mastery_bonus(teacher, course)` — computes
  course-wide average and delegates.
- `get_mastery_summary(teacher)` — read helper, creates the row on
  first access.

## API

Teacher (`TEACHER`, `HOD`, `IB_COORDINATOR`, `SCHOOL_ADMIN`):

- `GET /api/v1/gamification/mastery/` — `TeacherMasterySummary`.
- `GET /api/v1/gamification/mastery/history/` — paginated ledger for
  the calling teacher.

Admin (`SCHOOL_ADMIN`, `SUPER_ADMIN`):

- `GET /api/v1/gamification/admin/mastery/leaderboard/` — top-N
  teachers in tenant, ordered by `total_mastery_points`. Supports
  `?limit=` (default 25, max 200).

## Idempotency

Every award is keyed on
`(teacher, reason, reference_type, reference_id)` via a partial unique
index (only when `reference_id IS NOT NULL`). The engine wraps creates
in `transaction.atomic()` and catches `IntegrityError` — duplicate
awards return `None` cleanly. This means:

- Re-saving a `QuizSubmission` (e.g. admin manual re-grade) does not
  double-award MP.
- Re-saving an `AssignmentSubmission` with updated score does not
  double-award MP.
- Re-firing the course-completion hook does not double-award the
  course bonus.

Admin adjustments (`reason='admin_adjust'`) with `reference_id=NULL`
are explicitly not deduped — allowing multiple manual corrections.

## Cross-tenant isolation

- `MasteryPointTransaction` and `TeacherMasterySummary` both use
  `TenantManager` + `all_objects`.
- `award_mastery_points` derives `tenant` from
  `teacher.tenant` — a teacher can only ever write to their own
  tenant's ledger.
- API views filter with `all_objects.filter(tenant=request.tenant)`
  and compute rank/summary from that tenant-scoped queryset.

## Migration

`apps/progress/migrations/0019_mastery_points.py` — additive-only:

- Adds 5 fields to `GamificationConfig`.
- Creates `MasteryPointTransaction` and `TeacherMasterySummary`
  tables + their indexes + the partial unique constraint.

No backfill needed — MP accumulates going forward.

## Tests

`apps/progress/tests_mastery_points.py` — 20 test cases total:

- **Model (5):** tenant FK, decimal precision, TenantManager isolation,
  unique-constraint dedup, summary aggregation.
- **Engine (9):** happy path, idempotency, opt-out blocks award,
  gamification-inactive blocks award, quiz above threshold, quiz below
  threshold, quiz weight scaling, assignment grade award,
  assignment not graded, course bonus awarded, course bonus below
  threshold, `get_mastery_summary` is tenant-scoped.
- **Signal (5):** quiz ≥ threshold triggers MP, quiz < threshold
  does not, quiz re-save does not double-award, assignment GRADED
  triggers MP, course completion triggers bonus.
- **API (5):** teacher summary, teacher history pagination, admin
  leaderboard ordering, leaderboard tenant isolation, teacher history
  isolation.

Sandbox does not have docker/pytest available to run the Django test
runner; reviewer should run
`pytest apps/progress/tests_mastery_points.py -v` in CI.

## Risks & known limitations

- `award_quiz_mastery` keys off `Assignment.max_score` — legacy rows
  without a max_score default to 100, which is already the model
  default.
- The course mastery bonus only considers `QuizSubmission` (legacy
  quiz rows). If a tenant moves fully to the newer `QuizAttempt`
  (assessment_models) for all quizzes, the bonus formula will need to
  be extended to cover that ledger too. Tracking as a follow-up.
- MP is not displayed anywhere yet — frontend work is a follow-up for
  frontend-engineer.
- No admin UI to manually adjust MP (parallel to `xp_adjust`) — can
  use `award_mastery_points(reason='admin_adjust')` in a shell; if the
  reviewer wants an endpoint, happy to add in a follow-up.
