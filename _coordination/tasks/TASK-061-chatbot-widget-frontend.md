---
id: TASK-061
title: Chatbot Widget (frontend for TASK-059 RAG backend)
status: status/done
assigned: frontend-engineer
created: 2026-04-20
completed: 2026-04-20
---

# TASK-061 — Chatbot Widget Frontend

## Summary

Floating bottom-right launcher on teacher course-detail pages that opens a slide-in panel with single-turn RAG Q&A (no multi-turn memory). Backed by the `/api/v1/chatbot/ask/` endpoint (TASK-059).

## Work Log

### Files Created

| File | Purpose |
|------|---------|
| `frontend/src/services/chatbotService.ts` | Service: `askQuestion`, `getHistory`, `deleteHistoryItem` |
| `frontend/src/stores/ragChatbotStore.ts` | Zustand store with state machine (IDLE → OPEN_IDLE → OPEN_LOADING → OPEN_ANSWERED / OPEN_ERROR) |
| `frontend/src/components/chatbot/ChatbotLauncher.tsx` | Floating launcher button (sky-600, `fixed bottom-6 right-[5.5rem]`) |
| `frontend/src/components/chatbot/ChatbotPanel.tsx` | Slide-in Q&A panel with focus trap, Esc/Enter/Tab keyboard nav, aria-live |
| `frontend/src/components/chatbot/ChatbotMessage.tsx` | Answer renderer with [N] citation chips deep-linking via react-router. No dangerouslySetInnerHTML. |
| `frontend/src/components/chatbot/ChatbotHistory.tsx` | History list with optimistic delete + rollback on failure |
| `frontend/src/components/chatbot/index.ts` | Barrel export |
| `frontend/src/components/chatbot/ChatbotWidget.test.tsx` | 17 Vitest tests (all passing) |

### Files Modified

| File | Change |
|------|--------|
| `frontend/src/pages/teacher/CourseViewPage.tsx` | Added `ChatbotLauncher` import + mount alongside existing `ChatWidget` |

## Test Count

17 tests, all passing. Covers:
- Open/close panel (2)
- Submit happy path (1)
- 2000-char cap validation (1)
- 503 error card + retry (2)
- Citation chip navigation (1)
- History load on open (1)
- History delete optimistic + rollback (2)
- Keyboard nav: Enter submits, Esc closes (2)
- grounded=false fallback card (1)
- Loading state: spinner + disabled input (1)
- ChatbotHistory component: items, empty state, loading (3)

## Mount Point

`frontend/src/pages/teacher/CourseViewPage.tsx` — route `/teacher/courses/:courseId`

## UI Primitives Reused

- `cn()` from `frontend/src/lib/utils.ts`
- `@heroicons/react` SVG icons (BookOpenIcon, XMarkIcon, SparklesIcon, etc.)
- Tailwind design tokens (primary-600, slate-*, sky-600)

## Deviations from Spec

1. **No Storybook stories** — Storybook is not installed in this project.
2. **Telemetry no-ops** — No `useAnalytics()` hook found; telemetry wired as `// TODO: wire telemetry` comments.
3. **Launcher offset** — Positioned at `right-[5.5rem]` (not `right-6`) to avoid overlapping the existing `ChatWidget` session-based AI tutor button which sits at `right-6`.
4. **Task spec not in vault** — Spec file not found at provided path; task implemented from coordinator prompt summary.
