// src/pages/student/CourseViewPage.test.tsx
//
// Comprehensive Vitest + React Testing Library test suite for the student
// CourseViewPage component.
//
// Covers: loading state, back-button navigation, course title/progress text,
// module sidebar rendering, module expand/collapse, content item selection,
// locked content, completed content icon, content-type labels, ContentPlayer
// rendering, "Select an item" placeholder, auto-select on load, ChatWidget,
// sidebar toggle/close, handleComplete (success + error), completion % and
// module lock_reason display.
//
// Mocking strategy:
//   - studentService methods are vi.fn()s reset in beforeEach.
//   - ContentPlayer is a minimal stub that exposes onComplete as a button.
//   - ChatWidget and CompletionRing are inert stubs.
//   - usePageTitle is stubbed to avoid document.title side-effects.
//   - react-router-dom's useNavigate and useParams are patched.
//   - ToastProvider is rendered as a real wrapper so useToast works.

import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ToastProvider } from '../../components/common';
import { CourseViewPage } from './CourseViewPage';
import { studentService } from '../../services/studentService';

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../services/studentService', () => ({
  studentService: {
    getStudentCourseDetail: vi.fn(),
    completeContent: vi.fn(),
    startContentProgress: vi.fn(),
    updateContentProgress: vi.fn(),
  },
}));

vi.mock('../../components/teacher', () => ({
  ContentPlayer: ({ onComplete, content }: any) => (
    <div data-testid="content-player" data-content-id={content?.id}>
      <button onClick={onComplete}>Mark Complete</button>
    </div>
  ),
}));

vi.mock('../../components/ai/ChatWidget', () => ({
  ChatWidget: () => <div data-testid="chat-widget" />,
}));

vi.mock('../../components/teacher/dashboard/CompletionRing', () => ({
  CompletionRing: ({ value }: any) => (
    <div data-testid="completion-ring" data-value={value} />
  ),
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

const mockedUseNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockedUseNavigate,
    useParams: () => ({ courseId: 'course-1' }),
  };
});

// ── Typed mock helpers ────────────────────────────────────────────────────────

const mockedGetCourseDetail = studentService.getStudentCourseDetail as ReturnType<typeof vi.fn>;
const mockedCompleteContent = studentService.completeContent as ReturnType<typeof vi.fn>;
const mockedStartContentProgress = studentService.startContentProgress as ReturnType<typeof vi.fn>;

// ── Fixtures ──────────────────────────────────────────────────────────────────

const MOCK_CONTENT_VIDEO = {
  id: 'content-1',
  title: 'Intro to Biology',
  content_type: 'VIDEO' as const,
  order: 1,
  is_locked: false,
  is_completed: false,
  is_mandatory: true,
  is_active: true,
  status: 'NOT_STARTED',
  file_url: undefined,
  hls_url: 'https://cdn.example.com/video.m3u8',
  thumbnail_url: undefined,
  text_content: undefined,
  duration: 300,
  has_transcript: false,
  transcript_vtt_url: undefined,
  video_progress_seconds: 0,
  file_size: null,
  progress_percentage: 0,
  lock_reason: '',
};

const MOCK_CONTENT_DOC = {
  id: 'content-2',
  title: 'Reading: Cell Structure',
  content_type: 'DOCUMENT' as const,
  order: 2,
  is_locked: false,
  is_completed: true,
  is_mandatory: false,
  is_active: true,
  status: 'COMPLETED',
  file_url: 'https://cdn.example.com/doc.pdf',
  hls_url: undefined,
  thumbnail_url: undefined,
  text_content: undefined,
  duration: null,
  has_transcript: false,
  transcript_vtt_url: undefined,
  video_progress_seconds: 0,
  file_size: null,
  progress_percentage: 100,
  lock_reason: '',
};

const MOCK_CONTENT_LOCKED = {
  id: 'content-3',
  title: 'Advanced Genetics',
  content_type: 'DOCUMENT' as const,
  order: 3,
  is_locked: true,
  is_completed: false,
  is_mandatory: false,
  is_active: true,
  status: 'LOCKED',
  file_url: undefined,
  hls_url: undefined,
  thumbnail_url: undefined,
  text_content: undefined,
  duration: null,
  has_transcript: false,
  transcript_vtt_url: undefined,
  video_progress_seconds: 0,
  file_size: null,
  progress_percentage: 0,
  lock_reason: 'Complete previous content first',
};

const MOCK_COURSE = {
  id: 'course-1',
  title: 'Biology 101',
  slug: 'biology-101',
  description: 'An introduction to biology.',
  thumbnail: null,
  is_mandatory: false,
  is_published: true,
  is_active: true,
  deadline: null,
  estimated_hours: '5',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  progress: {
    completed_content_count: 1,
    total_content_count: 3,
    percentage: 33,
  },
  modules: [
    {
      id: 'module-1',
      title: 'Module 1: Foundations',
      description: '',
      order: 1,
      is_active: true,
      is_locked: false,
      is_completed: false,
      lock_reason: '',
      completion_percentage: 33,
      completed_content_count: 1,
      total_content_count: 3,
      contents: [MOCK_CONTENT_VIDEO, MOCK_CONTENT_DOC, MOCK_CONTENT_LOCKED],
    },
  ],
};

// Course with an empty module — auto-select yields null → "Select an item to begin"
const MOCK_COURSE_EMPTY_MODULE = {
  ...MOCK_COURSE,
  title: 'Empty Course',
  progress: { completed_content_count: 0, total_content_count: 0, percentage: 0 },
  modules: [
    {
      id: 'module-empty',
      title: 'Empty Module',
      description: '',
      order: 1,
      is_active: true,
      is_locked: false,
      is_completed: false,
      lock_reason: '',
      completion_percentage: 0,
      completed_content_count: 0,
      total_content_count: 0,
      contents: [],
    },
  ],
};

// Course with a locked module (used to test lock_reason display)
const MOCK_COURSE_LOCKED_MODULE = {
  ...MOCK_COURSE,
  title: 'Locked Course',
  progress: { completed_content_count: 0, total_content_count: 1, percentage: 0 },
  modules: [
    {
      id: 'module-locked',
      title: 'Locked Module',
      description: '',
      order: 1,
      is_active: true,
      is_locked: true,
      is_completed: false,
      lock_reason: 'Finish the prerequisite first',
      completion_percentage: 0,
      completed_content_count: 0,
      total_content_count: 1,
      contents: [
        {
          ...MOCK_CONTENT_LOCKED,
          id: 'content-locked-only',
          title: 'Locked Content',
        },
      ],
    },
  ],
};

// Course with two modules: first module auto-selected, second module unused at load
const MOCK_COURSE_TWO_MODULES = {
  ...MOCK_COURSE,
  title: 'Biology 101',
  modules: [
    {
      id: 'module-1',
      title: 'Module 1: Foundations',
      description: '',
      order: 1,
      is_active: true,
      is_locked: false,
      is_completed: false,
      lock_reason: '',
      completion_percentage: 33,
      completed_content_count: 1,
      total_content_count: 3,
      contents: [MOCK_CONTENT_VIDEO, MOCK_CONTENT_DOC, MOCK_CONTENT_LOCKED],
    },
    {
      id: 'module-2',
      title: 'Module 2: Advanced Topics',
      description: '',
      order: 2,
      is_active: true,
      is_locked: false,
      is_completed: false,
      lock_reason: '',
      completion_percentage: 0,
      completed_content_count: 0,
      total_content_count: 1,
      contents: [
        {
          ...MOCK_CONTENT_VIDEO,
          id: 'content-4',
          title: 'Genetics Overview',
          order: 1,
        },
      ],
    },
  ],
};

// ── Render helper ─────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });

const renderPage = () =>
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ToastProvider>
          <CourseViewPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('CourseViewPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedUseNavigate.mockReset();
    // Default: course loads successfully.
    mockedGetCourseDetail.mockResolvedValue(MOCK_COURSE);
    mockedCompleteContent.mockResolvedValue({});
    mockedStartContentProgress.mockResolvedValue({});
  });

  // ── 1. Loading state ──────────────────────────────────────────────────────

  describe('loading state', () => {
    it('shows spinner with border-indigo-500 class while query is pending', () => {
      mockedGetCourseDetail.mockImplementation(() => new Promise(() => {}));
      renderPage();

      const spinner = document.querySelector('.border-indigo-500');
      expect(spinner).toBeInTheDocument();
    });

    it('does not render the course title while loading', () => {
      mockedGetCourseDetail.mockImplementation(() => new Promise(() => {}));
      renderPage();

      expect(screen.queryByText('Biology 101')).not.toBeInTheDocument();
    });
  });

  // ── 2. Back button ────────────────────────────────────────────────────────

  describe('back button', () => {
    it('navigates to /student/courses when back button is clicked', async () => {
      renderPage();
      // Wait for the h1 specifically to avoid the ambiguity with the sidebar h2.
      await screen.findByRole('heading', { level: 1, name: /biology 101/i });

      const backBtn = screen.getByRole('button', { name: /back to my courses/i });
      await userEvent.click(backBtn);

      expect(mockedUseNavigate).toHaveBeenCalledWith('/student/courses');
    });
  });

  // ── 3. Course title ───────────────────────────────────────────────────────

  describe('course title', () => {
    it('renders the course title in the top bar', async () => {
      renderPage();
      await waitFor(() => {
        // Title appears in both top-bar h1 and sidebar header; getByRole finds h1.
        expect(screen.getByRole('heading', { level: 1, name: /biology 101/i })).toBeInTheDocument();
      });
    });
  });

  // ── 4. Progress text ──────────────────────────────────────────────────────

  describe('progress text', () => {
    it('shows "{completed}/{total} completed" text', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getByText(/1\/3 completed/i)).toBeInTheDocument();
      });
    });

    it('shows "{percentage}% complete" text', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getByText(/33% complete/i)).toBeInTheDocument();
      });
    });
  });

  // ── 5. Module in sidebar ──────────────────────────────────────────────────

  describe('module in sidebar', () => {
    it('renders the module title in the sidebar when course loads', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getByText('Module 1: Foundations')).toBeInTheDocument();
      });
    });
  });

  // ── 6 & 7. Module expand / collapse ──────────────────────────────────────

  describe('module expand and collapse', () => {
    it('clicking module button expands it — shows content items', async () => {
      // Use two-module course: module-1 is auto-expanded by auto-select logic.
      // module-2 starts collapsed; clicking it should reveal its content.
      mockedGetCourseDetail.mockResolvedValue(MOCK_COURSE_TWO_MODULES);
      renderPage();
      await screen.findByText('Module 2: Advanced Topics');

      // module-2 content is not visible before expanding.
      expect(screen.queryByText('Genetics Overview')).not.toBeInTheDocument();

      const module2Btn = screen.getByText('Module 2: Advanced Topics').closest('button')!;
      await userEvent.click(module2Btn);

      await waitFor(() => {
        expect(screen.getByText('Genetics Overview')).toBeInTheDocument();
      });
    });

    it('clicking the module button again collapses it — hides content items', async () => {
      renderPage();
      // Wait for auto-select which expands module-1.
      await screen.findByText('Intro to Biology');

      const moduleBtn = screen.getByText('Module 1: Foundations').closest('button')!;

      // First click: collapse (it was auto-expanded).
      await userEvent.click(moduleBtn);
      await waitFor(() => {
        expect(screen.queryByText('Intro to Biology')).not.toBeInTheDocument();
      });

      // Second click: expand again.
      await userEvent.click(moduleBtn);
      await waitFor(() => {
        expect(screen.getByText('Intro to Biology')).toBeInTheDocument();
      });
    });
  });

  // ── 8. Content item click — selects content ───────────────────────────────

  describe('content item click', () => {
    it('clicking an unlocked content item passes it to ContentPlayer', async () => {
      renderPage();
      // Auto-select shows content-1. Click content-2 (the doc) to change selection.
      await screen.findByText('Reading: Cell Structure');

      await userEvent.click(screen.getByText('Reading: Cell Structure'));

      await waitFor(() => {
        const player = screen.getByTestId('content-player');
        expect(player).toHaveAttribute('data-content-id', 'content-2');
      });
    });
  });

  // ── 9. Locked content item ────────────────────────────────────────────────

  describe('locked content item', () => {
    it('locked content button has the disabled attribute', async () => {
      renderPage();
      await screen.findByText('Advanced Genetics');

      const lockedBtn = screen.getByText('Advanced Genetics').closest('button')!;
      expect(lockedBtn).toBeDisabled();
    });
  });

  // ── 10. Completed content item — check icon ───────────────────────────────

  describe('completed content item', () => {
    it('renders the check icon (CheckCircleSolidIcon) for a completed content item', async () => {
      renderPage();
      await screen.findByText('Reading: Cell Structure');

      // The check icon has class text-emerald-500; confirm it exists in the DOM
      // alongside the completed content item.
      const docBtn = screen.getByText('Reading: Cell Structure').closest('button')!;
      const checkIcon = docBtn.querySelector('.text-emerald-500');
      expect(checkIcon).toBeInTheDocument();
    });
  });

  // ── 11. VIDEO content type label ──────────────────────────────────────────

  describe('content type labels', () => {
    it('shows "Video" sub-label for VIDEO content type', async () => {
      renderPage();
      await screen.findByText('Intro to Biology');

      // Sub-label rendered inside the content row.
      expect(screen.getByText(/^Video/)).toBeInTheDocument();
    });

    // ── 12. DOCUMENT content type label ─────────────────────────────────────

    it('shows "Reading" sub-label for DOCUMENT content type', async () => {
      renderPage();
      await screen.findByText('Reading: Cell Structure');

      // "Reading" label can appear multiple times (doc + locked doc share type).
      const readingLabels = screen.getAllByText(/^Reading/);
      expect(readingLabels.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── 13. ContentPlayer rendered ────────────────────────────────────────────

  describe('ContentPlayer rendering', () => {
    it('renders ContentPlayer stub when content is auto-selected on load', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getByTestId('content-player')).toBeInTheDocument();
      });
    });

    it('ContentPlayer receives the auto-selected content id', async () => {
      renderPage();
      await waitFor(() => {
        expect(screen.getByTestId('content-player')).toHaveAttribute(
          'data-content-id',
          'content-1',
        );
      });
    });
  });

  // ── 14. "Select an item to begin" placeholder ─────────────────────────────

  describe('"Select an item to begin" placeholder', () => {
    it('shows placeholder text when a module has no contents (auto-select yields null)', async () => {
      mockedGetCourseDetail.mockResolvedValue(MOCK_COURSE_EMPTY_MODULE);
      renderPage();

      await waitFor(() => {
        expect(screen.getByText(/select an item to begin/i)).toBeInTheDocument();
      });
    });

    it('does not render ContentPlayer when placeholder is shown', async () => {
      mockedGetCourseDetail.mockResolvedValue(MOCK_COURSE_EMPTY_MODULE);
      renderPage();

      await waitFor(() => {
        expect(screen.queryByTestId('content-player')).not.toBeInTheDocument();
      });
    });
  });

  // ── 15. Auto-select on load ───────────────────────────────────────────────

  describe('auto-select on load', () => {
    it('auto-selects the first incomplete unlocked content after course loads', async () => {
      renderPage();
      // content-1 is not locked + not completed → should be auto-selected.
      await waitFor(() => {
        expect(screen.getByTestId('content-player')).toHaveAttribute(
          'data-content-id',
          'content-1',
        );
      });
    });
  });

  // ── 16. ChatWidget rendered ───────────────────────────────────────────────

  describe('ChatWidget', () => {
    it('renders ChatWidget when courseId is set', async () => {
      renderPage();
      // ChatWidget is rendered unconditionally as long as courseId truthy.
      await waitFor(() => {
        expect(screen.getByTestId('chat-widget')).toBeInTheDocument();
      });
    });
  });

  // ── 17. Sidebar toggle button ─────────────────────────────────────────────

  describe('sidebar toggle button', () => {
    it('renders the "Toggle course rail" button in the DOM (lg:hidden — CSS only)', async () => {
      renderPage();
      await waitFor(() => {
        expect(
          screen.getByRole('button', { name: /toggle course rail/i }),
        ).toBeInTheDocument();
      });
    });
  });

  // ── 18. Close sidebar button ──────────────────────────────────────────────

  describe('close sidebar button', () => {
    it('clicking "Toggle course rail" opens sidebar, and clicking "Close course rail" closes it', async () => {
      renderPage();
      // Use findByRole to avoid the ambiguity between h1 and sidebar h2.
      await screen.findByRole('heading', { level: 1, name: /biology 101/i });

      // In JSDOM, matchMedia returns false so sidebarOpen starts false.
      // Open sidebar first.
      const toggleBtn = screen.getByRole('button', { name: /toggle course rail/i });
      await userEvent.click(toggleBtn);

      // Sidebar is now open; the close button becomes functionally visible.
      const closeBtn = screen.getByRole('button', { name: /close course rail/i });
      expect(closeBtn).toBeInTheDocument();

      // Clicking close sets sidebarOpen → false; the aside gets -translate-x-full.
      // We verify the close button click doesn't throw and the DOM settles.
      await userEvent.click(closeBtn);

      // After closing, toggle button is still in DOM (lg:hidden CSS class).
      expect(screen.getByRole('button', { name: /toggle course rail/i })).toBeInTheDocument();
    });
  });

  // ── 19. handleComplete — success ─────────────────────────────────────────

  describe('handleComplete (success)', () => {
    it('calls studentService.completeContent with the selected content id', async () => {
      renderPage();
      await screen.findByTestId('content-player');

      await userEvent.click(screen.getByRole('button', { name: /mark complete/i }));

      await waitFor(() => {
        expect(mockedCompleteContent).toHaveBeenCalledWith('content-1');
      });
    });
  });

  // ── 20. handleComplete — error ────────────────────────────────────────────

  describe('handleComplete (error)', () => {
    it('shows a "Content Locked" toast when completeContent rejects', async () => {
      mockedCompleteContent.mockRejectedValue({
        response: { data: { error: 'Content locked.' } },
      });

      renderPage();
      await screen.findByTestId('content-player');

      await userEvent.click(screen.getByRole('button', { name: /mark complete/i }));

      await waitFor(() => {
        expect(screen.getByText('Content Locked')).toBeInTheDocument();
      });
    });

    it('shows the server error message inside the toast on rejection', async () => {
      mockedCompleteContent.mockRejectedValue({
        response: { data: { error: 'Content locked.' } },
      });

      renderPage();
      await screen.findByTestId('content-player');

      await userEvent.click(screen.getByRole('button', { name: /mark complete/i }));

      await waitFor(() => {
        expect(screen.getByText('Content locked.')).toBeInTheDocument();
      });
    });
  });

  // ── 21. Completion % in top bar ───────────────────────────────────────────

  describe('completion percentage in top bar', () => {
    it('renders CompletionRing with the course progress percentage value', async () => {
      renderPage();
      await waitFor(() => {
        const rings = screen.getAllByTestId('completion-ring');
        // At least one ring should carry the top-bar course completion value (33).
        const topBarRing = rings.find(
          (r) => r.getAttribute('data-value') === '33',
        );
        expect(topBarRing).toBeDefined();
      });
    });

    it('shows the rounded percentage text "{n}%" in the top bar', async () => {
      renderPage();
      await waitFor(() => {
        // The top bar renders <p>{Math.round(percentage)}%</p>
        const pcts = screen.getAllByText('33%');
        expect(pcts.length).toBeGreaterThanOrEqual(1);
      });
    });
  });

  // ── 22. Module lock_reason ────────────────────────────────────────────────

  describe('module lock_reason', () => {
    it('displays lock_reason text under a locked module title', async () => {
      mockedGetCourseDetail.mockResolvedValue(MOCK_COURSE_LOCKED_MODULE);
      renderPage();

      await waitFor(() => {
        expect(screen.getByText('Finish the prerequisite first')).toBeInTheDocument();
      });
    });
  });
});
