# TASK-020 — Education vs Corporate Mode Switching

**Owner:** backend-engineer
**Status:** done (APPROVE — reviewer/lp-reviewer, 2026-04-20)
**Phase:** 4 (Gamification — final strategy line, master-strategy L122)
**Date:** 2026-04-20
**Review:** `projects/learnpuddle-lms/reviews/review-TASK-021-education-corporate-mode-2026-04-20.md`

## Goal

Introduce a tenant-level `mode` flag (`education` | `corporate`) that flips
default terminology across the product without mutating stored data.  The
backend provides a canonical **label map** keyed by mode; the frontend is
expected to substitute strings on render.  Admins can additionally supply a
per-tenant `mode_label_overrides` JSON to customise specific labels (e.g., a
"Masterclass" override for "Course").

This closes the last open item on the Phase 4 gamification strategy line:

> "Education vs Corporate mode switching"  — master strategy L122

## Design

### Model

`apps/tenants/models.py::Tenant`

- `mode` — `CharField(max_length=20, choices=MODE_CHOICES, default='education')`
  - `MODE_CHOICES = (('education', 'Education'), ('corporate', 'Corporate'))`
- `mode_label_overrides` — `JSONField(default=dict, blank=True)`
  - Per-tenant free-form overrides (e.g., `{"course": "Masterclass"}`)
  - Overrides are applied **on top of** the default map for the active mode.

### Default label maps

```python
MODE_LABEL_DEFAULTS = {
    "education": {
        "learner":        "Teacher",
        "learner_plural": "Teachers",
        "course":         "Course",
        "course_plural":  "Courses",
        "module":         "Module",
        "lesson":         "Lesson",
        "assignment":     "Assignment",
        "badge":          "Badge",
        "league":         "League",
        "xp":             "XP",
        "streak":         "Streak",
        "dashboard":      "Dashboard",
    },
    "corporate": {
        "learner":        "Employee",
        "learner_plural": "Employees",
        "course":         "Training Program",
        "course_plural":  "Training Programs",
        "module":         "Module",
        "lesson":         "Task",
        "assignment":     "Task",
        "badge":          "Achievement",
        "league":         "Tier",
        "xp":             "Points",
        "streak":         "Streak",
        "dashboard":      "Workspace",
    },
}
```

### Helper

`Tenant.get_mode_labels()` returns the merged dict:

```python
labels = MODE_LABEL_DEFAULTS[tenant.mode].copy()
labels.update(tenant.mode_label_overrides or {})
return labels
```

### API surface

| Endpoint | Method | Change |
|---|---|---|
| `GET /api/v1/tenants/me/` | GET | Adds `mode`, `mode_labels` (merged) |
| `GET /api/v1/tenants/settings/` | GET | Adds `mode`, `mode_label_overrides`, `mode_labels` (merged) |
| `PATCH /api/v1/tenants/settings/` | PATCH | Accepts `mode`, `mode_label_overrides` |

Both `/me` and `/settings` already use `@tenant_required`.
`/settings` additionally uses `@admin_only`, so non-admins receive `403`.

Invalid `mode` values produce `400` (DRF choice validation).
Cross-tenant flips are impossible: `tenant_settings_view` writes to
`request.tenant`, which is always the caller's own tenant.

### Data safety

- Purely additive migration — no backfill of gamification data.
- Existing rows receive `mode='education'` (the default), so behaviour is
  unchanged for all current tenants.
- Mode only affects display via `mode_labels`; no field, badge rarity, or
  XP computation is re-keyed.

## Tests

`backend/apps/tenants/tests_mode_switching.py`

1. Model defaults (`mode='education'`, `mode_label_overrides={}`).
2. `get_mode_labels()` returns education defaults.
3. `get_mode_labels()` returns corporate defaults when mode flipped.
4. Override applied on top of active mode.
5. `GET /me` includes `mode` + `mode_labels`.
6. `GET /settings` includes `mode`, `mode_label_overrides`, `mode_labels`.
7. Admin `PATCH /settings` flips mode, response labels reflect new mode.
8. Admin `PATCH /settings` writes overrides; `/me` reflects them.
9. Clearing override (`{}`) reverts the label to the mode default.
10. Non-admin `PATCH /settings` → `403`.
11. Invalid mode value → `400`.
12. Cross-tenant: admin in tenant A calling `/settings` on tenant-B subdomain
    is blocked by `@tenant_required` (the cross-tenant check in the
    decorator returns `403`).

## Files touched

- `backend/apps/tenants/models.py` — fields + helper
- `backend/apps/tenants/migrations/0024_tenant_mode.py` — additive
- `backend/apps/tenants/serializers.py` — `TenantThemeSerializer` exposes mode
- `backend/apps/tenants/serializers_admin.py` — `TenantSettingsSerializer` R/W
- `backend/apps/tenants/views.py` — include merged `mode_labels` in responses
- `backend/apps/tenants/tests_mode_switching.py` — 12 tests

## Risks

- **Frontend divergence** — FE must read `mode_labels` and render them;
  any hard-coded string ("Teachers") is a regression surface.  Out of scope
  for backend; flagged to frontend-engineer via shared-log.
- **Override drift** — if future label keys are added to the default map,
  tenants with overrides keep working (they fall through to defaults for
  unknown keys).  Documented in the helper.
