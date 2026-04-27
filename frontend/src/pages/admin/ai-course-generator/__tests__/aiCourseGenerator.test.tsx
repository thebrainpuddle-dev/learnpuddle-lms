// src/pages/admin/ai-course-generator/__tests__/aiCourseGenerator.test.tsx
// RTL + Vitest tests for the AI Course Generator feature.
// 10 required tests (plus some helpers).

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '../../../../test-utils';
import { Routes, Route } from 'react-router-dom';

// ─── Mocks ────────────────────────────────────────────────────────────────────

// Mock the API module so we never make real HTTP calls
vi.mock('../../../../config/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

// Mock the service module
vi.mock('../../../../services/aiCourseGeneratorService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../../services/aiCourseGeneratorService')>();
  return {
    ...actual,
    aiCourseGeneratorService: {
      createJob: vi.fn(),
      getJob: vi.fn(),
      listJobs: vi.fn(),
      materialiseJob: vi.fn(),
      deleteJob: vi.fn(),
    },
  };
});

// Mock toast
vi.mock('../../../../components/common/Toast', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../../components/common/Toast')>();
  const mockToast = {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    showToast: vi.fn(),
  };
  return {
    ...actual,
    useToast: () => mockToast,
    ToastProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

// Mock navigate
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// ─── Import component subjects ────────────────────────────────────────────────

import { AIGeneratorHome, mapApiError } from '../AIGeneratorHome';
import { AIGeneratorJobDetail } from '../AIGeneratorJobDetail';
import { AIGeneratorJobsList } from '../AIGeneratorJobsList';
import { SourcePicker } from '../components/SourcePicker';
import { OutlineEditor } from '../components/OutlineEditor';
import { aiCourseGeneratorService, MAX_FILE_BYTES, TERMINAL_STATES, validateOutline } from '../../../../services/aiCourseGeneratorService';
import { useAiGeneratorStore } from '../../../../stores/aiGeneratorStore';
import type { Job, Outline, JobListItem } from '../../../../services/aiCourseGeneratorService';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const makeMockJob = (overrides: Partial<Job> = {}): Job => ({
  id: 'job-uuid-001',
  source_type: 'pdf',
  source_metadata: { filename: 'test.pdf', file_size: 1024 },
  extracted_char_count: null,
  status: 'pending',
  error: null,
  outline_json: null,
  provider: null,
  model: null,
  tokens_prompt: null,
  tokens_completion: null,
  draft_course_id: null,
  created_by_email: 'admin@school.edu',
  started_at: null,
  finished_at: null,
  created_at: '2026-04-20T10:00:00Z',
  updated_at: '2026-04-20T10:00:00Z',
  ...overrides,
});

const makeOutline = (): Outline => ({
  title: 'Introduction to Python',
  description: 'Learn Python from scratch',
  modules: [
    {
      title: 'Module 1: Basics',
      contents: [
        { type: 'text', title: 'Variables', description: '' },
        { type: 'text', title: 'Data Types', description: '' },
      ],
    },
    {
      title: 'Module 2: Control Flow',
      contents: [
        { type: 'text', title: 'If/Else', description: '' },
        { type: 'text', title: 'Loops', description: '' },
      ],
    },
    {
      title: 'Module 3: Functions',
      contents: [
        { type: 'text', title: 'Defining Functions', description: '' },
        { type: 'text', title: 'Arguments', description: '' },
      ],
    },
  ],
});

const renderWithRouter = (ui: React.ReactElement, initialPath = '/') => {
  return render(ui, { useMemoryRouter: true, initialRoute: initialPath });
};

// ─── TASK-062 L2: validateOutline content title 200-char cap ─────────────────

describe('validateOutline — content title length cap (TASK-062 L2)', () => {
  const makeBaseOutline = (contentTitle: string): Outline => ({
    title: 'Valid Course Title',
    description: '',
    modules: [
      {
        title: 'Module 1',
        contents: [
          { type: 'text', title: contentTitle, description: '' },
          { type: 'text', title: 'Second content', description: '' },
        ],
      },
      {
        title: 'Module 2',
        contents: [
          { type: 'text', title: 'Content A', description: '' },
          { type: 'text', title: 'Content B', description: '' },
        ],
      },
      {
        title: 'Module 3',
        contents: [
          { type: 'text', title: 'Content C', description: '' },
          { type: 'text', title: 'Content D', description: '' },
        ],
      },
    ],
  });

  it('returns a content title error when title is 201 characters', () => {
    const longTitle = 'a'.repeat(201);
    const errors = validateOutline(makeBaseOutline(longTitle));
    expect(errors['module_0_content_0_title']).toBe(
      'Content title must be 200 characters or fewer.'
    );
  });

  it('returns no content title error when title is exactly 200 characters', () => {
    const exactTitle = 'a'.repeat(200);
    const errors = validateOutline(makeBaseOutline(exactTitle));
    expect(errors['module_0_content_0_title']).toBeUndefined();
  });
});

// ─── Test 1: Source type picker switches between file vs URL UI ───────────────

describe('SourcePicker — source type switching', () => {
  it('shows file upload UI when file source type is selected', () => {
    const { rerender } = renderWithRouter(
      <SourcePicker
        sourceType="pdf"
        onSourceTypeChange={vi.fn()}
        file={null}
        onFileChange={vi.fn()}
        url=""
        onUrlChange={vi.fn()}
        fileError={null}
        urlError={null}
      />
    );

    // Should show file input, not URL input
    expect(screen.getByTestId('file-drop-zone')).toBeInTheDocument();
    expect(screen.queryByTestId('url-input')).not.toBeInTheDocument();
  });

  it('shows URL input UI when YouTube source type is selected', () => {
    renderWithRouter(
      <SourcePicker
        sourceType="youtube"
        onSourceTypeChange={vi.fn()}
        file={null}
        onFileChange={vi.fn()}
        url=""
        onUrlChange={vi.fn()}
        fileError={null}
        urlError={null}
      />
    );

    // Should show URL input, not file drop zone
    expect(screen.getByTestId('url-input')).toBeInTheDocument();
    expect(screen.queryByTestId('file-drop-zone')).not.toBeInTheDocument();
  });

  it('calls onSourceTypeChange when a different type button is clicked', async () => {
    const onSourceTypeChange = vi.fn();
    renderWithRouter(
      <SourcePicker
        sourceType="pdf"
        onSourceTypeChange={onSourceTypeChange}
        file={null}
        onFileChange={vi.fn()}
        url=""
        onUrlChange={vi.fn()}
        fileError={null}
        urlError={null}
      />
    );

    await userEvent.click(screen.getByTestId('source-type-youtube'));
    expect(onSourceTypeChange).toHaveBeenCalledWith('youtube');
  });
});

// ─── Test 2: File-size client-side guard ──────────────────────────────────────

describe('AIGeneratorHome — file size guard', () => {
  it('shows inline error and disables submit when file exceeds 20 MB', async () => {
    renderWithRouter(<AIGeneratorHome />);

    // Get the hidden file input
    const fileInput = screen.getByTestId('file-input') as HTMLInputElement;

    // Create a mock file that's 30 MB
    const bigFile = new File(['x'.repeat(30 * 1024 * 1024)], 'big.pdf', {
      type: 'application/pdf',
    });
    Object.defineProperty(bigFile, 'size', { value: 30 * 1024 * 1024 });

    fireEvent.change(fileInput, { target: { files: [bigFile] } });

    await waitFor(() => {
      expect(screen.getByTestId('file-error')).toHaveTextContent(
        /exceeds 20 MB/i
      );
    });

    const submitBtn = screen.getByTestId('submit-btn');
    expect(submitBtn).toBeDisabled();
  });
});

// ─── Test 3: URL hostname guard ───────────────────────────────────────────────

describe('SourcePicker — URL hostname guard', () => {
  it('shows an inline error for a non-allowed hostname', async () => {
    const onUrlChange = vi.fn();
    renderWithRouter(
      <SourcePicker
        sourceType="youtube"
        onSourceTypeChange={vi.fn()}
        file={null}
        onFileChange={vi.fn()}
        url="https://evil.com/video"
        onUrlChange={onUrlChange}
        fileError={null}
        urlError="Only YouTube and Vimeo URLs are supported."
      />
    );

    expect(screen.getByTestId('url-error')).toHaveTextContent(
      /Only YouTube and Vimeo/i
    );
  });

  it('shows no error for a valid youtube.com URL', () => {
    renderWithRouter(
      <SourcePicker
        sourceType="youtube"
        onSourceTypeChange={vi.fn()}
        file={null}
        onFileChange={vi.fn()}
        url="https://www.youtube.com/watch?v=abc"
        onUrlChange={vi.fn()}
        fileError={null}
        urlError={null}
      />
    );

    expect(screen.queryByTestId('url-error')).not.toBeInTheDocument();
  });
});

// ─── Test 4: Submit success → navigate to job detail ─────────────────────────

describe('AIGeneratorHome — submit success', () => {
  beforeEach(() => {
    vi.mocked(aiCourseGeneratorService.createJob).mockResolvedValue({
      job_id: 'new-job-id-123',
      status: 'pending',
    });
  });

  it('navigates to job detail page after successful submit with a valid URL', async () => {
    renderWithRouter(<AIGeneratorHome />);

    // Switch to YouTube
    await userEvent.click(screen.getByTestId('source-type-youtube'));

    const urlInput = screen.getByTestId('url-input');
    await userEvent.type(urlInput, 'https://www.youtube.com/watch?v=test123');

    await userEvent.click(screen.getByTestId('submit-btn'));

    await waitFor(() => {
      expect(aiCourseGeneratorService.createJob).toHaveBeenCalledTimes(1);
      expect(mockNavigate).toHaveBeenCalledWith(
        '/admin/ai-course-generator/jobs/new-job-id-123'
      );
    });
  });
});

// ─── Test 5: Poll-until-terminal ──────────────────────────────────────────────

describe('AIGeneratorJobDetail — poll-until-terminal', () => {
  beforeEach(() => {
    // Only fake setTimeout/clearTimeout so React's MessageChannel scheduler and
    // RTL's waitFor setInterval remain real. This prevents the "should advance
    // time" mode from faking MessageChannel and breaking React concurrent mode.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it('polls the job and stops when succeeded state is reached', async () => {
    const getJobMock = vi.mocked(aiCourseGeneratorService.getJob);
    const successJob = makeMockJob({
      status: 'succeeded',
      outline_json: makeOutline(),
    });

    // First call: pending, second call: succeeded
    getJobMock
      .mockResolvedValueOnce(makeMockJob({ status: 'pending' }))
      .mockResolvedValueOnce(successJob);

    renderWithRouter(
      <Routes>
        <Route path="/admin/ai-course-generator/jobs/:jobId" element={<AIGeneratorJobDetail />} />
      </Routes>,
      '/admin/ai-course-generator/jobs/job-uuid-001'
    );

    // Initial load
    await waitFor(() => {
      expect(getJobMock).toHaveBeenCalledTimes(1);
    });

    // Advance timers to trigger polling interval
    await act(async () => {
      vi.advanceTimersByTime(3100);
    });

    await waitFor(() => {
      expect(getJobMock).toHaveBeenCalledTimes(2);
    });

    // After succeeded, should not poll again
    await act(async () => {
      vi.advanceTimersByTime(3100);
    });

    // Count should remain 2 (no more polling after terminal state)
    expect(getJobMock).toHaveBeenCalledTimes(2);
  });
});

// ─── Test 6: Outline edit + validation error (too many modules) ───────────────

describe('OutlineEditor — validation errors', () => {
  it('shows inline error when there are more than 12 modules', async () => {
    // Build an outline with 15 modules
    const outlineWith15 = makeOutline();
    for (let i = 3; i < 15; i++) {
      outlineWith15.modules.push({
        title: `Module ${i + 1}`,
        contents: [
          { type: 'text', title: 'Content A', description: '' },
          { type: 'text', title: 'Content B', description: '' },
        ],
      });
    }

    const onChange = vi.fn();
    renderWithRouter(
      <OutlineEditor
        initialOutline={outlineWith15}
        onChange={onChange}
      />
    );

    // The editor should fire onChange with errors that include 'modules'
    await waitFor(() => {
      expect(onChange).toHaveBeenCalled();
      const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1];
      const errors = lastCall[1] as Record<string, string>;
      expect(errors['modules']).toMatch(/No more than 12/i);
    });

    // Visible error message
    await waitFor(() => {
      expect(screen.getByTestId('modules-error')).toHaveTextContent(
        /No more than 12 modules/i
      );
    });
  });
});

// ─── Test 7: Materialise success → navigate to Course editor ─────────────────

describe('AIGeneratorJobDetail — materialise success', () => {
  beforeEach(() => {
    vi.mocked(aiCourseGeneratorService.getJob).mockResolvedValue(
      makeMockJob({
        status: 'succeeded',
        outline_json: makeOutline(),
      })
    );
    vi.mocked(aiCourseGeneratorService.materialiseJob).mockResolvedValue({
      draft_course_id: 'draft-course-uuid',
      idempotent: false,
    });
  });

  it('navigates to /admin/courses/{id}/edit after successful materialise', async () => {
    renderWithRouter(
      <Routes>
        <Route path="/admin/ai-course-generator/jobs/:jobId" element={<AIGeneratorJobDetail />} />
      </Routes>,
      '/admin/ai-course-generator/jobs/job-uuid-001'
    );

    // Wait for outline editor to appear
    await waitFor(() => {
      expect(screen.getByTestId('materialise-btn')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('materialise-btn'));

    // Confirmation modal
    await waitFor(() => {
      expect(screen.getByTestId('confirm-materialise-btn')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('confirm-materialise-btn'));

    await waitFor(() => {
      expect(aiCourseGeneratorService.materialiseJob).toHaveBeenCalledTimes(1);
      expect(mockNavigate).toHaveBeenCalledWith(
        '/admin/courses/draft-course-uuid/edit'
      );
    });
  });
});

// ─── Test 8: Materialise idempotency toast ────────────────────────────────────

describe('AIGeneratorJobDetail — materialise idempotency', () => {
  it('shows info toast when server returns idempotent=true', async () => {
    const { useToast } = await import('../../../../components/common/Toast');
    const toastMock = (useToast as ReturnType<typeof vi.fn>)();

    vi.mocked(aiCourseGeneratorService.getJob).mockResolvedValue(
      makeMockJob({
        status: 'succeeded',
        outline_json: makeOutline(),
        draft_course_id: 'existing-course-id',
      })
    );
    vi.mocked(aiCourseGeneratorService.materialiseJob).mockResolvedValue({
      draft_course_id: 'existing-course-id',
      idempotent: true,
    });

    renderWithRouter(
      <Routes>
        <Route path="/admin/ai-course-generator/jobs/:jobId" element={<AIGeneratorJobDetail />} />
      </Routes>,
      '/admin/ai-course-generator/jobs/job-uuid-001'
    );

    await waitFor(() => {
      expect(screen.getByTestId('materialise-btn')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('materialise-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('confirm-materialise-btn')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('confirm-materialise-btn'));

    await waitFor(() => {
      expect(toastMock.info).toHaveBeenCalledWith(
        'Draft already created',
        expect.stringContaining('Redirecting')
      );
      expect(mockNavigate).toHaveBeenCalledWith(
        '/admin/courses/existing-course-id/edit'
      );
    });
  });
});

// ─── Test 9: Failed state UI ──────────────────────────────────────────────────

describe('AIGeneratorJobDetail — failed state', () => {
  beforeEach(() => {
    vi.mocked(aiCourseGeneratorService.getJob).mockResolvedValue(
      makeMockJob({
        status: 'failed',
        error: 'LLM quota exceeded after 3 retries.',
      })
    );
  });

  it('shows error banner with verbatim error text and retry button', async () => {
    renderWithRouter(
      <Routes>
        <Route path="/admin/ai-course-generator/jobs/:jobId" element={<AIGeneratorJobDetail />} />
      </Routes>,
      '/admin/ai-course-generator/jobs/job-uuid-001'
    );

    await waitFor(() => {
      expect(screen.getByTestId('error-banner')).toBeInTheDocument();
    });

    expect(screen.getByTestId('error-banner')).toHaveTextContent(
      'LLM quota exceeded after 3 retries.'
    );
    expect(screen.getByTestId('retry-btn')).toBeInTheDocument();
  });
});

// ─── Test 10: Delete confirmation modal ──────────────────────────────────────

describe('AIGeneratorJobsList — delete confirmation', () => {
  const mockJobList: JobListItem[] = [
    {
      id: 'list-job-001',
      source_type: 'pdf',
      status: 'succeeded',
      error: null,
      provider: 'openrouter',
      model: 'gpt-4o',
      draft_course_id: null,
      created_by_email: 'admin@school.edu',
      created_at: '2026-04-20T10:00:00Z',
      finished_at: '2026-04-20T10:05:00Z',
    },
  ];

  beforeEach(() => {
    vi.mocked(aiCourseGeneratorService.listJobs).mockResolvedValue(mockJobList);
    vi.mocked(aiCourseGeneratorService.deleteJob).mockResolvedValue(undefined);
  });

  it('shows delete confirmation modal when delete icon is clicked', async () => {
    renderWithRouter(<AIGeneratorJobsList />);

    await waitFor(() => {
      expect(screen.getByTestId('delete-btn-list-job-001')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('delete-btn-list-job-001'));

    await waitFor(() => {
      expect(screen.getByTestId('delete-modal')).toBeInTheDocument();
    });
  });

  it('calls deleteJob API after confirming deletion', async () => {
    renderWithRouter(<AIGeneratorJobsList />);

    await waitFor(() => {
      expect(screen.getByTestId('delete-btn-list-job-001')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('delete-btn-list-job-001'));
    await waitFor(() => {
      expect(screen.getByTestId('confirm-delete-btn')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('confirm-delete-btn'));

    await waitFor(() => {
      expect(aiCourseGeneratorService.deleteJob).toHaveBeenCalledWith('list-job-001');
    });
  });

  it('shows draft course note when job has draft_course_id', async () => {
    const jobWithDraft: JobListItem[] = [
      {
        ...mockJobList[0],
        id: 'list-job-002',
        draft_course_id: 'draft-123',
      },
    ];
    vi.mocked(aiCourseGeneratorService.listJobs).mockResolvedValue(jobWithDraft);

    renderWithRouter(<AIGeneratorJobsList />);

    await waitFor(() => {
      expect(screen.getByTestId('delete-btn-list-job-002')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('delete-btn-list-job-002'));

    await waitFor(() => {
      // Actual text: "The draft course this job created will NOT be deleted."
      // Use .* to bridge the words between "draft course" and "not be deleted".
      expect(screen.getByTestId('delete-modal')).toHaveTextContent(
        /draft course.*not be deleted/i
      );
    });
  });
});

// ─── TASK-062 L8: validateOutline fires only once per outline change ──────────

describe('OutlineEditor — validateOutline fires once per outline change (TASK-062 L8)', () => {
  it('calls validateOutline exactly once per debounced outline change, not twice', async () => {
    // NOTE: The service mock above strips `validateOutline` from the mock because
    // it uses `...actual` spread. We spy on the real export here.
    // IMPORTANT: capture the original function BEFORE vi.spyOn replaces it on
    // the module namespace. Using serviceModule.validateOutline after spyOn would
    // reference the spy itself → spy.mockImplementation(spy) → infinite recursion
    // → Maximum call stack size exceeded.
    const serviceModule = await import('../../../../services/aiCourseGeneratorService');
    const originalValidateOutline = serviceModule.validateOutline; // capture BEFORE spy
    const spy = vi.spyOn(serviceModule, 'validateOutline');
    spy.mockImplementation(originalValidateOutline); // passthrough to real function

    const onChange = vi.fn();
    const outline = makeOutline();

    renderWithRouter(
      <OutlineEditor initialOutline={outline} onChange={onChange} />
    );

    // Wait for the initial debounced effect to fire
    await waitFor(() => {
      expect(onChange).toHaveBeenCalled();
    });

    const callsBefore = spy.mock.calls.length;

    // Append a SINGLE character to the course title so we produce exactly one
    // outline state change.  Typing many characters with userEvent.type()
    // would fire validateOutline once per keystroke, making the ≤2 upper
    // bound meaningless.  One keystroke → one distinct outline object.
    const titleInput = screen.getByTestId('outline-course-title');
    await userEvent.type(titleInput, 'X');

    // Wait for debounced propagation
    await waitFor(() => {
      const callsAfter = spy.mock.calls.length;
      const delta = callsAfter - callsBefore;

      // Lower bound: at least one call must fire to revalidate the changed title.
      expect(delta).toBeGreaterThan(0);

      // Upper bound: at most 2 calls per single outline change.
      // OutlineEditor has two useMemo(validateOutline, ...) hooks — one on
      // `outline` (for instant feedback) and one on `debouncedOutline` (for
      // the debounced onChange propagation).  They may fire in sequence when
      // the debounced value catches up to the live value, giving delta=2.
      // Any delta > 2 indicates spurious re-validation (e.g. stale-closure
      // identity mismatch causing the same outline reference to re-validate)
      // and should be treated as a regression.
      expect(delta).toBeLessThanOrEqual(2);
    });

    spy.mockRestore();
  });
});

// ─── TASK-062 L5: mapApiError parametric error code mapping ──────────────────

describe('mapApiError — parametric error code mapping (TASK-062 L5)', () => {
  it.each([
    [413, undefined, undefined, 'exceeds 20 MB'],
    [undefined, 'FILE_TOO_LARGE', undefined, 'exceeds 20 MB'],
    [undefined, 'INVALID_URL_HOST', undefined, 'YouTube and Vimeo'],
    [undefined, 'COST_LIMIT_EXCEEDED', undefined, 'too large'],
    [503, undefined, undefined, 'hourly generation limit'],
    [429, undefined, undefined, 'hourly generation limit'],
    [undefined, 'RATE_LIMIT_EXCEEDED', undefined, 'hourly generation limit'],
    [undefined, 'SERVICE_UNAVAILABLE', undefined, 'hourly generation limit'],
  ] as [number | undefined, string | undefined, string | undefined, string][])(
    'status=%s code=%s → message contains "%s"',
    (status, code, detail, expectedSubstring) => {
      const err = {
        response: {
          status,
          data: {
            error: code,
            detail,
          },
        },
      };
      expect(mapApiError(err)).toContain(expectedSubstring);
    }
  );
});

// ─── TASK-062 L10: reconnecting hint when errorCount >= 2 ────────────────────

describe('AIGeneratorJobDetail — reconnecting hint', () => {
  beforeEach(() => {
    useAiGeneratorStore.getState().reset();
  });

  afterEach(() => {
    useAiGeneratorStore.getState().reset();
  });

  it('shows reconnecting hint when polling errorCount is >= 2 and job is not terminal', async () => {
    vi.mocked(aiCourseGeneratorService.getJob).mockResolvedValue(
      makeMockJob({ status: 'extracting' })
    );

    renderWithRouter(
      <Routes>
        <Route path="/admin/ai-course-generator/jobs/:jobId" element={<AIGeneratorJobDetail />} />
      </Routes>,
      '/admin/ai-course-generator/jobs/job-uuid-001'
    );

    // Wait for the component to finish its initial fetch and register in the store
    await waitFor(() => {
      expect(aiCourseGeneratorService.getJob).toHaveBeenCalled();
    });

    // Now force the errorCount to 3 via direct store state mutation
    await act(async () => {
      useAiGeneratorStore.setState((state) => ({
        pollingRegistry: {
          ...state.pollingRegistry,
          'job-uuid-001': {
            ...(state.pollingRegistry['job-uuid-001'] ?? {
              jobId: 'job-uuid-001',
              pollingState: 'polling' as const,
              backoffMs: 12000,
            }),
            errorCount: 3,
          },
        },
      }));
    });

    await waitFor(() => {
      expect(screen.getByTestId('reconnecting-hint')).toBeInTheDocument();
    });

    expect(screen.getByTestId('reconnecting-hint')).toHaveTextContent('Reconnecting…');
  });
});
