# Phase 2 Implementation Plan — Technical Debt + Frontend Foundation

**Created:** 2026-03-25
**Author:** Coordinator
**Phase:** 2 (Days 4-7)
**Agents:** coordinator, backend-engineer, frontend-engineer, qa-tester, reviewer

---

## Overview

Phase 1 is complete — all 5 P0 security issues and 9 P1 high bugs are resolved (uncommitted on main). Phase 2 focuses on:
1. **Securing Phase 1 work** (testing, committing, branch cleanup)
2. **Backend technical debt** (deduplication, error standardization, notification archival)
3. **Frontend foundation** (WebSocket security, component decomposition, code cleanup)
4. **Test coverage** (raise from ~43% to 60%)

---

## Priority Order & Dependencies

```
TASK-011 (Commit Phase 1 work)
    ├── PREREQUISITE for everything — must be done first
    │
TASK-005 (JWT WebSocket)     TASK-007 (Extract helpers)    TASK-010 (Test coverage)
    │ [frontend]                  │ [backend]                   │ [qa-tester]
    │                             │                             │
TASK-006 (Decompose editor)  TASK-008 (Error standardization) │
    │ [frontend]                  │ [backend]                   │
    │                             │                             │
TASK-012 (Frontend cleanup)  TASK-009 (Notification archival)  │
    │ [frontend]                  │ [backend]                   │
    └─────────────┬───────────────┘                             │
                  ▼                                             │
            Code Review (reviewer)  ◄───────────────────────────┘
```

---

## Day-by-Day Schedule

### Day 4 — Secure Phase 1 + Start Phase 2

| Agent | Task | Hours |
|-------|------|-------|
| **coordinator** | TASK-011: Run tests, prepare commits, get human approval | 1-2h |
| **backend-engineer** | TASK-007: Extract duplicated helpers | 1-2h |
| **frontend-engineer** | TASK-005: Fix JWT in WebSocket URL | 1-2h |
| **qa-tester** | TASK-010: Begin test coverage audit, create factories | 2h |
| **reviewer** | Review TASK-007 and TASK-005 when complete | 1h |

### Day 5 — Component & Quality Work

| Agent | Task | Hours |
|-------|------|-------|
| **backend-engineer** | TASK-008: Error response standardization | 3-4h |
| **frontend-engineer** | TASK-006: Start CourseEditorPage decomposition | 4-6h |
| **qa-tester** | TASK-010: Video pipeline tests + cross-tenant tests | 4h |
| **reviewer** | Review completed tasks | 2h |

### Day 6 — Continued Development

| Agent | Task | Hours |
|-------|------|-------|
| **backend-engineer** | TASK-009: Notification archival | 2-3h |
| **frontend-engineer** | TASK-006: Continue decomposition + TASK-012: Cleanup | 4-6h |
| **qa-tester** | TASK-010: Edge case tests, target 60% | 4h |
| **reviewer** | Review all Phase 2 work | 3h |

### Day 7 — Integration & Review

| Agent | Task | Hours |
|-------|------|-------|
| **All agents** | Integration testing, final reviews, merge conflicts | 4h |
| **coordinator** | Phase 2 completion report, Phase 3 planning | 2h |

---

## Parallel Work Assignments

### Backend Engineer (TASK-007 → TASK-008 → TASK-009)
Sequential: helpers → errors → notifications (each builds on codebase familiarity)

### Frontend Engineer (TASK-005 → TASK-006 → TASK-012)
Start with WebSocket fix (security), then large decomposition, finish with cleanup

### QA Tester (TASK-010)
Continuous: start on Day 4, work through Day 7, building coverage incrementally

### Reviewer
Review each task as completed. Focus on:
- Security implications (TASK-005, TASK-008)
- Behavioral preservation (TASK-006, TASK-007)
- Test quality (TASK-010)

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| CourseEditorPage decomposition introduces regressions | Medium | High | Run E2E tests on course editing flows |
| Error standardization breaks frontend error handling | Medium | Medium | Update frontend error handlers simultaneously |
| Test coverage target (60%) not achievable in time | Medium | Low | Prioritize critical-path tests over percentage |
| WebSocket auth change breaks real-time notifications | Low | High | Test WebSocket connection in staging before merge |

---

## Success Criteria for Phase 2

- [ ] All Phase 1 work committed and pushed
- [ ] Stale branches cleaned up
- [ ] JWT removed from WebSocket URLs
- [ ] CourseEditorPage split into ≤400-line components
- [ ] Duplicated helpers extracted to utils/
- [ ] Error responses standardized
- [ ] Notification archival with 90-day TTL
- [ ] Backend test coverage ≥ 60%
- [ ] All code reviewed and approved
- [ ] CI pipeline green
