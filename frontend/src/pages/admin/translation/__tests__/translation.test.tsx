// src/pages/admin/translation/__tests__/translation.test.tsx
// RTL + Vitest tests for the Translation Admin UI feature (TASK-064 + TASK-064b).
// ≥22 required tests (16 original + 5 TASK-064b + 1 L1 per-content).

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, waitFor, fireEvent, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { render } from '../../../../test-utils';
import { Routes, Route } from 'react-router-dom';
import type { Course } from '../../course-editor/types';

// ─── Mocks ────────────────────────────────────────────────────────────────────

vi.mock('../../../../config/api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}));

// Mock fetchCourse used by TranslatePage to enumerate content IDs.
vi.mock('../../course-editor/api', () => ({
  fetchCourse: vi.fn(),
}));

vi.mock('../../../../services/translationService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../../services/translationService')>();
  return {
    ...actual,
    translationService: {
      createCourseJob: vi.fn(),
      getJob: vi.fn(),
      getContentTranslations: vi.fn(),
      approveField: vi.fn(),
      rejectField: vi.fn(),
      editField: vi.fn(),
      publishTranslation: vi.fn(),
    },
  };
});

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

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// ─── Imports ──────────────────────────────────────────────────────────────────

import { TranslatePage } from '../TranslatePage';
import { TranslationReview } from '../TranslationReview';
import { LocalePicker } from '../components/LocalePicker';
import { FieldDiff } from '../components/FieldDiff';
import { translationService } from '../../../../services/translationService';
import type { TranslationJob, ContentTranslationReview } from '../../../../services/translationService';
import { useTranslationStore } from '../../../../stores/translationStore';
import { fetchCourse } from '../../course-editor/api';

// ─── Helpers ──────────────────────────────────────────────────────────────────

const makeMockJob = (overrides: Partial<TranslationJob> = {}): TranslationJob => ({
  id: 'job-uuid-001',
  kind: 'course',
  target_id: 'course-uuid-001',
  target_languages: ['es', 'fr'],
  status: 'pending',
  started_at: null,
  finished_at: null,
  fields_translated: 0,
  error: '',
  created_at: '2026-04-20T10:00:00Z',
  ...overrides,
});

const makeMockReviewRow = (
  overrides: Partial<ContentTranslationReview> = {}
): ContentTranslationReview => ({
  id: 'row-uuid-001',
  source_type: 'content',
  source_id: 'content-uuid-001',
  field: 'title',
  target_language: 'es',
  translated_text: 'Hola Mundo',
  edited_text: null,
  review_status: 'pending',
  reviewed_by: null,
  reviewed_by_email: null,
  reviewed_at: null,
  published_at: null,
  translated_at: '2026-04-20T10:00:00Z',
  updated_at: '2026-04-20T10:00:00Z',
  ...overrides,
});

const makeMockCourse = (contentCount = 1): Course => ({
  id: 'course-uuid-001',
  title: 'Test Course',
  slug: 'test-course',
  description: 'A test course',
  thumbnail: null,
  thumbnail_url: null,
  is_mandatory: false,
  deadline: null,
  estimated_hours: 1,
  assigned_to_all: false,
  assigned_groups: [],
  assigned_teachers: [],
  target_sections: [],
  is_published: false,
  modules: [
    {
      id: 'module-uuid-001',
      title: 'Module 1',
      description: '',
      order: 1,
      contents: Array.from({ length: contentCount }, (_, i) => ({
        id: `content-uuid-00${i + 1}`,
        title: `Content ${i + 1}`,
        content_type: 'TEXT' as const,
        order: i + 1,
        file_url: null,
        text_content: '',
        is_mandatory: false,
        duration: null,
        file_size: null,
      })),
    },
  ],
});

const renderWithRouter = (
  ui: React.ReactElement,
  initialPath = '/admin/courses/course-123/translate'
) => {
  return render(ui, { useMemoryRouter: true, initialRoute: initialPath });
};

// ─── Test 1: Locale picker — submit disabled with no locales selected ─────────

describe('LocalePicker — no selection disables submit', () => {
  it('submit button is disabled when no locale is selected', () => {
    renderWithRouter(
      <Routes>
        <Route path="/admin/courses/:courseId/translate" element={<TranslatePage />} />
      </Routes>
    );

    const submitBtn = screen.getByTestId('translate-submit-btn');
    expect(submitBtn).toBeDisabled();
  });
});

// ─── Test 2: Locale picker — submit enabled after selecting a locale ──────────

describe('LocalePicker — selection enables submit', () => {
  it('submit button is enabled after selecting at least one locale', async () => {
    renderWithRouter(
      <Routes>
        <Route path="/admin/courses/:courseId/translate" element={<TranslatePage />} />
      </Routes>
    );

    await userEvent.click(screen.getByTestId('locale-btn-es'));

    const submitBtn = screen.getByTestId('translate-submit-btn');
    expect(submitBtn).not.toBeDisabled();
  });
});

// ─── Test 3: LocalePicker renders supported locales ────────────────────────────

describe('LocalePicker — renders supported locales', () => {
  it('renders locale buttons for all supported languages', () => {
    const onChange = vi.fn();
    renderWithRouter(
      <LocalePicker selected={[]} onChange={onChange} />
    );

    expect(screen.getByTestId('locale-btn-es')).toBeInTheDocument();
    expect(screen.getByTestId('locale-btn-fr')).toBeInTheDocument();
    expect(screen.getByTestId('locale-btn-de')).toBeInTheDocument();
    expect(screen.getByTestId('locale-btn-ar')).toBeInTheDocument();
  });

  it('shows selected count when locales are selected', () => {
    const onChange = vi.fn();
    renderWithRouter(
      <LocalePicker selected={['es', 'fr']} onChange={onChange} />
    );

    expect(screen.getByTestId('selected-count')).toHaveTextContent('2 languages selected');
  });

  it('toggles locale off when already selected', async () => {
    const onChange = vi.fn();
    renderWithRouter(
      <LocalePicker selected={['es']} onChange={onChange} />
    );

    await userEvent.click(screen.getByTestId('locale-btn-es'));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});

// ─── Test 4: Submit creates job and transitions to review ────────────────────

describe('TranslatePage — submit success', () => {
  beforeEach(() => {
    vi.mocked(translationService.createCourseJob).mockResolvedValue({
      job_id: 'new-job-id-123',
      status: 'pending',
      target_languages: ['es'],
    });
    vi.mocked(translationService.getJob).mockResolvedValue(
      makeMockJob({ id: 'new-job-id-123', status: 'pending' })
    );
    // Single-content course → falls into the single-review path
    vi.mocked(fetchCourse).mockResolvedValue(makeMockCourse(1));
  });

  it('creates a job and navigates to review when submitted', async () => {
    renderWithRouter(
      <Routes>
        <Route path="/admin/courses/:courseId/translate" element={<TranslatePage />} />
      </Routes>
    );

    await userEvent.click(screen.getByTestId('locale-btn-es'));
    await userEvent.click(screen.getByTestId('translate-submit-btn'));

    await waitFor(() => {
      expect(translationService.createCourseJob).toHaveBeenCalledWith('course-123', ['es']);
    });

    // After success and course fetch, review section appears (polling pending banner)
    await waitFor(() => {
      expect(screen.getByTestId('translation-pending-banner')).toBeInTheDocument();
    });
  });
});

// ─── Test 5: Poll-until-terminal ──────────────────────────────────────────────

describe('TranslationReview — poll-until-terminal', () => {
  beforeEach(() => {
    useTranslationStore.getState().reset();
    // Only fake setTimeout/clearTimeout — leaves MessageChannel and setInterval
    // real so React's scheduler and RTL's waitFor continue to work correctly.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  });

  afterEach(() => {
    vi.useRealTimers();
    useTranslationStore.getState().reset();
  });

  it('polls the job and stops when success state is reached', async () => {
    const getJobMock = vi.mocked(translationService.getJob);
    getJobMock
      .mockResolvedValueOnce(makeMockJob({ status: 'pending' }))
      .mockResolvedValueOnce(
        makeMockJob({ status: 'success', fields_translated: 8 })
      );

    renderWithRouter(
      <TranslationReview
        courseId="course-123"
        jobId="job-uuid-001"
        targetLanguages={['es']}
        onRetry={vi.fn()}
      />
    );

    // Wait for at least one initial fetch to have occurred, then snapshot count
    await waitFor(() => {
      expect(getJobMock).toHaveBeenCalled();
    });
    const callsAfterMount = getJobMock.mock.calls.length;

    await act(async () => {
      vi.advanceTimersByTime(3100);
    });

    // At least one more call after timer fires
    await waitFor(() => {
      expect(getJobMock.mock.calls.length).toBeGreaterThan(callsAfterMount);
    });

    const callsAfterFirstPoll = getJobMock.mock.calls.length;

    // After success, should not poll again — advance far past interval
    await act(async () => {
      vi.advanceTimersByTime(3100);
    });

    // No further calls — polling stopped at terminal state
    expect(getJobMock.mock.calls.length).toBe(callsAfterFirstPoll);
  });
});

// ─── Test 6: Succeeded job renders side-by-side review ───────────────────────

describe('TranslationReview — succeeded job shows review', () => {
  beforeEach(() => {
    vi.mocked(translationService.getJob).mockResolvedValue(
      makeMockJob({ status: 'success', fields_translated: 4 })
    );
  });

  it('shows success summary when job is succeeded', async () => {
    renderWithRouter(
      <TranslationReview
        courseId="course-123"
        jobId="job-uuid-001"
        targetLanguages={['es']}
        onRetry={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('translation-success-summary')).toBeInTheDocument();
    });
  });
});

// ─── Test 7: Approve field sets status to approved ────────────────────────────

describe('FieldDiff — approve field', () => {
  it('calls onApprove when Approve button is clicked', async () => {
    const onApprove = vi.fn();
    renderWithRouter(
      <FieldDiff
        fieldKey="title"
        fieldLabel="Title"
        sourceText="Hello World"
        translatedText="Hola Mundo"
        reviewStatus="pending"
        editedText={null}
        onApprove={onApprove}
        onReject={vi.fn()}
        onSaveEdit={vi.fn()}
      />
    );

    await userEvent.click(screen.getByTestId('approve-btn-title'));
    expect(onApprove).toHaveBeenCalledTimes(1);
  });

  it('shows Approved badge when reviewStatus is approved', () => {
    renderWithRouter(
      <FieldDiff
        fieldKey="title"
        fieldLabel="Title"
        sourceText="Hello"
        translatedText="Hola"
        reviewStatus="approved"
        editedText={null}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onSaveEdit={vi.fn()}
      />
    );

    expect(screen.getByTestId('status-approved-title')).toBeInTheDocument();
  });
});

// ─── Test 8: Edit field → save commits edited text ────────────────────────────

describe('FieldDiff — edit field and save', () => {
  it('enters edit mode and calls onSaveEdit with edited text', async () => {
    const onSaveEdit = vi.fn();
    renderWithRouter(
      <FieldDiff
        fieldKey="description"
        fieldLabel="Description"
        sourceText="Original text"
        translatedText="Texto original"
        reviewStatus="pending"
        editedText={null}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onSaveEdit={onSaveEdit}
      />
    );

    await userEvent.click(screen.getByTestId('edit-btn-description'));

    const textarea = screen.getByTestId('edit-textarea-description');
    expect(textarea).toBeInTheDocument();

    await userEvent.clear(textarea);
    await userEvent.type(textarea, 'Texto corregido');

    await userEvent.click(screen.getByTestId('save-edit-btn-description'));

    expect(onSaveEdit).toHaveBeenCalledWith('Texto corregido');
  });
});

// ─── Test 9: Reject field returns to pending (no commit) ──────────────────────

describe('FieldDiff — reject field', () => {
  it('calls onReject and shows rejected badge', async () => {
    const onReject = vi.fn();
    renderWithRouter(
      <FieldDiff
        fieldKey="body"
        fieldLabel="Body"
        sourceText="Source body"
        translatedText="Cuerpo"
        reviewStatus="pending"
        editedText={null}
        onApprove={vi.fn()}
        onReject={onReject}
        onSaveEdit={vi.fn()}
      />
    );

    await userEvent.click(screen.getByTestId('reject-btn-body'));
    expect(onReject).toHaveBeenCalledTimes(1);
  });

  it('shows Rejected badge when reviewStatus is rejected', () => {
    renderWithRouter(
      <FieldDiff
        fieldKey="body"
        fieldLabel="Body"
        sourceText="Source"
        translatedText="Translated"
        reviewStatus="rejected"
        editedText={null}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onSaveEdit={vi.fn()}
      />
    );

    expect(screen.getByTestId('status-rejected-body')).toBeInTheDocument();
  });
});

// ─── Test 10: Failed job shows error + retry button ──────────────────────────

describe('TranslationReview — failed state', () => {
  beforeEach(() => {
    vi.mocked(translationService.getJob).mockResolvedValue(
      makeMockJob({ status: 'failed', error: 'LLM quota exceeded.' })
    );
  });

  it('shows error banner with error text and retry button', async () => {
    const onRetry = vi.fn();
    renderWithRouter(
      <TranslationReview
        courseId="course-123"
        jobId="job-uuid-001"
        targetLanguages={['es']}
        onRetry={onRetry}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('translation-error-banner')).toBeInTheDocument();
    });

    expect(screen.getByTestId('translation-error-banner')).toHaveTextContent(
      'LLM quota exceeded.'
    );
    expect(screen.getByTestId('translation-retry-btn')).toBeInTheDocument();

    await userEvent.click(screen.getByTestId('translation-retry-btn'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});

// ─── Test 11: Cross-tenant 404 redirects ──────────────────────────────────────

describe('TranslationReview — cross-tenant 404 redirect', () => {
  it('redirects to course edit when job returns 404', async () => {
    vi.mocked(translationService.getJob).mockRejectedValue({
      response: { status: 404 },
    });

    renderWithRouter(
      <TranslationReview
        courseId="course-123"
        jobId="job-uuid-001"
        targetLanguages={['es']}
        onRetry={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/admin/courses/course-123/edit');
    });
  });
});

// ─── Test 12: Polling cleanup on unmount ──────────────────────────────────────

describe('TranslationReview — polling cleanup on unmount', () => {
  beforeEach(() => {
    useTranslationStore.getState().reset();
    // Only fake setTimeout/clearTimeout — leaves MessageChannel and setInterval
    // real so React's scheduler and RTL's waitFor continue to work correctly.
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  });

  afterEach(() => {
    vi.useRealTimers();
    useTranslationStore.getState().reset();
  });

  it('stops polling when component unmounts (no dangling requests)', async () => {
    const getJobMock = vi.mocked(translationService.getJob);
    getJobMock.mockResolvedValue(makeMockJob({ status: 'running' }));

    const { unmount } = renderWithRouter(
      <TranslationReview
        courseId="course-123"
        jobId="job-uuid-001"
        targetLanguages={['es']}
        onRetry={vi.fn()}
      />
    );

    // Wait for at least one call to arrive
    await waitFor(() => {
      expect(getJobMock).toHaveBeenCalled();
    });

    // Unmount the component and reset mock counts
    unmount();
    getJobMock.mockClear();

    // Advance time well past polling interval
    await act(async () => {
      vi.advanceTimersByTime(10000);
    });

    // No further calls after unmount
    expect(getJobMock).not.toHaveBeenCalled();
  });
});

// ─── TASK-064b Test 13: approveField calls service + store reflects server response ──

describe('TASK-064b — approveField happy path', () => {
  beforeEach(() => {
    vi.mocked(translationService.getJob).mockResolvedValue(
      makeMockJob({ status: 'success', fields_translated: 4 })
    );
    vi.mocked(translationService.getContentTranslations).mockResolvedValue({
      content_id: 'content-uuid-001',
      lang: 'es',
      rows: [],
    });
    vi.mocked(translationService.approveField).mockResolvedValue(
      makeMockReviewRow({ review_status: 'approved', reviewed_at: '2026-04-21T10:00:00Z' })
    );
  });

  afterEach(() => {
    useTranslationStore.getState().reset();
  });

  it('calls approveField service and updates store review_status to approved', async () => {
    renderWithRouter(
      <TranslationReview
        courseId="course-123"
        jobId="job-uuid-001"
        targetLanguages={['es']}
        contentId="content-uuid-001"
        onRetry={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('translation-success-summary')).toBeInTheDocument();
    });

    // Click approve on the title field
    await userEvent.click(screen.getByTestId('approve-btn-title'));

    await waitFor(() => {
      expect(translationService.approveField).toHaveBeenCalledWith(
        'content-uuid-001',
        'title',
        'es'
      );
    });

    // Store should reflect approved status from server response
    const storeState = useTranslationStore.getState();
    const entry = storeState.fieldReviews['content-uuid-001:es:title'];
    expect(entry?.status).toBe('approved');
  });
});

// ─── TASK-064b Test 14: editField calls service with correct args ──────────────

describe('TASK-064b — editField submits edited_text', () => {
  beforeEach(() => {
    vi.mocked(translationService.getJob).mockResolvedValue(
      makeMockJob({ status: 'success', fields_translated: 4 })
    );
    vi.mocked(translationService.getContentTranslations).mockResolvedValue({
      content_id: 'content-uuid-001',
      lang: 'es',
      rows: [],
    });
    vi.mocked(translationService.editField).mockResolvedValue(
      makeMockReviewRow({
        field: 'description',
        review_status: 'approved',
        edited_text: 'Texto corregido por admin',
      })
    );
  });

  afterEach(() => {
    useTranslationStore.getState().reset();
  });

  it('calls editField service with edited text and store reflects server response', async () => {
    renderWithRouter(
      <TranslationReview
        courseId="course-123"
        jobId="job-uuid-001"
        targetLanguages={['es']}
        contentId="content-uuid-001"
        onRetry={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('translation-success-summary')).toBeInTheDocument();
    });

    // Enter edit mode on description field
    await userEvent.click(screen.getByTestId('edit-btn-description'));
    const textarea = screen.getByTestId('edit-textarea-description');
    await userEvent.clear(textarea);
    await userEvent.type(textarea, 'Texto corregido por admin');
    await userEvent.click(screen.getByTestId('save-edit-btn-description'));

    await waitFor(() => {
      expect(translationService.editField).toHaveBeenCalledWith(
        'content-uuid-001',
        'description',
        'es',
        'Texto corregido por admin'
      );
    });

    const storeState = useTranslationStore.getState();
    const entry = storeState.fieldReviews['content-uuid-001:es:description'];
    expect(entry?.editedText).toBe('Texto corregido por admin');
    expect(entry?.status).toBe('approved');
  });
});

// ─── TASK-064b Test 15: rejectField calls service ─────────────────────────────

describe('TASK-064b — rejectField calls service', () => {
  beforeEach(() => {
    vi.mocked(translationService.getJob).mockResolvedValue(
      makeMockJob({ status: 'success', fields_translated: 4 })
    );
    vi.mocked(translationService.getContentTranslations).mockResolvedValue({
      content_id: 'content-uuid-001',
      lang: 'es',
      rows: [],
    });
    vi.mocked(translationService.rejectField).mockResolvedValue(
      makeMockReviewRow({ field: 'body', review_status: 'rejected' })
    );
  });

  afterEach(() => {
    useTranslationStore.getState().reset();
  });

  it('calls rejectField service and store transitions to rejected', async () => {
    renderWithRouter(
      <TranslationReview
        courseId="course-123"
        jobId="job-uuid-001"
        targetLanguages={['es']}
        contentId="content-uuid-001"
        onRetry={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('translation-success-summary')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('reject-btn-body'));

    await waitFor(() => {
      expect(translationService.rejectField).toHaveBeenCalledWith(
        'content-uuid-001',
        'body',
        'es'
      );
    });

    const storeState = useTranslationStore.getState();
    const entry = storeState.fieldReviews['content-uuid-001:es:body'];
    expect(entry?.status).toBe('rejected');
  });
});

// ─── TASK-064b Test 16: publishTranslation shows success banner ───────────────

describe('TASK-064b — publishTranslation happy path', () => {
  beforeEach(() => {
    vi.mocked(translationService.getJob).mockResolvedValue(
      makeMockJob({ status: 'success', fields_translated: 4 })
    );
    vi.mocked(translationService.getContentTranslations).mockResolvedValue({
      content_id: 'content-uuid-001',
      lang: 'es',
      rows: [],
    });
    vi.mocked(translationService.publishTranslation).mockResolvedValue({
      published_at: '2026-04-21T12:00:00Z',
      rows_published: 3,
      skipped: {},
    });
  });

  afterEach(() => {
    useTranslationStore.getState().reset();
  });

  it('shows publish result banner with rows_published count', async () => {
    renderWithRouter(
      <TranslationReview
        courseId="course-123"
        jobId="job-uuid-001"
        targetLanguages={['es']}
        contentId="content-uuid-001"
        onRetry={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('publish-translation-btn')).toBeInTheDocument();
    });

    await userEvent.click(screen.getByTestId('publish-translation-btn'));

    await waitFor(() => {
      expect(translationService.publishTranslation).toHaveBeenCalledWith(
        'content-uuid-001',
        'es'
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId('publish-result-banner')).toBeInTheDocument();
      expect(screen.getByTestId('publish-result-banner')).toHaveTextContent('3 fields published');
    });

    // Button transitions to Published state
    expect(screen.getByTestId('publish-translation-btn')).toHaveTextContent('Published');
    expect(screen.getByTestId('publish-translation-btn')).toBeDisabled();
  });
});

// ─── TASK-064b Test 17: approveField rollback on server error ─────────────────

describe('TASK-064b — approveField rollback on server error', () => {
  const mockToast = {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    showToast: vi.fn(),
  };

  beforeEach(() => {
    vi.mocked(translationService.getJob).mockResolvedValue(
      makeMockJob({ status: 'success', fields_translated: 4 })
    );
    vi.mocked(translationService.getContentTranslations).mockResolvedValue({
      content_id: 'content-uuid-001',
      lang: 'es',
      rows: [],
    });
    // Simulate server rejecting the approve call
    vi.mocked(translationService.approveField).mockRejectedValue({
      response: { status: 500, data: { detail: 'Internal server error' } },
    });
  });

  afterEach(() => {
    useTranslationStore.getState().reset();
    vi.resetAllMocks();
  });

  it('rolls back optimistic state and shows error toast when approve fails', async () => {
    renderWithRouter(
      <TranslationReview
        courseId="course-123"
        jobId="job-uuid-001"
        targetLanguages={['es']}
        contentId="content-uuid-001"
        onRetry={vi.fn()}
      />
    );

    await waitFor(() => {
      expect(screen.getByTestId('translation-success-summary')).toBeInTheDocument();
    });

    // The approve button should be visible (status is 'pending')
    const approveBtn = screen.getByTestId('approve-btn-title');
    await userEvent.click(approveBtn);

    // After error the store should roll back to pending
    await waitFor(() => {
      expect(translationService.approveField).toHaveBeenCalled();
    });

    await waitFor(() => {
      const storeState = useTranslationStore.getState();
      const entry = storeState.fieldReviews['content-uuid-001:es:title'];
      // Rolled back — either undefined (never set) or back to pending
      const status = entry?.status ?? 'pending';
      expect(status).toBe('pending');
    });

    // The approve button should be visible again (status rolled back to pending)
    await waitFor(() => {
      expect(screen.getByTestId('approve-btn-title')).toBeInTheDocument();
    });
  });
});

// ─── TASK-064 L6 — locale selection survives handleRetry ─────────────────────

describe('TranslatePage L6 — locale selection survives retry', () => {
  beforeEach(() => {
    vi.mocked(translationService.createCourseJob).mockResolvedValue({
      job_id: 'job-retry-001',
      status: 'pending',
      target_languages: ['fr'],
    });
    vi.mocked(translationService.getJob).mockResolvedValue(
      makeMockJob({ id: 'job-retry-001', status: 'failed', error: 'Worker crashed' })
    );
    vi.mocked(fetchCourse).mockResolvedValue(makeMockCourse(1));
  });

  afterEach(() => {
    useTranslationStore.getState().reset();
    vi.resetAllMocks();
  });

  it('locale selection is preserved after clicking Retry on a failed job', async () => {
    renderWithRouter(
      <Routes>
        <Route path="/admin/courses/:courseId/translate" element={<TranslatePage />} />
      </Routes>
    );

    // Select 'fr' locale and submit
    await userEvent.click(screen.getByTestId('locale-btn-fr'));
    await userEvent.click(screen.getByTestId('translate-submit-btn'));

    // Wait for the failed banner to appear
    await waitFor(() => {
      expect(screen.getByTestId('translation-error-banner')).toBeInTheDocument();
    });

    // Click Retry — this should clear jobId but preserve targetLanguages
    await userEvent.click(screen.getByTestId('translation-retry-btn'));

    // After retry the locale picker is visible again with 'fr' still selected
    await waitFor(() => {
      const frBtn = screen.getByTestId('locale-btn-fr');
      expect(frBtn).toHaveAttribute('aria-pressed', 'true');
    });
  });
});

// ─── Test 18: L1 — course with 2 contents renders two independent cards ────────

describe('TranslatePage L1 — per-content cards', () => {
  beforeEach(() => {
    vi.mocked(translationService.createCourseJob).mockResolvedValue({
      job_id: 'job-multi-001',
      status: 'pending',
      target_languages: ['es'],
    });
    vi.mocked(translationService.getJob).mockResolvedValue(
      makeMockJob({ id: 'job-multi-001', status: 'success', fields_translated: 8 })
    );
    vi.mocked(translationService.getContentTranslations).mockResolvedValue({
      content_id: 'content-uuid-001',
      lang: 'es',
      rows: [],
    });
    vi.mocked(translationService.publishTranslation).mockResolvedValue({
      published_at: '2026-04-21T12:00:00Z',
      rows_published: 2,
      skipped: {},
    });
    // Two-content course → multi-card path
    vi.mocked(fetchCourse).mockResolvedValue(makeMockCourse(2));
  });

  afterEach(() => {
    useTranslationStore.getState().reset();
    vi.resetAllMocks();
  });

  it('renders two collapsible cards and each has an independent Publish button', async () => {
    renderWithRouter(
      <Routes>
        <Route path="/admin/courses/:courseId/translate" element={<TranslatePage />} />
      </Routes>
    );

    // Select locale and submit
    await userEvent.click(screen.getByTestId('locale-btn-es'));
    await userEvent.click(screen.getByTestId('translate-submit-btn'));

    // Wait for course fetch + multi-card layout to appear
    await waitFor(() => {
      expect(screen.getByTestId('content-review-card-content-uuid-001')).toBeInTheDocument();
      expect(screen.getByTestId('content-review-card-content-uuid-002')).toBeInTheDocument();
    });

    // Open the first card (defaultOpen=true) — publish button visible
    await waitFor(() => {
      expect(screen.getByTestId('publish-translation-btn')).toBeInTheDocument();
    });

    // Open the second card via toggle
    await userEvent.click(screen.getByTestId('content-review-toggle-content-uuid-002'));

    // Now both cards are open — each has its own publish button
    const publishBtns = await screen.findAllByTestId('publish-translation-btn');
    expect(publishBtns).toHaveLength(2);

    // Click publish on card 1 — only card 1's store key is affected
    await userEvent.click(publishBtns[0]);

    await waitFor(() => {
      expect(translationService.publishTranslation).toHaveBeenCalledWith(
        'content-uuid-001',
        'es'
      );
    });

    // Card 1's button is now Published; card 2's button is still enabled (idle)
    await waitFor(() => {
      const btns = screen.getAllByTestId('publish-translation-btn');
      expect(btns[0]).toHaveTextContent('Published');
      expect(btns[0]).toBeDisabled();
      // Card 2 is unaffected
      expect(btns[1]).not.toBeDisabled();
      expect(btns[1]).not.toHaveTextContent('Published');
    });
  });
});
