// src/pages/teacher/__tests__/MAICPlayerPage.flipDetection.test.tsx
//
// SPRINT-2-BATCH-5-F10 — Render tests for the flip-detection useEffect in
// teacher MAICPlayerPage.tsx (lines ~:98-138).
//
// The useEffect fires when `images_pending` flips true → false and:
//   1. Calls `setSlides` with the new payload from the API.
//   2. Calls `saveClassroom` (IndexedDB write) with the new payload.
//
// This is the most consequential FE change in BATCH-3-F2 and had zero unit
// coverage before this file.
//
// Strategy: use QueryClient.setQueryData to drive the same mounted instance
// through a data change (true → false), so `prevImagesPendingRef` retains
// its value across the update (unlike rerender with a fresh QueryClient).

import React from 'react';
import { describe, test, expect, vi, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ─── Hoisted spies (vi.hoisted runs before vi.mock factories) ─────────────────

const { mockSetSlides, mockSetScenes, mockSetAgents, mockSetChatMessages,
        mockSetSceneSlideBounds, mockSetClassroomId, mockReset,
        mockGetStoredClassroom, mockSaveClassroom } = vi.hoisted(() => ({
  mockSetSlides: vi.fn(),
  mockSetScenes: vi.fn(),
  mockSetAgents: vi.fn(),
  mockSetChatMessages: vi.fn(),
  mockSetSceneSlideBounds: vi.fn(),
  mockSetClassroomId: vi.fn(),
  mockReset: vi.fn(),
  mockGetStoredClassroom: vi.fn(async () => null as null),
  mockSaveClassroom: vi.fn(async () => {}),
}));

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('../../../stores/maicStageStore', () => {
  const store = {
    setSlides: mockSetSlides,
    setScenes: mockSetScenes,
    setAgents: mockSetAgents,
    setChatMessages: mockSetChatMessages,
    setSceneSlideBounds: mockSetSceneSlideBounds,
    setClassroomId: mockSetClassroomId,
    reset: mockReset,
    classroomId: null as string | null,
    scenes: [] as unknown[],
  };
  const useMAICStageStore = (selector: (s: typeof store) => unknown) =>
    selector(store);
  // getState is called directly (not as a hook) inside the component.
  useMAICStageStore.getState = () => store;
  return { useMAICStageStore };
});

vi.mock('../../../lib/maicDb', () => ({
  getStoredClassroom: (...args: unknown[]) => mockGetStoredClassroom(...args),
  saveClassroom: (...args: unknown[]) => mockSaveClassroom(...args),
}));

vi.mock('../../../services/openmaicService', () => ({
  maicApi: {
    getClassroom: vi.fn(async () => ({ data: null })),
  },
}));

vi.mock('../../../components/maic/Stage', () => ({
  Stage: () => <div data-testid="mock-stage" />,
}));

vi.mock('../../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

// ─── Component under test ─────────────────────────────────────────────────────

import { MAICPlayerPage } from '../MAICPlayerPage';

// ─── Test helpers ─────────────────────────────────────────────────────────────

const TEST_CLASSROOM_ID = 'test-classroom-id';
const QUERY_KEY = ['maic-classroom', TEST_CLASSROOM_ID];

function makeSlides(tag: string) {
  return [
    { id: `slide-${tag}-1`, title: `Slide 1 (${tag})`, elements: [] },
    { id: `slide-${tag}-2`, title: `Slide 2 (${tag})`, elements: [] },
  ];
}

function makeScenes(tag: string) {
  return [{ id: `scene-${tag}-1`, title: `Scene (${tag})`, actions: [] }];
}

function makeClassroomPayload(
  imagesPending: boolean | undefined,
  tag: string,
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    id: TEST_CLASSROOM_ID,
    title: 'Test Classroom',
    status: 'READY',
    images_pending: imagesPending,
    updated_at: new Date().toISOString(),
    content: {
      slides: makeSlides(tag),
      scenes: makeScenes(tag),
      sceneSlideBounds: [],
    },
    config: { agents: [] },
    ...overrides,
  };
}

interface TestHarness {
  queryClient: QueryClient;
  unmount: () => void;
}

/** Mount MAICPlayerPage with the given initial classroom data pre-seeded into
 * the QueryClient cache so the component renders synchronously. */
function mountPage(initialData: Record<string, unknown> | null): TestHarness {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity } },
  });

  if (initialData !== null) {
    queryClient.setQueryData(QUERY_KEY, initialData);
  }

  const { unmount } = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter
        initialEntries={[`/teacher/ai-classroom/${TEST_CLASSROOM_ID}`]}
      >
        <Routes>
          <Route
            path="/teacher/ai-classroom/:id"
            element={<MAICPlayerPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

  return { queryClient, unmount };
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('MAICPlayerPage flip-detection useEffect (SPRINT-2-BATCH-5-F10)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Restore the getState mock after clearAllMocks resets fns but not factories.
    mockGetStoredClassroom.mockResolvedValue(null);
    mockSaveClassroom.mockResolvedValue(undefined);
  });

  test('calls setSlides with new payload when images_pending flips true → false', async () => {
    // Mount with images_pending=true — no flip yet.
    const { queryClient, unmount } = mountPage(
      makeClassroomPayload(true, 'before-flip'),
    );

    // Flush the initial effects (content-loading useEffect).
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    // Capture call count before the flip.
    const callsBefore = mockSetSlides.mock.calls.length;

    // Simulate the poll returning images_pending=false (the flip).
    await act(async () => {
      queryClient.setQueryData(
        QUERY_KEY,
        makeClassroomPayload(false, 'after-flip'),
      );
      await new Promise((r) => setTimeout(r, 0));
    });

    // setSlides should have been called at least once more after the flip.
    expect(mockSetSlides.mock.calls.length).toBeGreaterThan(callsBefore);

    // The flip-triggered call should contain after-flip slide ids.
    const flipCalls = mockSetSlides.mock.calls.filter((args) =>
      (args[0] as Array<{ id: string }>).some((s) =>
        typeof s.id === 'string' && s.id.includes('after-flip'),
      ),
    );
    expect(flipCalls.length).toBeGreaterThanOrEqual(1);

    unmount();
  });

  test('calls saveClassroom (IndexedDB write) when images_pending flips true → false', async () => {
    const { queryClient, unmount } = mountPage(
      makeClassroomPayload(true, 'before-flip'),
    );

    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    // Clear any saves from the initial content-loading effect so we can
    // confirm the flip path specifically.
    mockSaveClassroom.mockClear();

    // Flip images_pending to false.
    await act(async () => {
      queryClient.setQueryData(
        QUERY_KEY,
        makeClassroomPayload(false, 'after-flip'),
      );
      await new Promise((r) => setTimeout(r, 0));
    });

    // saveClassroom must have been called by the flip effect.
    expect(mockSaveClassroom).toHaveBeenCalled();

    // The call payload should carry the new slides.
    const callArg = mockSaveClassroom.mock.calls[0]?.[0] as
      | { id: string; title: string; slides: Array<{ id: string }> }
      | undefined;
    expect(callArg).toBeDefined();
    expect(callArg?.id).toBe(TEST_CLASSROOM_ID);
    expect(callArg?.title).toBe('Test Classroom');
    // After-flip slides should be in the save payload.
    expect(
      callArg?.slides.some((s) => s.id?.includes('after-flip')),
    ).toBe(true);

    unmount();
  });

  test('does NOT trigger flip effect when images_pending stays false (no flip)', async () => {
    // images_pending was never true — no flip should occur.
    const { queryClient, unmount } = mountPage(
      makeClassroomPayload(false, 'no-flip-A'),
    );

    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    // Clear saves from initial content-loading effect.
    mockSaveClassroom.mockClear();

    // Update data — still false, no flip.
    await act(async () => {
      queryClient.setQueryData(
        QUERY_KEY,
        makeClassroomPayload(false, 'no-flip-B'),
      );
      await new Promise((r) => setTimeout(r, 0));
    });

    // No saveClassroom call with 'no-flip-B' slides — the flip-detection
    // effect only fires when prev===true AND current===false.
    const flipBSaves = mockSaveClassroom.mock.calls.filter((args) =>
      (args[0]?.slides as Array<{ id: string }> | undefined)?.some((s) =>
        typeof s.id === 'string' && s.id.includes('no-flip-B'),
      ),
    );
    expect(flipBSaves).toHaveLength(0);

    unmount();
  });

  test('does NOT fire flip effect on initial mount with images_pending=true (prev is undefined)', async () => {
    // On the first render prevImagesPendingRef is undefined.
    // The guard `prev === true && current === false` cannot fire because
    // prev=undefined, not true.
    const { unmount } = mountPage(
      makeClassroomPayload(true, 'initial'),
    );

    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });

    // No flip happened (images_pending never became false), so setSlides
    // should not have been called with slides that carry an 'after' tag.
    // (The content-loading effect may call setSlides with 'initial' slides,
    // but that is separate from the flip path.)
    const afterFlipCalls = mockSetSlides.mock.calls.filter((args) =>
      (args[0] as Array<{ id: string }>).some(
        (s) => typeof s.id === 'string' && s.id.includes('-after-'),
      ),
    );
    expect(afterFlipCalls).toHaveLength(0);

    unmount();
  });
});
