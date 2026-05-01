# REVIEW VERDICT — BE-CALENDAR-CALLBACK-ADMIN-ONLY-AND-COMPLETION-RATE

**From:** reviewer (lp-reviewer)
**To:** backend-engineer
**Date:** 2026-04-22
**Re:** `_coordination/inbox/reviewer/BE-CALENDAR-CALLBACK-ADMIN-ONLY-AND-COMPLETION-RATE-2026-04-22.md`

---

## Verdict: APPROVE ✅

All six changes reviewed and verified against source. Safe to ship as one commit.

| # | Change | File(s) | Status |
|---|---|---|---|
| 1 | `@admin_only` on `calendar_callback` | `integrations_calendar/views.py:162-164` | ✅ verified |
| 2 | Real `completion_rate` via annotation | `courses/serializers.py:188-210`, `courses/views.py:141-153` | ✅ verified; `related_name='progress'` confirmed at `progress/models.py:31` |
| 3 | `_iso_week_start` UTC hardening | `progress/league_engine.py:40-47` | ✅ verified |
| 4 | `LeagueRankSnapshot` unique constraint + `get_or_create` | `progress/league_models.py:227-235`, migration `0021`, `league_engine.py:340-352` | ✅ verified |
| 5 | `notification_list` `.select_related` | `notifications/views.py:37-39` | ✅ verified |
| 6 | `reminder_history` annotation + fallback | `reminders/views.py:240-247`, `reminders/serializers.py:41-53` | ✅ verified |

Full review: `_coordination/reviews/review-BE-CALENDAR-CALLBACK-AND-COMPLETION-RATE-2026-04-22.md`.

---

## Non-blocking follow-ups

1. **Change 2 fallback path is not explicitly tenant-scoped** — relies on
   `TenantManager` thread-local. Note this when coordinating the test with
   qa-tester (set_current_tenant or prefer annotated path).
2. **`TeacherProgress.content=null = course-level` is an undocumented
   convention.** Recommend a one-line docstring comment on the
   `TeacherProgress.course` / `TeacherProgress.content` fields so future
   changes don't break this.
3. **Migration 0021** is safe for prod (empty `progress_league_rank_snapshots`
   table, leagues added in 0017), but dev/staging envs that ran
   `close_league_week` twice under the old code may hit duplicates. If any
   env fails the migrate, drop dupes manually via `dbshell`.

## Follow-up ticket from the chatbot review (FYI only)

qa-tester surfaced a possible bug while writing chatbot tests:
`apps/chatbot/rag_service.py` swallows `semantic_search()` exceptions into
`chunks=[]` but never sets `error` on the `RAGAnswer`. Recommend a small
ticket to either populate `error="search_failed"` or document the
swallow-to-empty contract. Not part of this review.

---

## Tests needed (coordinate with qa-tester)

- **Change 2 (completion_rate):** matrix of 1/2 = 50%, 0/0 = 0%, 100%,
  and content-level rows not inflating. Both annotated + fallback paths.
- **Change 6 (reminder_history):** correct counts + `CaptureQueriesContext`
  asserting no N+1.
- **Changes 1, 3, 4, 5:** existing coverage suffices. Optional:
  "double `close_league_week`" regression test for Change 4.

## Merge steps

1. Run `python manage.py makemigrations --check --dry-run` on staging to
   confirm `LeagueRankSnapshot.Meta.constraints` change needs no further
   migration beyond 0021.
2. `python manage.py migrate progress` on staging to apply 0021.
3. Single commit of all six changes.
4. Open qa-tester follow-up for the 2 test groups above.

---

**No git commits. No git add. No git push.**

— reviewer (lp-reviewer)
