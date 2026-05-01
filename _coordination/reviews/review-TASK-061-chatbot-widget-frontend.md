---
tags: [review, task/TASK-061, verdict/approve, reviewer/lp-reviewer]
created: 2026-04-22
---

# Review: TASK-061 — Chatbot Widget Frontend

## Verdict: APPROVE

## Summary
Static review only (sandbox blocks Vitest). All claimed files exist, structure matches the work log, and integration points with the backend (TASK-059) are confirmed.

## Checks performed

| Check | Result |
|---|---|
| All 8 files present (services, store, 4 components, barrel, tests) | PASS — verified via `ls` |
| `ChatbotMessage.tsx` avoids `dangerouslySetInnerHTML` | PASS — only mentioned in a comment explaining the avoidance |
| Launcher offset `fixed bottom-6 right-[5.5rem]` (avoids ChatWidget at `right-6`) | PASS — present in `ChatbotLauncher.tsx:40` |
| Backend endpoint `/api/v1/chatbot/ask/` exists (TASK-059) | PASS — `backend/apps/chatbot/views.py` + URL include in `backend/config/urls.py:117-118` |
| Test file has ≥17 `it(`/`test(` cases | PASS — 20 occurrences |
| `chatbotService.ts` exports `askQuestion`, `getHistory`, `deleteHistoryItem` | PASS — all three methods present |
| Barrel export (`index.ts`) re-exports all components | PASS |
| `ChatbotLauncher` mounted in `CourseViewPage.tsx` alongside existing `ChatWidget` | PASS — import at line 9, mount at line 564 with `courseId` guard |

## Minor Observations (non-blocking)
- Storybook omitted (project has no Storybook — acceptable).
- Telemetry left as `// TODO: wire telemetry` (no `useAnalytics()` hook exists yet).
- Vitest execution is sandbox-blocked here; author claims 17/17 pass. Next CI run will confirm.

## Positive Observations
- Clean separation: service → store → components. State machine (IDLE → OPEN_IDLE → OPEN_LOADING → OPEN_ANSWERED/OPEN_ERROR) is a good fit for single-turn RAG.
- Safety-first rendering: no HTML injection; citation chips routed via react-router instead of raw links.
- Optimistic delete with rollback in history is the correct UX pattern.
- Launcher is guarded by `courseId` so it never mounts without context.
