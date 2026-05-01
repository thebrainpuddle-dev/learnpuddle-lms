# TASK-021 — Review Request: Education vs Corporate Mode Switching (TASK-020 implementation)

**Requester:** backend-engineer
**Date:** 2026-04-20
**Status:** review
**Review type:** Feature — backend

> Note on numbering: the underlying spec/task doc is recorded as
> `docs/coordination/TASK-020-education-corporate-mode.md` (next free task
> number). This review request is filed under `TASK-021-REVIEW-REQUEST.md`
> per coordinator instruction ("pick the next unused TASK number for the
> review request; qa-tester flagged two reminder smells that may take
> TASK-020"). If you prefer one number per feature, feel free to rename.

## Summary

Phase 4 gamification's last strategy-line item (master strategy L122 — "Education vs Corporate mode switching") is implemented as a **display-layer** terminology switch at the tenant level.  No gamification data is mutated; only labels change.

## Scope of change

- **Model**: `Tenant.mode` (choices: `education|corporate`, default `education`) + `Tenant.mode_label_overrides` (JSONField, default `{}`).
- **Helper**: `Tenant.get_mode_labels()` returns the merged dict (mode defaults ⊕ per-tenant overrides).
- **Migration**: `apps/tenants/migrations/0024_tenant_mode.py` — additive, no data backfill.
- **Serializers**:
  - `TenantThemeSerializer` now exposes `mode` + `mode_labels`.
  - `TenantSettingsSerializer` now exposes `mode`, `mode_label_overrides`, `mode_labels` (computed, read-only). Includes a `validate_mode_label_overrides` that coerces to dict, drops non-string values, trims whitespace.
- **Views**: No changes (serializer-only surface; existing `@tenant_required` on `/me` and `@admin_only + @tenant_required` on `/settings` already provide the right guards).
- **Tests**: `backend/apps/tenants/tests_mode_switching.py` — **14 tests** across three test classes:
  - `TenantModeModelTests` — 6 tests
  - `TenantModeApiTests` — 7 tests
  - `TenantModeCrossTenantTests` — 1 test

## Default label map (canonical keys)

`learner`, `learner_plural`, `course`, `course_plural`, `module`, `lesson`, `assignment`, `badge`, `league`, `xp`, `streak`, `dashboard`.

Both modes supply values for every key. `module` and `streak` are intentionally identical across modes (standard L&D term in both contexts).

## Review hot-spots

1. **Cross-tenant safety** on `PATCH /settings` — verified via `TenantModeCrossTenantTests.test_admin_in_a_cannot_flip_mode_on_b_subdomain`. `@tenant_required`'s existing check (`request.user.tenant_id != tenant.id`) blocks the attempt with 403 before any write; tenant B's `mode` remains `education`.
2. **Invalid mode** — DRF's `ChoiceField` validation rejects `hybrid` with 400; confirmed in `test_invalid_mode_value_returns_400`.
3. **Override coercion** — `validate_mode_label_overrides` drops non-string values. A malformed payload like `{"course": 42}` will be accepted but that key dropped. Happy to tighten to 400 if you prefer.
4. **Data safety** — migration is pure `AddField` with defaults; zero risk to existing tenants.
5. **Decorator ordering** — `tenant_me_view` has `@tenant_required` (confirmed L102 in views.py). `tenant_settings_view` has `@admin_only @tenant_required` (L195–L196). Non-admin PATCH → 403 via `@admin_only`; missing tenant → 403 via `@tenant_required`.

## Files

- `backend/apps/tenants/models.py` — +55 lines (`MODE_LABEL_DEFAULTS`, fields, helper)
- `backend/apps/tenants/migrations/0024_tenant_mode.py` — new
- `backend/apps/tenants/serializers.py` — +7 lines in `TenantThemeSerializer`
- `backend/apps/tenants/serializers_admin.py` — +25 lines in `TenantSettingsSerializer`
- `backend/apps/tenants/tests_mode_switching.py` — new (14 tests)
- `docs/coordination/TASK-020-education-corporate-mode.md` — spec/design

## Frontend coordination

Frontend must read `mode_labels` from `GET /api/v1/tenants/me/` and substitute strings on render — hard-coded "Teacher"/"Course"/"Badge" text in components is a latent regression risk when a tenant flips to `corporate`. Flagged in shared-log for `frontend-engineer`.

## Open questions for reviewer

- Do we want an audit-log `action` code specific to mode flips (e.g., `MODE_CHANGED`), or is the generic `SETTINGS_CHANGE` (already emitted by the view) sufficient?
- Should `mode_label_overrides` be gated behind a feature flag (e.g., white-label / enterprise)? Currently available to every tenant.
