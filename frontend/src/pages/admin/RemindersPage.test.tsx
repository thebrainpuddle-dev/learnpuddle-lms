// src/pages/admin/RemindersPage.test.tsx
//
// FE-036 — Comprehensive tests for the Admin Reminders page.
//
// Covers all three tabs and their sub-components:
//   • Tab navigation (4 tests)
//   • RulesSection — automated rules list (6 tests)
//   • ManualSendSection — CUSTOM, ASSIGNMENT_DUE, teacher picker, schedule (10 tests)
//   • HistorySection — loading, data, filter, empty state (6 tests)
//
// Mock strategy: module-level vi.mock() for all network services.
// The QueryClient is created fresh per test (retry: false) so TanStack
// Query never re-tries on expected failures.

import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { RemindersPage } from './RemindersPage';
import { adminRemindersService } from '../../services/adminRemindersService';
import { adminTeachersService } from '../../services/adminTeachersService';
import { adminReportsService } from '../../services/adminReportsService';
import { ToastProvider } from '../../components/common';
import type { ReminderCampaign } from '../../services/adminRemindersService';
import type { User } from '../../types';
import type { ReportAssignment } from '../../services/adminReportsService';

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../services/adminRemindersService', () => ({
  adminRemindersService: {
    preview: vi.fn(),
    send: vi.fn(),
    history: vi.fn(),
    automationStatus: vi.fn(),
  },
}));

vi.mock('../../services/adminTeachersService', () => ({
  adminTeachersService: {
    listTeachers: vi.fn(),
    createTeacher: vi.fn(),
    updateTeacher: vi.fn(),
    deactivateTeacher: vi.fn(),
  },
}));

vi.mock('../../services/adminReportsService', () => ({
  adminReportsService: {
    listAssignments: vi.fn(),
    listCourses: vi.fn(),
    courseProgress: vi.fn(),
    assignmentStatus: vi.fn(),
    engagementHeatmap: vi.fn(),
    getDeadlineAdherence: vi.fn(),
    getApprovalTrends: vi.fn(),
    getCourseEffectiveness: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const mockTeachers: User[] = [
  {
    id: 'teacher-alice',
    email: 'alice@school.com',
    first_name: 'Alice',
    last_name: 'Smith',
    role: 'TEACHER',
    is_active: true,
    email_verified: true,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    id: 'teacher-bob',
    email: 'bob@school.com',
    first_name: 'Bob',
    last_name: 'Jones',
    role: 'TEACHER',
    is_active: true,
    email_verified: true,
    created_at: '2026-01-01T00:00:00Z',
  },
];

const mockAssignments: ReportAssignment[] = [
  { id: 'assign-1', title: 'Algebra Quiz', course_id: 'course-1', due_date: '2026-05-15' },
  { id: 'assign-2', title: 'History Essay', course_id: 'course-2', due_date: '2026-05-20' },
];

const mockCampaigns: ReminderCampaign[] = [
  {
    id: 'campaign-manual',
    reminder_type: 'CUSTOM',
    source: 'MANUAL',
    course: null,
    assignment: null,
    subject: 'Important: Staff Meeting',
    message: 'Don\'t forget the meeting.',
    deadline_override: null,
    automation_key: '',
    created_at: '2026-04-25T10:00:00Z',
    sent_count: 8,
    failed_count: 0,
  },
  {
    id: 'campaign-auto',
    reminder_type: 'COURSE_DEADLINE',
    source: 'AUTOMATED',
    course: 'c1',
    assignment: null,
    subject: 'Deadline Approaching',
    message: 'Your course deadline is near.',
    deadline_override: null,
    automation_key: 'deadline-3d',
    created_at: '2026-04-20T08:00:00Z',
    sent_count: 15,
    failed_count: 2,
  },
];

// ── Render helper ─────────────────────────────────────────────────────────────

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const user = userEvent.setup();
  const utils = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <ToastProvider>
          <RemindersPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { user, qc, ...utils };
}

// ── Scoped mock references ────────────────────────────────────────────────────

const svc = vi.mocked(adminRemindersService);
const teacherSvc = vi.mocked(adminTeachersService);
const reportSvc = vi.mocked(adminReportsService);

// ── Default mock setup ────────────────────────────────────────────────────────

beforeEach(() => {
  vi.resetAllMocks();
  svc.history.mockResolvedValue({ results: mockCampaigns });
  svc.send.mockResolvedValue({ sent: 5, failed: 0 });
  svc.preview.mockResolvedValue({
    recipient_count: 5,
    recipients_preview: [{ id: 'teacher-alice', name: 'Alice Smith', email: 'alice@school.com' }],
    resolved_subject: 'Test Reminder',
    resolved_message: 'Hello all teachers',
  });
  teacherSvc.listTeachers.mockResolvedValue(mockTeachers);
  reportSvc.listAssignments.mockResolvedValue(mockAssignments);
});

// ─────────────────────────────────────────────────────────────────────────────
// 1. TAB NAVIGATION
// ─────────────────────────────────────────────────────────────────────────────

describe('RemindersPage — tab navigation', () => {
  it('renders with the Rules tab active by default', () => {
    renderPage();
    expect(screen.getByText('Automated Rules')).toBeInTheDocument();
  });

  it('switches to Manual Send tab and shows the composer form', async () => {
    const { user } = renderPage();
    await user.click(screen.getByRole('button', { name: /manual send/i }));
    // The section heading "Manual Send" and the tab both appear — assert on the
    // heading specifically plus the form being present.
    const headings = screen.getAllByText('Manual Send');
    expect(headings.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByLabelText(/type/i)).toBeInTheDocument();
  });

  it('switches to History tab and shows the history section', async () => {
    const { user } = renderPage();
    await user.click(screen.getByRole('button', { name: /history/i }));
    // Both the tab button and the section heading contain "History" — assert
    // via the section description which is unique to HistorySection.
    expect(
      screen.getByText(/log of all sent reminders/i),
    ).toBeInTheDocument();
  });

  it('can navigate back to Rules after visiting another tab', async () => {
    const { user } = renderPage();
    await user.click(screen.getByRole('button', { name: /manual send/i }));
    await user.click(screen.getByRole('button', { name: /rules/i }));
    expect(screen.getByText('Automated Rules')).toBeInTheDocument();
    expect(screen.queryByLabelText(/type/i)).not.toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. RULES SECTION
// ─────────────────────────────────────────────────────────────────────────────

describe('RemindersPage — RulesSection (automated rules)', () => {
  it('renders all six default rules', () => {
    renderPage();
    expect(screen.getByText('Course deadline approaching')).toBeInTheDocument();
    expect(screen.getByText('Course deadline imminent')).toBeInTheDocument();
    expect(screen.getByText('Weekly digest for incomplete courses')).toBeInTheDocument();
    expect(screen.getByText('Certification expiry warning')).toBeInTheDocument();
    expect(screen.getByText('Certification expiry urgent')).toBeInTheDocument();
    expect(screen.getByText('Assignment overdue notification')).toBeInTheDocument();
  });

  it('renders trigger labels for each rule', () => {
    renderPage();
    expect(screen.getByText('3 days before deadline')).toBeInTheDocument();
    expect(screen.getByText('Every 7 days')).toBeInTheDocument();
    expect(screen.getByText('30 days before expiry')).toBeInTheDocument();
  });

  it('toggles a rule active state when its switch is clicked', async () => {
    const { user } = renderPage();
    // The "Assignment overdue notification" rule starts inactive.
    const switches = screen.getAllByRole('switch');
    const overdueSwitch = switches[5]; // sixth rule, index 5
    expect(overdueSwitch).toHaveAttribute('aria-checked', 'false');
    await user.click(overdueSwitch);
    expect(overdueSwitch).toHaveAttribute('aria-checked', 'true');
  });

  it('clicking the pencil icon shows an inline number input for that rule', async () => {
    const { user } = renderPage();
    // Find the first edit button (pencil icon)
    const editButtons = screen.getAllByTitle('Edit trigger days');
    await user.click(editButtons[0]);
    // A number input should appear
    const input = screen.getByRole('spinbutton');
    expect(input).toBeInTheDocument();
    // Initial value should match the rule's triggerDays (3)
    expect(input).toHaveValue(3);
  });

  it('saves the updated trigger days when Enter is pressed', async () => {
    const { user } = renderPage();
    const editButtons = screen.getAllByTitle('Edit trigger days');
    await user.click(editButtons[0]);
    const input = screen.getByRole('spinbutton');
    await user.clear(input);
    await user.type(input, '7');
    fireEvent.keyDown(input, { key: 'Enter' });
    // Input should be gone and label should be updated
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    expect(screen.getByText('7 days before deadline')).toBeInTheDocument();
  });

  it('cancels the edit when Escape is pressed', async () => {
    const { user } = renderPage();
    const editButtons = screen.getAllByTitle('Edit trigger days');
    await user.click(editButtons[0]);
    const input = screen.getByRole('spinbutton');
    await user.clear(input);
    await user.type(input, '99');
    fireEvent.keyDown(input, { key: 'Escape' });
    // Input should be gone and original label preserved
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
    expect(screen.getByText('3 days before deadline')).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. MANUAL SEND SECTION
// ─────────────────────────────────────────────────────────────────────────────

describe('RemindersPage — ManualSendSection (manual send form)', () => {
  async function goToManualTab(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole('button', { name: /manual send/i }));
  }

  it('renders type selector, subject, message, and action buttons', async () => {
    const { user } = renderPage();
    await goToManualTab(user);

    expect(screen.getByLabelText(/type/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/subject/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/message/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send now/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /preview/i })).toBeInTheDocument();
  });

  it('shows an assignment picker only when ASSIGNMENT_DUE is selected', async () => {
    const { user } = renderPage();
    await goToManualTab(user);

    // Assignment picker not shown initially (CUSTOM type)
    expect(screen.queryByLabelText(/assignment/i)).not.toBeInTheDocument();

    // Switch to ASSIGNMENT_DUE
    await user.selectOptions(screen.getByLabelText(/type/i), 'ASSIGNMENT_DUE');
    await waitFor(() =>
      expect(screen.getByLabelText(/assignment/i)).toBeInTheDocument(),
    );
  });

  it('populates the assignment picker from the API', async () => {
    const { user } = renderPage();
    await goToManualTab(user);
    await user.selectOptions(screen.getByLabelText(/type/i), 'ASSIGNMENT_DUE');
    await waitFor(() => {
      const picker = screen.getByLabelText(/assignment/i);
      expect(within(picker).getByText('Algebra Quiz')).toBeInTheDocument();
      expect(within(picker).getByText('History Essay')).toBeInTheDocument();
    });
  });

  it('disables the Send button when ASSIGNMENT_DUE is selected but no assignment is chosen', async () => {
    const { user } = renderPage();
    await goToManualTab(user);
    await user.selectOptions(screen.getByLabelText(/type/i), 'ASSIGNMENT_DUE');
    // The component sets disabled={!isPayloadValid} — payload is invalid without assignment_id.
    await waitFor(() => {
      const sendBtn = screen.getByRole('button', { name: /send now/i });
      expect(sendBtn).toBeDisabled();
    });
    expect(svc.send).not.toHaveBeenCalled();
  });

  it('calls send API with CUSTOM payload and shows success toast', async () => {
    const { user } = renderPage();
    await goToManualTab(user);

    await user.type(screen.getByLabelText(/subject/i), 'Staff reminder');
    await user.type(screen.getByLabelText(/message/i), 'Please review your courses.');
    await user.click(screen.getByRole('button', { name: /send now/i }));

    await waitFor(() => {
      expect(svc.send).toHaveBeenCalledWith(
        expect.objectContaining({
          reminder_type: 'CUSTOM',
          subject: 'Staff reminder',
          message: 'Please review your courses.',
        }),
      );
    });
    await waitFor(() =>
      expect(screen.getByText('Reminders sent!')).toBeInTheDocument(),
    );
  });

  it('resets subject and message after a successful send', async () => {
    const { user } = renderPage();
    await goToManualTab(user);

    const subjectInput = screen.getByLabelText(/subject/i);
    const messageTextarea = screen.getByLabelText(/message/i);

    await user.type(subjectInput, 'Test subject');
    await user.type(messageTextarea, 'Test message');
    await user.click(screen.getByRole('button', { name: /send now/i }));

    await waitFor(() => expect(screen.getByText('Reminders sent!')).toBeInTheDocument());
    // After reset the fields should be empty
    expect(subjectInput).toHaveValue('');
    expect(messageTextarea).toHaveValue('');
  });

  it('calls preview API and shows recipient count in the preview panel', async () => {
    const { user } = renderPage();
    await goToManualTab(user);
    await user.click(screen.getByRole('button', { name: /preview/i }));
    await waitFor(() => expect(svc.preview).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.getByText('5')).toBeInTheDocument(), // recipient_count
    );
    expect(screen.getByText('Test Reminder')).toBeInTheDocument(); // resolved_subject
  });

  it('shows an error toast when the send API fails', async () => {
    svc.send.mockRejectedValue({
      response: { data: { error: 'Server unavailable' } },
    });
    const { user } = renderPage();
    await goToManualTab(user);
    await user.click(screen.getByRole('button', { name: /send now/i }));
    await waitFor(() =>
      expect(screen.getByText('Send failed')).toBeInTheDocument(),
    );
  });

  it('shows the schedule datetime picker when Schedule mode is selected', async () => {
    const { user } = renderPage();
    await goToManualTab(user);

    // Find the "Schedule" radio by its label text
    const scheduleRadio = screen.getByLabelText(/schedule/i);
    await user.click(scheduleRadio);
    await waitFor(() =>
      expect(screen.getByLabelText(/schedule date/i)).toBeInTheDocument(),
    );
  });

  it('shows an error toast when Schedule mode is active but no date is set', async () => {
    const { user } = renderPage();
    await goToManualTab(user);
    const scheduleRadio = screen.getByLabelText(/schedule/i);
    await user.click(scheduleRadio);
    // Click the Schedule button without picking a date
    await user.click(screen.getByRole('button', { name: /^schedule$/i }));
    await waitFor(() =>
      expect(screen.getByText('Schedule required')).toBeInTheDocument(),
    );
    expect(svc.send).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. MANUAL SEND — TEACHER PICKER
// ─────────────────────────────────────────────────────────────────────────────
//
// The teacher search has a 300 ms debounce (useDebounce hook inside
// ManualSendSection). We use real timers throughout these tests — userEvent
// key-by-key typing takes ~50ms/char, so by the time we `waitFor` the dropdown
// the debounce has already fired naturally without any fake-timer manipulation.

describe('RemindersPage — ManualSendSection (teacher picker)', () => {
  async function goToManualTab(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole('button', { name: /manual send/i }));
  }

  it('adds a teacher chip when a search result is clicked', async () => {
    const { user } = renderPage();
    await goToManualTab(user);

    const searchInput = screen.getByPlaceholderText(/search teachers/i);
    // Type enough to make debouncedTeacherSearch truthy (fires after ~300ms)
    await user.type(searchInput, 'Ali');

    // waitFor polls until the dropdown appears (debounce fires + query resolves)
    await waitFor(
      () => expect(screen.getByText('Alice Smith')).toBeInTheDocument(),
      { timeout: 3000 },
    );
    await user.click(screen.getByText('Alice Smith'));

    // After clicking Alice, her chip should appear in the recipients area
    await waitFor(() => {
      // Multiple "Alice Smith" nodes expected: dropdown entry gone, chip present
      const allAlice = screen.queryAllByText('Alice Smith');
      expect(allAlice.length).toBeGreaterThan(0);
    });
    // The "Clear all" link appears when at least one teacher is selected
    expect(screen.getByText('Clear all')).toBeInTheDocument();
  });

  it('removes a teacher chip when Clear all is clicked', async () => {
    const { user } = renderPage();
    await goToManualTab(user);

    // Add Alice
    const searchInput = screen.getByPlaceholderText(/search teachers/i);
    await user.type(searchInput, 'Ali');
    await waitFor(
      () => expect(screen.getByText('Alice Smith')).toBeInTheDocument(),
      { timeout: 3000 },
    );
    await user.click(screen.getByText('Alice Smith'));
    await waitFor(() => expect(screen.getByText('Clear all')).toBeInTheDocument());

    // Click "Clear all" to remove all selected teachers
    await user.click(screen.getByText('Clear all'));
    expect(screen.queryByText('Clear all')).not.toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 5. HISTORY SECTION
// ─────────────────────────────────────────────────────────────────────────────

describe('RemindersPage — HistorySection (history log)', () => {
  async function goToHistoryTab(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole('button', { name: /history/i }));
  }

  it('shows a loading spinner while history is being fetched', async () => {
    // Never resolve so loading stays visible
    svc.history.mockReturnValue(new Promise(() => {}));
    const { user } = renderPage();
    await goToHistoryTab(user);
    expect(screen.getByText('Loading history...')).toBeInTheDocument();
  });

  it('renders campaign subjects once history loads', async () => {
    const { user } = renderPage();
    await goToHistoryTab(user);
    await waitFor(() =>
      expect(screen.getByText('Important: Staff Meeting')).toBeInTheDocument(),
    );
    expect(screen.getByText('Deadline Approaching')).toBeInTheDocument();
  });

  it('shows "Manual" and "Auto" source badges for campaigns', async () => {
    const { user } = renderPage();
    await goToHistoryTab(user);
    await waitFor(() => screen.getByText('Important: Staff Meeting'));
    // The filter buttons also use "Manual" — use getAllByText and assert ≥2
    // instances (filter button + badge); "Auto" badge is unique.
    const manualMatches = screen.getAllByText('Manual');
    expect(manualMatches.length).toBeGreaterThanOrEqual(2); // filter + badge
    expect(screen.getByText('Auto')).toBeInTheDocument();
  });

  it('filters to show only MANUAL campaigns when the Manual filter is clicked', async () => {
    const { user } = renderPage();
    await goToHistoryTab(user);
    await waitFor(() => screen.getByText('Deadline Approaching'));

    await user.click(screen.getByRole('button', { name: /^manual$/i }));

    await waitFor(() => {
      expect(screen.getByText('Important: Staff Meeting')).toBeInTheDocument();
      expect(screen.queryByText('Deadline Approaching')).not.toBeInTheDocument();
    });
  });

  it('filters via subject search and hides non-matching campaigns', async () => {
    const { user } = renderPage();
    await goToHistoryTab(user);
    await waitFor(() => screen.getByText('Deadline Approaching'));

    const searchInput = screen.getByPlaceholderText(/search by subject/i);
    await user.type(searchInput, 'Staff');

    await waitFor(() => {
      expect(screen.getByText('Important: Staff Meeting')).toBeInTheDocument();
      expect(screen.queryByText('Deadline Approaching')).not.toBeInTheDocument();
    });
  });

  it('shows empty state when no reminders have been sent', async () => {
    svc.history.mockResolvedValue({ results: [] });
    const { user } = renderPage();
    await goToHistoryTab(user);
    await waitFor(() =>
      expect(screen.getByText('No reminders found')).toBeInTheDocument(),
    );
    expect(screen.getByText('Sent reminders will appear here.')).toBeInTheDocument();
  });
});
