# TASK-011: Branch Cleanup and Commit Uncommitted Work

**Priority:** P0 (Critical — all work is at risk)
**Phase:** 1 (wrap-up)
**Status:** todo
**Assigned:** coordinator (needs human approval)
**Estimated:** 1 hour

## Problem

ALL Phase 1 work (14 security/performance fixes, 4 task deliverables) exists as **uncommitted changes on main**. This is extremely fragile:
- Any `git checkout` or `git clean` could destroy the work
- Multiple worktrees may have overlapping changes
- 36 files modified, 1,057 insertions

## Actions Required

### 1. Test All Changes
```bash
docker compose up -d
docker compose exec web pytest --cov --cov-fail-under=60
cd frontend && npm test && npm run build
```

### 2. Commit Cohesive Change Sets
Break into logical commits:
1. **Security hardening** — tenant_middleware, webhook_views, serializers, nginx, docker-compose
2. **Tenant isolation** — progress models + migration
3. **Password validation** — superadmin_serializers, admin_views, AcceptInvitationPage
4. **Performance** — N+1 annotations, React.lazy code splitting
5. **CI/CD improvements** — ci.yml changes

### 3. Delete Stale Branches
```bash
git branch -d codex/session-idle-timeout-fix    # Fully superseded by main
git branch -d claude/nostalgic-tu                # No commits ahead
git branch -d claude/festive-heisenberg          # No commits ahead
```

### 4. Fix and Merge admiring-pike
- Fix silent ID dropping in `assigned_teachers` validation
- Then merge (most impactful remaining fix)

### 5. Evaluate fix/admin-panel-bugs
- Cherry-pick valid teacher validation commit
- Discard the rest (stale/duplicate)

## Acceptance Criteria

- [ ] All tests pass
- [ ] Changes committed in logical groups
- [ ] Stale branches deleted
- [ ] No uncommitted work at risk
