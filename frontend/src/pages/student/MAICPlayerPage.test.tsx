// src/pages/student/MAICPlayerPage.test.tsx
//
// Vitest + React Testing Library suite for StudentMAICPlayerPage.
//
// Covers all render states:
//   1. LOADING  — spinner visible, Stage not mounted
//   2. ERROR / NOT-FOUND — "Classroom Not Found" heading + back button nav
//   3. STATUS !== 'READY' — "Classroom Not Available" heading + back button nav
//   4. READY + storeReady=false — preparing spinner (+ images-pending text)
//   5. READY + storeReady=true + playable=true — Stage + h1 title + back button
//   6. READY + imagesStalled=true — stall banner shown with Refresh button
//
// Mocking strategy:
//   - maicStudentApi.getClassroom is driven per-test via mockResolvedValue /
//     mockReturnValue so we can control isLoading / error / data separately.
//   - useMAICStageStore is stubbed with vi.hoisted (same pattern as the
//     teacher flip-detection test) so getState() / setState() / selector calls
//     are all safe no-ops.
//   - useMaicMediaGenerationStore is stubbed to expose hydrateFromMap,
//     clearStage, and tasks (empty map → falls to legacy gate path).
//   - useMaicClassroomChannel is a no-op.
//   - getStoredClassroom resolves to null immediately (fast path through
//     loadContent so storeReady flips true after one micro-task tick).
//   - saveClassroom is a no-op.
//   - computeRefetchInterval always returns false (no polling in tests).
//   - isClassroomPlayable is mocked and its return value is overridden
//     per-test group.
//   - Stage is stubbed with <div data-testid="mock-stage" />.
//   - usePageTitle is a no-op vi.fn().
//   - useNavigate is hoisted so navigation assertions are plain expect() calls.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { act } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// ─── Hoisted mocks (vi.hoisted runs before vi.mock factories) ─────────────────

const mockedUseNavigate = vi.fn();

const {
  mockSetSlides,
  mockSetScenes,
  mockSetAgents,
  mockSetChatMessages,
  mockSetSceneSlideBounds,
  mockSetClassroomId,
  mockReset,
  mockGetStoredClassroom,
  mockSaveClassroom,
  mockHydrateFromMap,
  mockClearStage,
  mockIsClassroomPlayable,
  mockComputeRefetchInterval,
} = vi.hoisted(() => ({
  mockSetSlides: vi.fn(),
  mockSetScenes: vi.fn(),
  mockSetAgents: vi.fn(),
  mockSetChatMessages: vi.fn(),
  mockSetSceneSlideBounds: vi.fn(),
  mockSetClassroomId: vi.fn(),
  mockReset: vi.fn(),
  mockGetStoredClassroom: vi.fn(async () => null as null),
  mockSaveClassroom: vi.fn(async () => {}),
  mockHydrateFromMap: vi.fn(),
  mockClearStage: vi.fn(),
  // Default: playable (renders Stage when storeReady=true)
  mockIsClassroomPlayable: vi.fn(() => true),
  // Default: no polling in tests
  mockComputeRefetchInterval: vi.fn(() => false as false),
}));

// ─── react-router-dom: hoist navigate ────────────────────────────────────────

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockedUseNavigate };
});

// ─── useMAICStageStore ────────────────────────────────────────────────────────

vi.mock('../../stores/maicStageStore', () => {
  const store = {
    setSlides: mockSetSlides,
    setScenes: mockSetScenes,
    setAgents: mockSetAgents,
    setChatMessages: mockSetChatMessages,
    setSceneSlideBounds: mockSetSceneSlideBounds,
    setClassroomId: mockSetClassroomId,
    reset: mockReset,
    classroomId: null as string | null,
    currentSceneIndex: 0,
    currentSlideIndex: 0,
    scenes: [] as unknown[],
  };

  const useMAICStageStore = (selector: (s: typeof store) => unknown) =>
    selector(store);

  useMAICStageStore.getState = () => store;

  useMAICStageStore.setState = (
    patch: Partial<typeof store> | ((s: typeof store) => Partial<typeof store>),
  ) => {
    const next = typeof patch === 'function' ? patch(store) : patch;
    Object.assign(store, next);
  };

  return { useMAICStageStore };
});

// ─── useMaicMediaGenerationStore ─────────────────────────────────────────────

vi.mock('../../stores/maicMediaGenerationStore', () => {
  // Selector-based hook: map selector function to the right mock function
  const useMaicMediaGenerationStore = (selector: (s: {
    hydrateFromMap: typeof mockHydrateFromMap;
    clearStage: typeof mockClearStage;
    tasks: Record<string, unknown>;
  }) => unknown) =>
    selector({
      hydrateFromMap: mockHydrateFromMap,
      clearStage: mockClearStage,
      tasks: {}, // empty → legacy gate fallback → drives playable via isClassroomPlayable mock
    });

  return { useMaicMediaGenerationStore };
});

// ─── useMaicClassroomChannel — no-op ─────────────────────────────────────────

vi.mock('../../hooks/useMaicClassroomChannel', () => ({
  useMaicClassroomChannel: vi.fn(),
}));

// ─── maicDb ──────────────────────────────────────────────────────────────────

vi.mock('../../lib/maicDb', () => ({
  getStoredClassroom: (...args: unknown[]) => mockGetStoredClassroom(...args),
  saveClassroom: (...args: unknown[]) => mockSaveClassroom(...args),
}));

// ─── maicPollingPolicy ────────────────────────────────────────────────────────

vi.mock('../../lib/maicPollingPolicy', () => ({
  computeRefetchInterval: (...args: unknown[]) =>
    mockComputeRefetchInterval(...args),
}));

// ─── maicReadinessGate ────────────────────────────────────────────────────────

vi.mock('../../lib/maicReadinessGate', () => ({
  isClassroomPlayable: (...args: unknown[]) =>
    mockIsClassroomPlayable(...args),
}));

// ─── Stage stub ───────────────────────────────────────────────────────────────

vi.mock('../../components/maic/Stage', () => ({
  Stage: () => <div data-testid="mock-stage" />,
}));

// ─── usePageTitle — no-op ─────────────────────────────────────────────────────

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ─── maicStudentApi ───────────────────────────────────────────────────────────

vi.mock('../../services/openmaicService', () => ({
  maicStudentApi: {
    getClassroom: vi.fn(),
    listClassrooms: vi.fn(),
    myClassrooms: vi.fn(),
  },
}));

// ─── Import handles after vi.mock ─────────────────────────────────────────────

import { maicStudentApi } from '../../services/openmaicService';
import { StudentMAICPlayerPage } from './MAICPlayerPage';

const mockedGetClassroom = maicStudentApi.getClassroom as ReturnType<typeof vi.fn>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const makeClassroom = (overrides: Record<string, unknown> = {}) => ({
  id: 'cls-test',
  title: 'Test AI Classroom',
  status: 'READY',
  images_pending: false,
  updated_at: new Date().toISOString(),
  content_image_tasks: {},
  content: { slides: [], scenes: [], sceneSlideBounds: [] },
  config: { agents: [] },
  ...overrides,
});

// ─── QueryClient factory ──────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
        refetchOnWindowFocus: false,
      },
    },
  });

// ─── Render helper ────────────────────────────────────────────────────────────

function renderPage(queryClient = makeQueryClient()) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }} initialEntries={['/student/ai-classroom/cls-test']}>
        <Routes>
          <Route
            path="/student/ai-classroom/:id"
            element={<StudentMAICPlayerPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/**
 * Render with a pre-seeded QueryClient and flush async effects so that
 * `storeReady` becomes `true`.  Returns the queryClient for further
 * manipulation in tests that need it.
 */
async function renderPageWithStoreReady(
  classroomOverrides: Record<string, unknown> = {},
) {
  const qc = makeQueryClient();
  const classroom = makeClassroom(classroomOverrides);
  qc.setQueryData(['student-maic-classroom', 'cls-test'], classroom);

  // Also make getClassroom resolve fast (it may still be called by React
  // Query even though cache is seeded, depending on staleTime).
  mockedGetClassroom.mockResolvedValue({ data: classroom });

  renderPage(qc);

  // Flush the loadContent() async effect so storeReady flips to true.
  await act(async () => {
    await new Promise((r) => setTimeout(r, 0));
  });

  return qc;
}

// ─── Suite ────────────────────────────────────────────────────────────────────

describe('StudentMAICPlayerPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // Restore key mock defaults after resetAllMocks clears implementations.
    mockGetStoredClassroom.mockResolvedValue(null);
    mockSaveClassroom.mockResolvedValue(undefined);
    mockIsClassroomPlayable.mockReturnValue(true);
    mockComputeRefetchInterval.mockReturnValue(false);
  });

  // ── 1. Loading state — spinner visible ────────────────────────────────────

  it('shows an animate-spin spinner while the classroom is loading', () => {
    // Keep the query in-flight forever so isLoading stays true.
    mockedGetClassroom.mockReturnValue(new Promise(() => {}));

    renderPage();

    const spinner = document.querySelector('.animate-spin');
    expect(spinner).not.toBeNull();
  });

  // ── 2. Loading state — Stage not mounted ─────────────────────────────────

  it('does not render the Stage while loading', () => {
    mockedGetClassroom.mockReturnValue(new Promise(() => {}));

    renderPage();

    expect(screen.queryByTestId('mock-stage')).not.toBeInTheDocument();
  });

  // ── 3. Error state — "Classroom Not Found" heading ───────────────────────

  it('shows "Classroom Not Found" heading when the query errors', async () => {
    mockedGetClassroom.mockRejectedValue(new Error('network error'));

    renderPage();

    expect(
      await screen.findByRole('heading', { level: 3, name: /classroom not found/i }),
    ).toBeInTheDocument();
  });

  // ── 4. Error state — back button present ─────────────────────────────────

  it('shows a back button when the query errors', async () => {
    mockedGetClassroom.mockRejectedValue(new Error('network error'));

    renderPage();

    const backBtn = await screen.findByRole('button', { name: /back to classrooms/i });
    expect(backBtn).toBeInTheDocument();
  });

  // ── 5. Error state — back button navigates correctly ─────────────────────

  it('back button from error state navigates to /student/ai-classroom', async () => {
    const user = userEvent.setup();
    mockedGetClassroom.mockRejectedValue(new Error('network error'));

    renderPage();

    const backBtn = await screen.findByRole('button', { name: /back to classrooms/i });
    await user.click(backBtn);

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/ai-classroom');
  });

  // ── 6. Not-found — classroom is null after query resolves ─────────────────

  it('shows "Classroom Not Found" when the API returns null data', async () => {
    mockedGetClassroom.mockResolvedValue({ data: null });

    renderPage();

    expect(
      await screen.findByRole('heading', { level: 3, name: /classroom not found/i }),
    ).toBeInTheDocument();
  });

  // ── 7. Status GENERATING — "Classroom Not Available" heading ─────────────

  it('shows "Classroom Not Available" heading when status is GENERATING', async () => {
    mockedGetClassroom.mockResolvedValue({
      data: makeClassroom({ status: 'GENERATING' }),
    });

    renderPage();

    expect(
      await screen.findByRole('heading', { level: 3, name: /classroom not available/i }),
    ).toBeInTheDocument();
  });

  // ── 8. Status DRAFT — "Classroom Not Available" heading ──────────────────

  it('shows "Classroom Not Available" heading when status is DRAFT', async () => {
    mockedGetClassroom.mockResolvedValue({
      data: makeClassroom({ status: 'DRAFT' }),
    });

    renderPage();

    expect(
      await screen.findByRole('heading', { level: 3, name: /classroom not available/i }),
    ).toBeInTheDocument();
  });

  // ── 9. Status FAILED — "Classroom Not Available" heading ─────────────────

  it('shows "Classroom Not Available" heading when status is FAILED', async () => {
    mockedGetClassroom.mockResolvedValue({
      data: makeClassroom({ status: 'FAILED' }),
    });

    renderPage();

    expect(
      await screen.findByRole('heading', { level: 3, name: /classroom not available/i }),
    ).toBeInTheDocument();
  });

  // ── 10. Not-available — back button navigates correctly ──────────────────

  it('back button from not-available state navigates to /student/ai-classroom', async () => {
    const user = userEvent.setup();
    mockedGetClassroom.mockResolvedValue({
      data: makeClassroom({ status: 'GENERATING' }),
    });

    renderPage();

    const backBtn = await screen.findByRole('button', { name: /back to classrooms/i });
    await user.click(backBtn);

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/ai-classroom');
  });

  // ── 11. READY + storeReady=false — preparing spinner ─────────────────────

  it('shows a spinner while storeReady is false (before effects resolve)', async () => {
    // Seed the cache so classroom data is available immediately (READY),
    // but do NOT await the act flush — storeReady is still false.
    const qc = makeQueryClient();
    qc.setQueryData(
      ['student-maic-classroom', 'cls-test'],
      makeClassroom({ images_pending: false }),
    );
    mockedGetClassroom.mockResolvedValue({
      data: makeClassroom({ images_pending: false }),
    });
    // Block getStoredClassroom so loadContent never completes.
    mockGetStoredClassroom.mockReturnValue(new Promise(() => {}));

    renderPage(qc);

    // storeReady is still false — we should see the preparing spinner.
    const spinner = document.querySelector('.animate-spin');
    expect(spinner).not.toBeNull();
  });

  // ── 12. READY + imagesPending=true + storeReady=false — "Fetching" text ──

  it('shows "Finishing up — fetching slide images…" when imagesPending=true and preparing', async () => {
    const qc = makeQueryClient();
    qc.setQueryData(
      ['student-maic-classroom', 'cls-test'],
      makeClassroom({ images_pending: true }),
    );
    mockedGetClassroom.mockResolvedValue({
      data: makeClassroom({ images_pending: true }),
    });
    // Block getStoredClassroom so storeReady stays false.
    mockGetStoredClassroom.mockReturnValue(new Promise(() => {}));
    // isClassroomPlayable returns false (images still pending).
    mockIsClassroomPlayable.mockReturnValue(false);

    renderPage(qc);

    expect(
      await screen.findByText(/finishing up — fetching slide images/i),
    ).toBeInTheDocument();
  });

  // ── 13. READY + storeReady=true + playable=true — Stage renders ──────────

  it('renders the Stage when storeReady=true and classroom is playable', async () => {
    await renderPageWithStoreReady();

    expect(screen.getByTestId('mock-stage')).toBeInTheDocument();
  });

  // ── 14. READY + storeReady=true — classroom title in h1 ──────────────────

  it('shows the classroom title in an h1 element after store is ready', async () => {
    await renderPageWithStoreReady();

    expect(
      screen.getByRole('heading', { level: 1, name: /test ai classroom/i }),
    ).toBeInTheDocument();
  });

  // ── 15. Player header — back button navigates correctly ──────────────────

  it('back button in player header navigates to /student/ai-classroom', async () => {
    const user = userEvent.setup();
    await renderPageWithStoreReady();

    // The player header back button has title "Back to Classrooms".
    const backBtn = screen.getByRole('button', { name: /back to classrooms/i });
    await user.click(backBtn);

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/ai-classroom');
  });

  // ── 16. Stage not shown when not playable and not stalled ────────────────

  it('does not render the Stage when playable=false and imagesStalled=false', async () => {
    const qc = makeQueryClient();
    // images_pending=true, recent updated_at → not stalled
    qc.setQueryData(
      ['student-maic-classroom', 'cls-test'],
      makeClassroom({ images_pending: true }),
    );
    mockedGetClassroom.mockResolvedValue({
      data: makeClassroom({ images_pending: true }),
    });
    mockIsClassroomPlayable.mockReturnValue(false);
    // Block loadContent so storeReady never flips — also ensures spinner path.
    mockGetStoredClassroom.mockReturnValue(new Promise(() => {}));

    renderPage(qc);

    expect(screen.queryByTestId('mock-stage')).not.toBeInTheDocument();
  });

  // ── 17. imagesStalled banner — data-testid present ───────────────────────

  it('shows data-testid="images-stall-banner" when images are stalled', async () => {
    // images_pending=true AND updated_at > 10 minutes ago → stalled.
    const stalledUpdatedAt = new Date(
      Date.now() - 11 * 60 * 1000,
    ).toISOString();

    await renderPageWithStoreReady({
      images_pending: true,
      updated_at: stalledUpdatedAt,
    });

    expect(screen.getByTestId('images-stall-banner')).toBeInTheDocument();
  });

  // ── 18. imagesStalled banner — warning text ───────────────────────────────

  it('stall banner contains "Image fetching is taking unusually long" text', async () => {
    const stalledUpdatedAt = new Date(
      Date.now() - 11 * 60 * 1000,
    ).toISOString();

    await renderPageWithStoreReady({
      images_pending: true,
      updated_at: stalledUpdatedAt,
    });

    expect(
      screen.getByText(/image fetching is taking unusually long/i),
    ).toBeInTheDocument();
  });

  // ── 19. imagesStalled banner — Refresh button present ────────────────────

  it('stall banner contains a Refresh button', async () => {
    const stalledUpdatedAt = new Date(
      Date.now() - 11 * 60 * 1000,
    ).toISOString();

    await renderPageWithStoreReady({
      images_pending: true,
      updated_at: stalledUpdatedAt,
    });

    expect(
      screen.getByRole('button', { name: /refresh/i }),
    ).toBeInTheDocument();
  });

  // ── 20. imagesStalled — Stage still renders (stall bypasses playable gate)

  it('renders the Stage even when images are stalled (stall overrides playable gate)', async () => {
    const stalledUpdatedAt = new Date(
      Date.now() - 11 * 60 * 1000,
    ).toISOString();

    // isClassroomPlayable returns false, but imagesStalled overrides the guard.
    mockIsClassroomPlayable.mockReturnValue(false);

    await renderPageWithStoreReady({
      images_pending: true,
      updated_at: stalledUpdatedAt,
    });

    expect(screen.getByTestId('mock-stage')).toBeInTheDocument();
  });

  // ── 21. No stall banner when images_pending=false ────────────────────────

  it('does not show the stall banner when images_pending=false', async () => {
    await renderPageWithStoreReady({ images_pending: false });

    expect(screen.queryByTestId('images-stall-banner')).not.toBeInTheDocument();
  });

  // ── 22. No stall banner when updated_at is recent (< 10 min) ─────────────

  it('does not show the stall banner when images_pending=true but updated_at is recent', async () => {
    // 5 minutes ago — below the 10-minute threshold.
    const recentUpdatedAt = new Date(
      Date.now() - 5 * 60 * 1000,
    ).toISOString();

    mockIsClassroomPlayable.mockReturnValue(false);
    // Block loadContent so storeReady stays false → preparing spinner path.
    mockGetStoredClassroom.mockReturnValue(new Promise(() => {}));

    const qc = makeQueryClient();
    qc.setQueryData(
      ['student-maic-classroom', 'cls-test'],
      makeClassroom({ images_pending: true, updated_at: recentUpdatedAt }),
    );
    mockedGetClassroom.mockResolvedValue({
      data: makeClassroom({ images_pending: true, updated_at: recentUpdatedAt }),
    });

    renderPage(qc);

    await waitFor(() => {
      expect(screen.queryByTestId('images-stall-banner')).not.toBeInTheDocument();
    });
  });

  // ── 23. Stall banner Refresh button clears stall state ───────────────────

  it('Refresh button in stall banner triggers a refetch and hides the banner', async () => {
    const user = userEvent.setup();
    const stalledUpdatedAt = new Date(
      Date.now() - 11 * 60 * 1000,
    ).toISOString();

    const qc = await renderPageWithStoreReady({
      images_pending: true,
      updated_at: stalledUpdatedAt,
    });

    // Update the cache to a fresh, non-stalled state so the banner disappears.
    const freshClassroom = makeClassroom({ images_pending: false });
    mockedGetClassroom.mockResolvedValue({ data: freshClassroom });

    const refreshBtn = screen.getByRole('button', { name: /refresh/i });
    await user.click(refreshBtn);

    // After clicking Refresh, imagesStalled is reset to false → banner gone.
    await waitFor(() => {
      expect(
        screen.queryByTestId('images-stall-banner'),
      ).not.toBeInTheDocument();
    });
  });

  // ── 24. "Fetching slide images…" text when imagesPending=true + spinning ──

  it('shows "Finishing up — fetching slide images…" text when imagesPending=true and still loading store', async () => {
    const qc = makeQueryClient();
    qc.setQueryData(
      ['student-maic-classroom', 'cls-test'],
      makeClassroom({ images_pending: true }),
    );
    mockedGetClassroom.mockResolvedValue({
      data: makeClassroom({ images_pending: true }),
    });
    // Block getStoredClassroom so storeReady never flips.
    mockGetStoredClassroom.mockReturnValue(new Promise(() => {}));
    mockIsClassroomPlayable.mockReturnValue(false);

    renderPage(qc);

    expect(
      await screen.findByText(/finishing up — fetching slide images/i),
    ).toBeInTheDocument();
  });

  // ── 25. No "Fetching" text when imagesPending=false ───────────────────────

  it('does not show the images-pending text when imagesPending=false', async () => {
    const qc = makeQueryClient();
    qc.setQueryData(
      ['student-maic-classroom', 'cls-test'],
      makeClassroom({ images_pending: false }),
    );
    mockedGetClassroom.mockResolvedValue({
      data: makeClassroom({ images_pending: false }),
    });
    // Block getStoredClassroom so we stay in the preparing-spinner state.
    mockGetStoredClassroom.mockReturnValue(new Promise(() => {}));

    renderPage(qc);

    await waitFor(() => {
      expect(
        screen.queryByText(/finishing up — fetching slide images/i),
      ).not.toBeInTheDocument();
    });
  });
});
