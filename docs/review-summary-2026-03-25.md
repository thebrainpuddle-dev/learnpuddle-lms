---
tags: [review, summary, reviewer/lp-reviewer]
created: 2026-03-25
---

# Code Review Summary — 2026-03-25

## Reviewer: lp-reviewer (Principal Engineer)
## Scope: All branches with commits ahead of `main`

---

## Branches Reviewed

| # | Branch | Commits | Verdict | Key Issue |
|---|--------|---------|---------|-----------|
| 1 | `claude/admiring-pike` | 2 | **REQUEST_CHANGES** | Silent ID dropping in assigned_teachers validation is a security/data integrity gap |
| 2 | `claude/wizardly-engelbart` | 1 | **APPROVE** (conditional) | Already on main; remaining serializer changes redundant with admiring-pike |
| 3 | `codex/session-idle-timeout-fix` | 1 | **REQUEST_CHANGES** | Already on main in improved form; branch is stale, recommend deletion |
| 4 | `feature/ui-improvements-and-fixes` | 1 | **REQUEST_CHANGES** | Smoke test imports deleted `apps.media` module; tenant mismatch test asserts wrong behavior |
| 5 | `fix/admin-panel-bugs` | 5 | **REQUEST_CHANGES** | Partially stale; bulk import leaks cross-tenant user existence; serializer fix uses wrong DRF API |

---

## Cross-Branch Observations

### 1. Duplicate Work Across Branches
Three branches independently fix the same FormData `Content-Type` header bug:
- `claude/admiring-pike` (commit `bb7e02e`)
- `fix/admin-panel-bugs` (commit `446b16b`)
- Main already has the fix

**Action**: Coordinate merges to avoid conflicts. `admiring-pike` has the most complete fix (backend + frontend).

### 2. Serializer `assigned_teachers` — Three Different Approaches
- **Main**: `PrimaryKeyRelatedField(many=True)` with `.child_relation.queryset` (correct DRF pattern)
- **admiring-pike**: `ListField(child=UUIDField())` with custom `validate_assigned_teachers` (different approach, silently drops invalid IDs)
- **fix/admin-panel-bugs**: `PrimaryKeyRelatedField(many=True)` with `.queryset` directly (broken — doesn't work with `many=True`)

**Recommendation**: Stick with main's approach. If switching to admiring-pike's `ListField` approach, fix the silent ID dropping.

### 3. Stale Branches
- `codex/session-idle-timeout-fix` — fully superseded by main
- `claude/nostalgic-tu` and `claude/festive-heisenberg` — no commits ahead of main

**Action**: Delete stale branches to reduce confusion.

### 4. Security Findings (Priority)
| Severity | Branch | Issue |
|----------|--------|-------|
| **HIGH** | `fix/admin-panel-bugs` | Bulk import reveals if email exists in another tenant |
| **MEDIUM** | `claude/admiring-pike` | Silent ID dropping could mask data corruption |
| **LOW** | `claude/wizardly-engelbart` | Tenant middleware error message leaks internal details |

### 5. Test Coverage Gaps
- No unit tests for `validate_assigned_teachers` custom validator
- No tests for `_normalize_multipart_list_fields` normalization logic
- Smoke tests depend on `apps.media` module that may be deleted

---

## Recommended Merge Order

1. **Do not merge any branch as-is** — all need changes
2. Fix `admiring-pike` security issues → merge first (most impactful bug fix)
3. Evaluate `fix/admin-panel-bugs` teacher validation commit for cherry-pick
4. Delete stale branches: `codex/session-idle-timeout-fix`, `claude/nostalgic-tu`, `claude/festive-heisenberg`
5. Decide on `apps/media` module fate before merging UI improvements branch

---

## Detailed Reviews
- [review-admiring-pike.md](./review-admiring-pike.md)
- [review-wizardly-engelbart.md](./review-wizardly-engelbart.md)
- [review-codex-session-idle-timeout-fix.md](./review-codex-session-idle-timeout-fix.md)
- [review-feature-ui-improvements.md](./review-feature-ui-improvements.md)
- [review-fix-admin-panel-bugs.md](./review-fix-admin-panel-bugs.md)
