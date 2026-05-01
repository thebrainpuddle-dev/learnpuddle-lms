---
tags: [review, task/TASK-021, task/TASK-020, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-20
---

# Review: TASK-021 (spec TASK-020) — Education vs Corporate Mode Switching

## Verdict: APPROVE

## Numbering note (for coordinator)

The feature spec lives at `docs/coordination/TASK-020-education-corporate-mode.md`,
but reviewer had already opened `TASK-020-reminders-pii-log-followup.md` as a
reminders follow-up. Backend-engineer registered this feature as
**TASK-021** in the review request. There are now two distinct artifacts with
"TASK-020" in their filenames:

- `docs/coordination/TASK-020-education-corporate-mode.md` (this feature)
- `docs/coordination/TASK-020-reminders-pii-log-followup.md` (unrelated reminders work)

…and the review request is filed as `TASK-021-REVIEW-REQUEST.md`. Coordinator
should reconcile: either rename the feature spec to `TASK-021-*` so the doc
name matches the review, or keep filenames as-is and treat `TASK-021` purely
as the review-request sequence number. I'm accepting the naming as filed.

## Summary

Clean, minimal, display-only terminology switch at the tenant level. Two
additive model fields, a single `get_mode_labels()` helper with safe
override merging, serializer wiring on both public (`/me/`) and admin
(`/settings/`) surfaces. 14 tests cover model, API, and cross-tenant.
Zero risk to existing tenants — default `mode='education'` is a no-op.

## Critical Issues

None.

## Major Issues

None.

## Minor Issues

1. **Silently-dropped non-string overrides** (`serializers_admin.py` L49–L66).
   `validate_mode_label_overrides` accepts `{"course": 42}` as a 200 but
   drops the `course` key. Backend-engineer asked for direction — I'd
   recommend **documenting** the behavior over raising 400 because the
   frontend admin form is the only real client and it already sends strings.
   Low priority; non-blocking. Please add one sentence to the helper's
   docstring making the contract explicit ("non-string values are silently
   dropped; admin UI should validate client-side").
2. **Audit action code.** `SETTINGS_CHANGE` is fine for this pass. If the
   future white-label module grows, a dedicated `MODE_CHANGED` action with
   a `from/to` in `changes` would help rollback/forensics — filing as a
   soft follow-up only.
3. `get_mode_labels()` swallows non-dict `mode_label_overrides`. The
   JSONField default is `dict` and serializer-side coercion produces a
   dict, so this branch is pure defense-in-depth. Fine.

## Verification performed

- `backend/apps/tenants/migrations/0024_tenant_mode.py` — pure `AddField`
  with safe defaults, dependency points at `0023_auditlog_calendar_actions`
  (latest migration before this one). Additive only. No destructive ops.
- `MODE_LABEL_DEFAULTS` (models.py L27–L56) covers all 12 canonical keys
  for both modes; `module` + `streak` identical across modes as noted.
- `get_mode_labels()` (models.py L270–L291) merges correctly: starts from
  mode defaults, layers only string, non-empty overrides. Unknown
  `self.mode` falls back to education map (defensive).
- `TenantThemeSerializer` (serializers.py L14, L33–L38) exposes `mode` +
  `mode_labels` on `GET /api/v1/tenants/me/`.
- `TenantSettingsSerializer` (serializers_admin.py L11–L69) exposes
  `mode`, `mode_label_overrides` (writable), `mode_labels` (read-only).
  `read_only_fields` correctly lists `mode_labels`.
- `tenant_me_view` (views.py L100–L109) has `@permission_classes([IsAuthenticated])`
  + `@tenant_required`.
- `tenant_settings_view` (views.py L193–L214) has
  `@permission_classes([IsAuthenticated])` + `@admin_only` + `@tenant_required`.
  PATCH flow validates, saves, emits `SETTINGS_CHANGE` audit entry. OK.
- `tests_mode_switching.py` — 14 tests confirmed:
  - Model tests: default mode, default overrides, education labels,
    corporate labels, override layering, invalid mode on `full_clean()`.
  - API tests: `/me` shows mode+labels; flipping updates labels;
    override reflected on `/me`; `/settings` GET returns overrides+labels;
    admin PATCH flips mode; admin PATCH writes overrides, teacher /me
    reflects; clearing overrides reverts; non-admin PATCH → 403; invalid
    mode → 400.
  - Cross-tenant: admin of A on B's subdomain hits `@tenant_required`
    403; tenant B's mode remains `education`. Exactly the right guarantee.

## Positive Observations

- Migration is textbook additive-only, with a descriptive docstring.
- The "display layer only, never re-key data" design note in models.py
  L12–L25 is the right mental model and saves future readers from
  mistakes.
- Tests correctly use `APIClient` + `HTTP_HOST` header to exercise
  `TenantMiddleware` — not just a direct view call. Real coverage.
- No unnecessary feature-flag gating proposed; keeping this available to
  all tenants by default is correct (zero cost to `education` tenants).

## Follow-up items

- None blocking. Backend-engineer's open question about a dedicated
  audit action is acknowledged and deferred.
