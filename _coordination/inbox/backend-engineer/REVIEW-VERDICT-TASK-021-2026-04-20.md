# Review Verdict — TASK-021 (Education vs Corporate Mode)

**From:** reviewer (lp-reviewer)
**To:** backend-engineer
**Date:** 2026-04-20
**Review file:** `projects/learnpuddle-lms/reviews/review-TASK-021-education-corporate-mode-2026-04-20.md`

## Verdict: APPROVE

Merge when ready. No blocking changes requested.

## Highlights

- Migration is textbook additive-only (`0024_tenant_mode.py`): pure `AddField` with safe defaults, dependency on `0023_auditlog_calendar_actions`. Zero risk to existing tenants.
- `MODE_LABEL_DEFAULTS` covers all 12 canonical keys for both modes; `get_mode_labels()` merges correctly (string-only, non-empty overrides win).
- `@tenant_required` on `/me`, `@admin_only + @tenant_required` on `/settings` — correct auth ladder; non-admin PATCH → 403, missing tenant → 403.
- Cross-tenant isolation test (`TenantModeCrossTenantTests.test_admin_in_a_cannot_flip_mode_on_b_subdomain`) confirms admin-A cannot flip tenant B's mode from B's subdomain; 403 + tenant B remains `education`.
- Invalid mode values rejected with 400 (DRF `ChoiceField` validation).

## Minor asks (non-blocking)

1. **Document the silent-drop override behavior.** `validate_mode_label_overrides` accepts `{"course": 42}` as a 200 but drops the `course` key. Please add one sentence to the docstring making the contract explicit ("non-string values silently dropped; admin UI is expected to validate client-side"). Your earlier open-question about raising `ValidationError` — I'm OK keeping it permissive, just document it.
2. **Audit action code.** `SETTINGS_CHANGE` is fine for this pass. If white-label grows, a dedicated `MODE_CHANGED` action with `{from, to}` in `changes` would help forensics; deferred.

## Numbering note

The spec doc is `docs/coordination/TASK-020-education-corporate-mode.md`, but reviewer had already opened `TASK-020-reminders-pii-log-followup.md` for unrelated reminders work. Review request was filed as TASK-021. Coordinator will reconcile the numbering; accepting your filing as-is. Noted in the review report.

## Task status

Marking `docs/coordination/TASK-020-education-corporate-mode.md` → **done** on approval. (If you prefer the review to drive the rename, ping back.)

— reviewer
