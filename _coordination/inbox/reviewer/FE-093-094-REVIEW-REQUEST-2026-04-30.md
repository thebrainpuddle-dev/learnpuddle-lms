# Review Request — FE-093 + FE-094: MAICPlayerPage Test Suites (Teacher + Student)

**From:** frontend-engineer
**To:** lp-reviewer
**Date:** 2026-04-30
**Priority:** Normal — test-only, closes the last functional-page coverage gap

---

## Summary

Added Vitest + React Testing Library test suites for the two remaining untested
functional pages:

| Task | File | Tests | Key coverage |
|------|------|-------|--------------|
| FE-093 | `src/pages/teacher/MAICPlayerPage.test.tsx` | 48 | All 10 render states (Loading, Error/Not-Found, FAILED, ARCHIVED, GENERATING normal/progress/stall, READY-preparing, READY-full-player, imagesStalled, StallActions) |
| FE-094 | `src/pages/student/MAICPlayerPage.test.tsx` | 25 | All 6 render states (Loading, Error/Not-Found, Not-Available, READY-preparing, READY-full-player, imagesStalled) |

**Total: 73 tests across 2 new files — all passing**

---

## FE-093 — Teacher MAICPlayerPage (48 tests)

**File:** `src/pages/teacher/MAICPlayerPage.test.tsx`

Coverage by describe group:

| Group | Tests | What it verifies |
|-------|-------|-----------------|
| Loading state | 1 | Spinner visible when `isLoading=true` |
| Error / Not Found | 3 | "Classroom Not Found" heading, back button nav → `/teacher/ai-classroom` |
| FAILED status | 5 | "Generation Failed" heading, `error_message` rendered, default fallback, "Try Again" → `/teacher/ai-classroom/new`, back nav |
| ARCHIVED status | 2 | "Classroom Archived" heading, back nav |
| GENERATING (no content) | 6 | "Generating your classroom" heading, back button, progress bar from `config.sceneCount`, progress bar from `progress.expected_scenes`, safe-to-leave message |
| GENERATING stall detection | 3 | "Generation appears stalled" when `last_progress_at > 3min`, NOT stalled when recent, NOT stalled when absent |
| READY + storeReady=false | 3 | Spinner while `storeReady=false` (blocking `getStoredClassroom`), Stage absent, "Finishing up — fetching slide images…" text when `imagesPending=true` |
| READY + storeReady=true | 6 | Stage renders, classroom title in header, back nav, "Fetching images…" badge when `imagesPending=true`, badge absent when `imagesPending=false`, stall banner absent when not stalled |
| READY + imagesStalled | 5 | `data-testid="images-stall-banner"` shown when `images_pending=true` + `updated_at > 10min`, warning text, Stage renders alongside banner, Refresh button triggers refetch, NOT shown when `updated_at` is fresh |
| StallActions | 10 | "Use what's saved (N scenes)" visible (plural/singular/hidden when 0), "Back to library" present + navigates, `finalizePartialClassroom` called on click, "Finalizing…" label while in-flight, error message on `ok=false`, error on throw, fallback error string |
| isClassroomPlayable gate | 2 | Stage absent when `playable=false` and not stalled, Stage present when `playable=true` + `imagesPending=true` |

**Key discoveries:**
- `storeReady` is component-local `useState`; controlled by blocking/resolving `getStoredClassroom` mock
- `imagesStalled` triggered by `updated_at` set 11 min in the past (no fake timers needed)
- `StallActions` stall condition requires: `status=GENERATING` + `last_progress_at > 3min ago` + `savedSceneCount > 0`
- Mocking pattern matches `MAICPlayerPage.flipDetection.test.tsx` exactly (hoisted spies, store with `getState`/`setState` shims)

---

## FE-094 — Student MAICPlayerPage (25 tests)

**File:** `src/pages/student/MAICPlayerPage.test.tsx`

Coverage:

| Test | What it verifies |
|------|-----------------|
| Spinner while loading | `animate-spin` visible |
| Stage absent while loading | No `mock-stage` in DOM |
| "Classroom Not Found" on error | Heading present |
| Back button navigates on error | → `/student/ai-classroom` |
| "Classroom Not Found" when data=null | Direct null-data case |
| "Classroom Not Available" for GENERATING | Non-READY status guard |
| "Classroom Not Available" for DRAFT | Non-READY status guard |
| "Classroom Not Available" for FAILED | Non-READY status guard |
| Back nav from not-available | → `/student/ai-classroom` |
| Spinner while storeReady=false | Blocking `getStoredClassroom` |
| "Finishing up" text when `imagesPending=true` | Preparing spinner text |
| No "Finishing up" text when `imagesPending=false` | Conditional check |
| Stage renders when storeReady=true + playable | `mock-stage` present |
| Classroom title in h1 | After effects flush |
| Back button in player header | → `/student/ai-classroom` |
| Stage absent when `playable=false` + not stalled | Gate respected |
| Stall banner present (`data-testid`) | 11-min-old `updated_at` |
| Stall banner warning text | "Image fetching is taking unusually long" |
| Refresh button in stall banner | Button visible |
| Stage WITH stall banner | `imagesStalled` overrides gate |
| Stall banner absent when `images_pending=false` | Not triggered |
| Stall banner absent when recent `updated_at` | Not triggered |
| Refresh button triggers refetch + hides banner | onClick behavior |
| "Fetching slide images…" text when pending | Preparing panel text |
| No pending text when not pending | Conditional check |

---

## Mocking Strategy

Both files use the same pattern as `MAICPlayerPage.flipDetection.test.tsx`:

```typescript
// vi.hoisted — runs before vi.mock factories so spies are available
const { mockSetSlides, mockGetStoredClassroom, mockIsClassroomPlayable, ... } = vi.hoisted(() => ({
  mockSetSlides: vi.fn(),
  mockGetStoredClassroom: vi.fn(async () => null),
  mockIsClassroomPlayable: vi.fn(() => true),
  // ...
}));

// useMAICStageStore — selector-based stub with getState/setState shims
vi.mock('../../stores/maicStageStore', () => {
  const store = { setSlides: mockSetSlides, ... };
  const useMAICStageStore = (selector) => selector(store);
  useMAICStageStore.getState = () => store;
  useMAICStageStore.setState = (patch) => Object.assign(store, typeof patch === 'function' ? patch(store) : patch);
  return { useMAICStageStore };
});

// isClassroomPlayable — mocked directly so F3 gate logic is test-controlled
vi.mock('../../lib/maicReadinessGate', () => ({
  isClassroomPlayable: (...args) => mockIsClassroomPlayable(...args),
}));

// computeRefetchInterval — returns false (stops polling in tests)
vi.mock('../../lib/maicPollingPolicy', () => ({
  computeRefetchInterval: (...args) => mockComputeRefetchInterval(...args),
}));

// Stage — stubbed so tests don't need the full MAIC canvas
vi.mock('../../components/maic/Stage', () => ({
  Stage: () => <div data-testid="mock-stage" />,
}));
```

---

## Test Run

```
npx vitest run src/pages/teacher/MAICPlayerPage.test.tsx src/pages/student/MAICPlayerPage.test.tsx

Test Files  2 passed (2)
     Tests  73 passed (73)
  Duration  1.77s
```

---

## Coverage Milestone

This closes the last functional-page coverage gap. All pages across all roles
(admin, teacher, student, parent, superadmin, auth, onboarding) now have test suites.

— frontend-engineer
