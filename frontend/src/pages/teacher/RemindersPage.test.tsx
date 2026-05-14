// src/pages/teacher/RemindersPage.test.tsx
//
// FE-055: Tests for the Teacher Reminders page.
// Covers: page header (user name, tenant name), loading state, empty states per filter,
//         filter tabs (ALL/UNREAD/READ) with counts, reminder list rendering (title,
//         message, unread indicator), "Mark all read" button visibility, mark-all-read
//         mutation, individual mark-read button, click navigation (course/assignment),
//         and filter-specific empty state messages.
//
// Mocking strategy:
//   - notificationService (getNotifications, markAsRead, markAllAsRead) via vi.mock
//   - useAuthStore and useTenantStore mocked to return fixed user / theme data
//   - useNavigate mocked via importOriginal spread
//   - usePageTitle stubbed

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { RemindersPage } from './RemindersPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/notificationService', () => ({
  notificationService: {
    getNotifications: vi.fn(),
    markAsRead: vi.fn(),
    markAllAsRead: vi.fn(),
  },
}));

vi.mock('../../stores/authStore', () => ({
  useAuthStore: vi.fn(() => ({
    user: { first_name: 'Alice', last_name: 'Smith' },
  })),
}));

vi.mock('../../stores/tenantStore', () => ({
  useTenantStore: vi.fn(() => ({
    theme: { name: 'Demo School' },
  })),
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { notificationService } from '../../services/notificationService';
const mockGetNotifications = notificationService.getNotifications as ReturnType<typeof vi.fn>;
const mockMarkAsRead = notificationService.markAsRead as ReturnType<typeof vi.fn>;
const mockMarkAllAsRead = notificationService.markAllAsRead as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <RemindersPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

const reminderUnread = {
  id: 'r-1',
  notification_type: 'REMINDER' as const,
  title: 'Complete Module 3',
  message: 'Please complete Module 3 by Friday.',
  course: 'course-123',
  is_read: false,
  is_actionable: true,
  created_at: '2024-01-01T10:00:00Z',
};

const reminderRead = {
  id: 'r-2',
  notification_type: 'REMINDER' as const,
  title: 'Workshop Reminder',
  message: 'Staff workshop is tomorrow at 9 AM.',
  assignment: 'assignment-456',
  is_read: true,
  is_actionable: false,
  created_at: '2024-01-02T12:00:00Z',
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('RemindersPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockMarkAsRead.mockResolvedValue({ ...reminderUnread, is_read: true });
    mockMarkAllAsRead.mockResolvedValue({ marked_read: 1 });
  });

  // ── Page header ─────────────────────────────────────────────────────────────

  it('renders "Reminders" heading', async () => {
    mockGetNotifications.mockResolvedValue([]);
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /reminders/i }),
    ).toBeInTheDocument();
  });

  it('shows user name in subtitle', async () => {
    mockGetNotifications.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(/Alice Smith/)).toBeInTheDocument();
  });

  it('shows tenant name in subtitle when theme.name is set', async () => {
    mockGetNotifications.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText(/Demo School/)).toBeInTheDocument();
  });

  // ── Loading ─────────────────────────────────────────────────────────────────

  it('shows "Loading reminders..." while query is pending', () => {
    mockGetNotifications.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    expect(screen.getByText('Loading reminders...')).toBeInTheDocument();
  });

  // ── Empty states ────────────────────────────────────────────────────────────

  it('shows "No reminders yet" for empty ALL filter', async () => {
    mockGetNotifications.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByText('No reminders yet')).toBeInTheDocument();
  });

  it('shows school admin hint in ALL empty state', async () => {
    mockGetNotifications.mockResolvedValue([]);
    renderPage();
    expect(
      await screen.findByText(/when your school admin sends reminders/i),
    ).toBeInTheDocument();
  });

  it('shows "No unread reminders" when UNREAD filter is empty', async () => {
    const user = userEvent.setup();
    // Only read reminders exist
    mockGetNotifications.mockResolvedValue([reminderRead]);
    renderPage();
    await screen.findByText('Workshop Reminder');
    await user.click(screen.getByRole('button', { name: /unread/i }));
    expect(screen.getByText('No unread reminders')).toBeInTheDocument();
  });

  it('shows "No read reminders" when READ filter is empty', async () => {
    const user = userEvent.setup();
    // Only unread reminders exist
    mockGetNotifications.mockResolvedValue([reminderUnread]);
    renderPage();
    await screen.findByText('Complete Module 3');
    // Scope to filter bar to avoid collision with individual "Read" mark-as-read button
    const filterBar = document.querySelector('[data-tour="teacher-reminders-filters"]')!;
    await user.click(within(filterBar as HTMLElement).getByRole('button', { name: /^read/i }));
    expect(screen.getByText('No read reminders')).toBeInTheDocument();
  });

  // ── Filter tabs ─────────────────────────────────────────────────────────────

  it('renders All, Unread, and Read filter tabs', async () => {
    mockGetNotifications.mockResolvedValue([reminderUnread, reminderRead]);
    renderPage();
    await screen.findByText('Complete Module 3');
    // Scope to filter bar to avoid collision with "Mark all read" and individual "Read" buttons
    const filterBar = document.querySelector('[data-tour="teacher-reminders-filters"]')!;
    const fb = within(filterBar as HTMLElement);
    expect(fb.getByRole('button', { name: /^all/i })).toBeInTheDocument();
    expect(fb.getByRole('button', { name: /^unread/i })).toBeInTheDocument();
    expect(fb.getByRole('button', { name: /^read/i })).toBeInTheDocument();
  });

  it('ALL tab shows total count 2', async () => {
    mockGetNotifications.mockResolvedValue([reminderUnread, reminderRead]);
    renderPage();
    await screen.findByText('Complete Module 3');
    const filterBar = document.querySelector('[data-tour="teacher-reminders-filters"]')!;
    const allBtn = within(filterBar as HTMLElement).getByRole('button', { name: /^all/i });
    expect(allBtn.textContent).toContain('2');
  });

  it('Unread tab shows unread count 1', async () => {
    mockGetNotifications.mockResolvedValue([reminderUnread, reminderRead]);
    renderPage();
    await screen.findByText('Complete Module 3');
    const unreadBtn = screen.getByRole('button', { name: /unread/i });
    expect(unreadBtn.textContent).toContain('1');
  });

  // ── Reminder list ───────────────────────────────────────────────────────────

  it('renders reminder titles in the list', async () => {
    mockGetNotifications.mockResolvedValue([reminderUnread, reminderRead]);
    renderPage();
    expect(await screen.findByText('Complete Module 3')).toBeInTheDocument();
    expect(screen.getByText('Workshop Reminder')).toBeInTheDocument();
  });

  it('renders reminder messages in the list', async () => {
    mockGetNotifications.mockResolvedValue([reminderUnread, reminderRead]);
    renderPage();
    expect(
      await screen.findByText('Please complete Module 3 by Friday.'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Staff workshop is tomorrow at 9 AM.'),
    ).toBeInTheDocument();
  });

  // ── Mark all read ───────────────────────────────────────────────────────────

  it('shows "Mark all read" button when unread reminders exist', async () => {
    mockGetNotifications.mockResolvedValue([reminderUnread]);
    renderPage();
    expect(await screen.findByRole('button', { name: /mark all read/i })).toBeInTheDocument();
  });

  it('does not show "Mark all read" button when no unread reminders', async () => {
    mockGetNotifications.mockResolvedValue([reminderRead]);
    renderPage();
    await screen.findByText('Workshop Reminder');
    expect(screen.queryByRole('button', { name: /mark all read/i })).not.toBeInTheDocument();
  });

  it('calls markAllAsRead when "Mark all read" button is clicked', async () => {
    const user = userEvent.setup();
    mockGetNotifications.mockResolvedValue([reminderUnread]);
    renderPage();
    const btn = await screen.findByRole('button', { name: /mark all read/i });
    await user.click(btn);
    expect(mockMarkAllAsRead).toHaveBeenCalledTimes(1);
  });

  // ── Individual mark-read button ─────────────────────────────────────────────

  it('shows individual "Read" button on unread reminder row', async () => {
    mockGetNotifications.mockResolvedValue([reminderUnread]);
    renderPage();
    await screen.findByText('Complete Module 3');
    // The individual mark-read button is titled "Mark as read" and labeled "Read"
    expect(screen.getByTitle('Mark as read')).toBeInTheDocument();
  });

  it('calls markAsRead with correct id when individual Read button clicked', async () => {
    const user = userEvent.setup();
    mockGetNotifications.mockResolvedValue([reminderUnread]);
    renderPage();
    await screen.findByText('Complete Module 3');
    await user.click(screen.getByTitle('Mark as read'));
    // TanStack Query passes a second context argument to mutationFn — check only the first arg
    expect(mockMarkAsRead.mock.calls[0][0]).toBe('r-1');
  });

  it('does not show individual Read button on already-read reminder', async () => {
    mockGetNotifications.mockResolvedValue([reminderRead]);
    renderPage();
    await screen.findByText('Workshop Reminder');
    expect(screen.queryByTitle('Mark as read')).not.toBeInTheDocument();
  });

  // ── Navigation on click ─────────────────────────────────────────────────────

  it('navigates to course page when unread course reminder is clicked', async () => {
    const user = userEvent.setup();
    mockGetNotifications.mockResolvedValue([reminderUnread]);
    renderPage();
    // The clickable area is a <button> inside the reminder row
    const titleBtn = await screen.findByRole('button', { name: /complete module 3/i });
    await user.click(titleBtn);
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/courses/course-123');
  });

  it('also marks reminder as read when navigating from unread reminder', async () => {
    const user = userEvent.setup();
    mockGetNotifications.mockResolvedValue([reminderUnread]);
    renderPage();
    const titleBtn = await screen.findByRole('button', { name: /complete module 3/i });
    await user.click(titleBtn);
    // TanStack Query passes a second context argument to mutationFn — check only the first arg
    expect(mockMarkAsRead.mock.calls[0][0]).toBe('r-1');
  });

  it('navigates to assignments page when reminder has assignment link', async () => {
    const user = userEvent.setup();
    mockGetNotifications.mockResolvedValue([reminderRead]);
    renderPage();
    const titleBtn = await screen.findByRole('button', { name: /workshop reminder/i });
    await user.click(titleBtn);
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/assignments');
  });

  // ── UNREAD filter ───────────────────────────────────────────────────────────

  it('UNREAD filter shows only unread reminders', async () => {
    const user = userEvent.setup();
    mockGetNotifications.mockResolvedValue([reminderUnread, reminderRead]);
    renderPage();
    await screen.findByText('Complete Module 3');
    await user.click(screen.getByRole('button', { name: /unread/i }));
    expect(screen.getByText('Complete Module 3')).toBeInTheDocument();
    expect(screen.queryByText('Workshop Reminder')).not.toBeInTheDocument();
  });

  // ── READ filter ─────────────────────────────────────────────────────────────

  it('READ filter shows only read reminders', async () => {
    const user = userEvent.setup();
    mockGetNotifications.mockResolvedValue([reminderUnread, reminderRead]);
    renderPage();
    await screen.findByText('Complete Module 3');
    const filterBar = document.querySelector('[data-tour="teacher-reminders-filters"]')!;
    await user.click(within(filterBar as HTMLElement).getByRole('button', { name: /^read/i }));
    expect(screen.getByText('Workshop Reminder')).toBeInTheDocument();
    expect(screen.queryByText('Complete Module 3')).not.toBeInTheDocument();
  });

  // ── Refresh button ──────────────────────────────────────────────────────────

  it('renders the Refresh button', async () => {
    mockGetNotifications.mockResolvedValue([]);
    renderPage();
    expect(await screen.findByRole('button', { name: /refresh/i })).toBeInTheDocument();
  });
});
