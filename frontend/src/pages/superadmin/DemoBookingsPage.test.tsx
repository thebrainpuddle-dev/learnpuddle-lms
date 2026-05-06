// src/pages/superadmin/DemoBookingsPage.test.tsx
//
// Comprehensive Vitest + React Testing Library test suite for DemoBookingsPage.
//
// Covers:
//   - Page heading and subtitle
//   - "Add Booking" button presence
//   - Search input presence
//   - Status filter dropdown (select element)
//   - Loading skeleton while data is fetching
//   - Empty state ("No demo bookings yet")
//   - Booking list: name, email, scheduled date, status badge select, source badge
//   - Status badge colours via CSS class (scheduled=blue, completed=green, cancelled=slate, no_show=red)
//   - Create modal: opens on button click
//   - Create modal: form fields rendered (Name *, Email *, Scheduled Date/Time *)
//   - Create modal: Zod validation on empty submit (name required)
//   - Create modal: calls createDemoBooking on valid submission
//   - Create modal: closes on success
//   - Create modal: closes on Cancel
//   - Status dropdown in row calls updateDemoBooking on change
//   - Send email modal: opens when envelope icon clicked on a booking
//   - Send email modal: shows "Email <name>" heading and "To: <email>"
//   - Send email modal: subject + body fields present
//   - Send email modal: calls sendDemoBookingEmail on submit
//   - Send email modal: closes on Cancel

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DemoBookingsPage } from './DemoBookingsPage';
import { ToastProvider } from '../../components/common';
import { superAdminService } from '../../services/superAdminService';

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../services/superAdminService', () => ({
  superAdminService: {
    listDemoBookings:    vi.fn(),
    createDemoBooking:   vi.fn(),
    updateDemoBooking:   vi.fn(),
    sendDemoBookingEmail: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed service helpers ─────────────────────────────────────────────────────

const mockedService = superAdminService as {
  listDemoBookings:    ReturnType<typeof vi.fn>;
  createDemoBooking:   ReturnType<typeof vi.fn>;
  updateDemoBooking:   ReturnType<typeof vi.fn>;
  sendDemoBookingEmail: ReturnType<typeof vi.fn>;
};

// ── Fixtures ──────────────────────────────────────────────────────────────────

const BOOKING_SCHEDULED = {
  id: 'booking-1',
  name: 'Alice Johnson',
  email: 'alice@example.com',
  company: 'Acme Corp',
  phone: '+1-555-0100',
  source: 'manual' as const,
  cal_event_id: '',
  scheduled_at: '2026-05-10T14:00:00Z',
  notes: 'Interested in starter plan',
  status: 'scheduled' as const,
  followup_sent_at: null,
  created_at: '2026-04-20T10:00:00Z',
  created_by: null,
};

const BOOKING_COMPLETED = {
  id: 'booking-2',
  name: 'Bob Smith',
  email: 'bob@widgets.io',
  company: 'Widgets Inc',
  phone: '+1-555-0200',
  source: 'cal_webhook' as const,
  cal_event_id: 'cal-abc-123',
  scheduled_at: '2026-04-15T09:30:00Z',
  notes: '',
  status: 'completed' as const,
  followup_sent_at: '2026-04-15T12:00:00Z',
  created_at: '2026-04-01T08:00:00Z',
  created_by: null,
};

const BOOKING_CANCELLED = {
  id: 'booking-3',
  name: 'Carol White',
  email: 'carol@school.edu',
  company: '',
  phone: '',
  source: 'manual' as const,
  cal_event_id: '',
  scheduled_at: '2026-04-20T11:00:00Z',
  notes: '',
  status: 'cancelled' as const,
  followup_sent_at: null,
  created_at: '2026-04-10T07:00:00Z',
  created_by: null,
};

const BOOKING_NO_SHOW = {
  id: 'booking-4',
  name: 'Dave Brown',
  email: 'dave@enterprise.com',
  company: 'Enterprise Ltd',
  phone: '+1-555-0400',
  source: 'cal_webhook' as const,
  cal_event_id: 'cal-xyz-456',
  scheduled_at: '2026-04-22T15:00:00Z',
  notes: 'Rescheduled twice',
  status: 'no_show' as const,
  followup_sent_at: null,
  created_at: '2026-04-12T09:00:00Z',
  created_by: null,
};

const MOCK_BOOKINGS_RESPONSE = {
  count: 4,
  results: [BOOKING_SCHEDULED, BOOKING_COMPLETED, BOOKING_CANCELLED, BOOKING_NO_SHOW],
};

// ── QueryClient factory ───────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });

// ── renderPage ────────────────────────────────────────────────────────────────

const renderPage = () =>
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter>
        <ToastProvider>
          <DemoBookingsPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('DemoBookingsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedService.listDemoBookings.mockResolvedValue(MOCK_BOOKINGS_RESPONSE);
    mockedService.createDemoBooking.mockResolvedValue(BOOKING_SCHEDULED);
    mockedService.updateDemoBooking.mockResolvedValue({ ...BOOKING_SCHEDULED, status: 'completed' });
    mockedService.sendDemoBookingEmail.mockResolvedValue({ queued: true, to: 'alice@example.com' });
  });

  // ── Page-level rendering ────────────────────────────────────────────────

  describe('page-level rendering', () => {
    it('renders the "Demo Bookings" heading', async () => {
      renderPage();
      expect(await screen.findByRole('heading', { name: /Demo Bookings/i })).toBeInTheDocument();
    });

    it('renders the subtitle', async () => {
      renderPage();
      expect(await screen.findByText(/Track and manage demo call bookings/i)).toBeInTheDocument();
    });

    it('renders the "Add Booking" button', async () => {
      renderPage();
      expect(await screen.findByRole('button', { name: /Add Booking/i })).toBeInTheDocument();
    });

    it('renders the search input with correct placeholder', async () => {
      renderPage();
      expect(
        await screen.findByPlaceholderText(/Search by name, email, or company/i),
      ).toBeInTheDocument();
    });

    it('renders the status filter dropdown with "All Statuses" default option', async () => {
      renderPage();
      // The status filter is a <select> element
      const selects = await screen.findAllByRole('combobox');
      // The first combobox in the filters section has the "All Statuses" option
      const filterSelect = selects.find((el) =>
        within(el as HTMLElement).queryByText === undefined
          ? false
          : el.innerHTML.includes('All Statuses'),
      );
      expect(filterSelect ?? selects[0]).toBeInTheDocument();
      expect(screen.getByRole('option', { name: /All Statuses/i })).toBeInTheDocument();
    });

    it('renders all four status options in the filter dropdown', async () => {
      renderPage();
      await screen.findByRole('heading', { name: /Demo Bookings/i });
      // Options exist in both the filter select and the inline row selects — just check they exist
      expect(screen.getAllByRole('option', { name: /Scheduled/i }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByRole('option', { name: /Completed/i }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByRole('option', { name: /Cancelled/i }).length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByRole('option', { name: /No show/i }).length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── Loading state ───────────────────────────────────────────────────────

  describe('loading state', () => {
    it('shows loading skeleton (animate-pulse elements) while data is fetching', () => {
      mockedService.listDemoBookings.mockReturnValue(new Promise(() => {}));
      renderPage();
      const pulseEls = document.querySelectorAll('.animate-pulse');
      expect(pulseEls.length).toBeGreaterThanOrEqual(1);
    });
  });

  // ── Empty state ─────────────────────────────────────────────────────────

  describe('empty state', () => {
    it('shows "No demo bookings yet" when results are empty', async () => {
      mockedService.listDemoBookings.mockResolvedValue({ count: 0, results: [] });
      renderPage();
      expect(await screen.findByText(/No demo bookings yet/i)).toBeInTheDocument();
    });

    it('shows the Cal.com hint text in empty state', async () => {
      mockedService.listDemoBookings.mockResolvedValue({ count: 0, results: [] });
      renderPage();
      expect(
        await screen.findByText(/Bookings from Cal\.com will appear here automatically/i),
      ).toBeInTheDocument();
    });
  });

  // ── Booking list rendering ──────────────────────────────────────────────

  describe('booking list rendering', () => {
    it('renders booking names in the table', async () => {
      renderPage();
      expect(await screen.findByText('Alice Johnson')).toBeInTheDocument();
      expect(screen.getByText('Bob Smith')).toBeInTheDocument();
      expect(screen.getByText('Carol White')).toBeInTheDocument();
      expect(screen.getByText('Dave Brown')).toBeInTheDocument();
    });

    it('renders booking email addresses', async () => {
      renderPage();
      await screen.findByText('Alice Johnson');
      expect(screen.getByText('alice@example.com')).toBeInTheDocument();
      expect(screen.getByText('bob@widgets.io')).toBeInTheDocument();
    });

    it('renders a formatted scheduled date', async () => {
      renderPage();
      await screen.findByText('Alice Johnson');
      // The date '2026-05-10T14:00:00Z' formatted in en-US short format will contain "May" and "2026"
      const dateCells = screen.getAllByText(/May.*2026|2026.*May/i);
      expect(dateCells.length).toBeGreaterThanOrEqual(1);
    });

    it('renders "Manual" source badge for manual bookings', async () => {
      renderPage();
      await screen.findByText('Alice Johnson');
      const manualBadges = screen.getAllByText('Manual');
      expect(manualBadges.length).toBeGreaterThanOrEqual(1);
    });

    it('renders "Cal.com" source badge for cal_webhook bookings', async () => {
      renderPage();
      await screen.findByText('Bob Smith');
      const calBadges = screen.getAllByText('Cal.com');
      expect(calBadges.length).toBeGreaterThanOrEqual(1);
    });

    it('renders an email (envelope) button for each booking row', async () => {
      renderPage();
      await screen.findByText('Alice Johnson');
      // Each row has a "Send email" button
      const emailButtons = screen.getAllByTitle('Send email');
      expect(emailButtons.length).toBe(4);
    });
  });

  // ── Status badge colours ────────────────────────────────────────────────

  describe('status badge colour classes', () => {
    it('applies blue classes to the "scheduled" status select', async () => {
      renderPage();
      await screen.findByText('Alice Johnson');
      // Find the status select whose current value is "scheduled"
      const statusSelects = screen.getAllByRole('combobox');
      // The row-level selects (inline status dropdowns) start after the filter select
      const scheduledSelect = statusSelects.find(
        (el) => (el as HTMLSelectElement).value === 'scheduled',
      ) as HTMLSelectElement | undefined;
      expect(scheduledSelect).toBeDefined();
      expect(scheduledSelect!.className).toMatch(/bg-blue-100/);
      expect(scheduledSelect!.className).toMatch(/text-blue-700/);
    });

    it('applies green classes to the "completed" status select', async () => {
      renderPage();
      await screen.findByText('Bob Smith');
      const statusSelects = screen.getAllByRole('combobox');
      const completedSelect = statusSelects.find(
        (el) => (el as HTMLSelectElement).value === 'completed',
      ) as HTMLSelectElement | undefined;
      expect(completedSelect).toBeDefined();
      expect(completedSelect!.className).toMatch(/bg-green-100/);
      expect(completedSelect!.className).toMatch(/text-green-700/);
    });

    it('applies slate classes to the "cancelled" status select', async () => {
      renderPage();
      await screen.findByText('Carol White');
      const statusSelects = screen.getAllByRole('combobox');
      const cancelledSelect = statusSelects.find(
        (el) => (el as HTMLSelectElement).value === 'cancelled',
      ) as HTMLSelectElement | undefined;
      expect(cancelledSelect).toBeDefined();
      expect(cancelledSelect!.className).toMatch(/bg-slate-100/);
      expect(cancelledSelect!.className).toMatch(/text-slate-500/);
    });

    it('applies red classes to the "no_show" status select', async () => {
      renderPage();
      await screen.findByText('Dave Brown');
      const statusSelects = screen.getAllByRole('combobox');
      const noShowSelect = statusSelects.find(
        (el) => (el as HTMLSelectElement).value === 'no_show',
      ) as HTMLSelectElement | undefined;
      expect(noShowSelect).toBeDefined();
      expect(noShowSelect!.className).toMatch(/bg-red-100/);
      expect(noShowSelect!.className).toMatch(/text-red-700/);
    });
  });

  // ── Status dropdown — updateDemoBooking ─────────────────────────────────

  describe('inline status dropdown', () => {
    it('calls updateDemoBooking with new status when row select changes', async () => {
      renderPage();
      await screen.findByText('Alice Johnson');

      const statusSelects = screen.getAllByRole('combobox');
      const scheduledSelect = statusSelects.find(
        (el) => (el as HTMLSelectElement).value === 'scheduled',
      ) as HTMLSelectElement;

      await userEvent.selectOptions(scheduledSelect, 'completed');

      await waitFor(() => {
        expect(mockedService.updateDemoBooking).toHaveBeenCalledWith(
          'booking-1',
          { status: 'completed' },
        );
      });
    });
  });

  // ── Create Booking modal ────────────────────────────────────────────────

  describe('Create Booking modal', () => {
    it('opens when "Add Booking" button is clicked', async () => {
      renderPage();
      const btn = await screen.findByRole('button', { name: /Add Booking/i });
      await userEvent.click(btn);
      expect(screen.getByRole('heading', { name: /Add Demo Booking/i })).toBeInTheDocument();
    });

    it('renders Name, Email, and Scheduled Date/Time fields', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Booking/i }));
      // FormField renders <label htmlFor="name"> → getByLabelText works
      expect(screen.getByLabelText(/Name \*/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Email \*/i)).toBeInTheDocument();
      // The scheduled_at field is a raw <input type="datetime-local"> inside a Controller,
      // associated via a <label> text
      expect(screen.getByText(/Scheduled Date\/Time \*/i)).toBeInTheDocument();
    });

    it('renders Company and Phone fields', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Booking/i }));
      expect(screen.getByLabelText(/Company/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Phone/i)).toBeInTheDocument();
    });

    it('renders a Notes textarea', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Booking/i }));
      expect(screen.getByText(/Notes/i)).toBeInTheDocument();
      // The notes Controller renders a <textarea>
      expect(document.querySelector('textarea')).toBeInTheDocument();
    });

    it('shows "Name is required" Zod error on empty submit', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Booking/i }));
      const submitBtn = screen.getByRole('button', { name: /Create Booking/i });
      await userEvent.click(submitBtn);
      await waitFor(() => {
        expect(screen.getByText(/Name is required/i)).toBeInTheDocument();
      });
    });

    it('shows "Email is required" Zod error when only name is filled', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Booking/i }));
      await userEvent.type(screen.getByLabelText(/Name \*/i), 'Test User');
      await userEvent.click(screen.getByRole('button', { name: /Create Booking/i }));
      await waitFor(() => {
        expect(screen.getByText(/Email is required/i)).toBeInTheDocument();
      });
    });

    it('calls createDemoBooking with correct data on valid submission', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Booking/i }));

      await userEvent.type(screen.getByLabelText(/Name \*/i), 'Eve Clarke');
      await userEvent.type(screen.getByLabelText(/Email \*/i), 'eve@example.com');
      // Fill the datetime-local input (raw <input> inside the Controller wrapper)
      const datetimeInput = document.querySelector('input[type="datetime-local"]') as HTMLInputElement;
      await userEvent.type(datetimeInput, '2026-06-01T10:00');

      await userEvent.click(screen.getByRole('button', { name: /Create Booking/i }));

      await waitFor(() => {
        expect(mockedService.createDemoBooking).toHaveBeenCalledWith(
          expect.objectContaining({
            name: 'Eve Clarke',
            email: 'eve@example.com',
          }),
        );
      });
    });

    it('closes modal after successful creation', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Booking/i }));

      await userEvent.type(screen.getByLabelText(/Name \*/i), 'Eve Clarke');
      await userEvent.type(screen.getByLabelText(/Email \*/i), 'eve@example.com');
      const datetimeInput = document.querySelector('input[type="datetime-local"]') as HTMLInputElement;
      await userEvent.type(datetimeInput, '2026-06-01T10:00');

      await userEvent.click(screen.getByRole('button', { name: /Create Booking/i }));

      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: /Add Demo Booking/i })).not.toBeInTheDocument();
      });
    });

    it('closes modal when Cancel is clicked', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Booking/i }));
      expect(screen.getByRole('heading', { name: /Add Demo Booking/i })).toBeInTheDocument();

      await userEvent.click(screen.getByRole('button', { name: /Cancel/i }));

      await waitFor(() => {
        expect(screen.queryByRole('heading', { name: /Add Demo Booking/i })).not.toBeInTheDocument();
      });
    });

    it('does not call createDemoBooking when form is cancelled', async () => {
      renderPage();
      await userEvent.click(await screen.findByRole('button', { name: /Add Booking/i }));
      await userEvent.click(screen.getByRole('button', { name: /Cancel/i }));
      expect(mockedService.createDemoBooking).not.toHaveBeenCalled();
    });
  });

  // ── Send Email modal ────────────────────────────────────────────────────

  describe('Send Email modal', () => {
    async function openEmailModal(bookingName = 'Alice Johnson') {
      renderPage();
      await screen.findByText(bookingName);
      // Each row has a button with title="Send email"
      const emailButtons = screen.getAllByTitle('Send email');
      await userEvent.click(emailButtons[0]);
    }

    it('opens the email modal when the envelope button is clicked', async () => {
      await openEmailModal();
      expect(
        screen.getByRole('heading', { name: /Email Alice Johnson/i }),
      ).toBeInTheDocument();
    });

    it('displays the recipient email address', async () => {
      await openEmailModal();
      expect(screen.getByText(/To: alice@example\.com/i)).toBeInTheDocument();
    });

    it('renders Subject and Body fields', async () => {
      await openEmailModal();
      // Subject uses FormField → label linked via htmlFor="subject"
      expect(screen.getByLabelText(/Subject \*/i)).toBeInTheDocument();
      // Body is a raw <textarea> inside a Controller with a plain <label>
      expect(screen.getByText(/Body \*/i)).toBeInTheDocument();
      expect(document.querySelector('textarea')).toBeInTheDocument();
    });

    it('calls sendDemoBookingEmail with correct payload on submission', async () => {
      await openEmailModal();

      await userEvent.type(screen.getByLabelText(/Subject \*/i), 'Follow-up on your demo');
      const bodyTextarea = document.querySelector('textarea') as HTMLTextAreaElement;
      await userEvent.type(bodyTextarea, 'Hi Alice, just following up on your demo request.');

      // Exact-match string (no regex) disambiguates the modal's "Send
      // Email" submit from the row's title="Send email" envelope icon.
      await userEvent.click(screen.getByRole('button', { name: 'Send Email' }));

      await waitFor(() => {
        expect(mockedService.sendDemoBookingEmail).toHaveBeenCalledWith(
          'booking-1',
          expect.objectContaining({
            subject: 'Follow-up on your demo',
            body: 'Hi Alice, just following up on your demo request.',
          }),
        );
      });
    });

    it('closes email modal after successful send', async () => {
      await openEmailModal();

      await userEvent.type(screen.getByLabelText(/Subject \*/i), 'Hello');
      const bodyTextarea = document.querySelector('textarea') as HTMLTextAreaElement;
      await userEvent.type(bodyTextarea, 'Some body content.');

      // Exact-match string (no regex) disambiguates the modal's "Send
      // Email" submit from the row's title="Send email" envelope icon.
      await userEvent.click(screen.getByRole('button', { name: 'Send Email' }));

      await waitFor(() => {
        expect(
          screen.queryByRole('heading', { name: /Email Alice Johnson/i }),
        ).not.toBeInTheDocument();
      });
    });

    it('closes email modal when Cancel is clicked', async () => {
      await openEmailModal();
      expect(screen.getByRole('heading', { name: /Email Alice Johnson/i })).toBeInTheDocument();

      await userEvent.click(screen.getByRole('button', { name: /Cancel/i }));

      await waitFor(() => {
        expect(
          screen.queryByRole('heading', { name: /Email Alice Johnson/i }),
        ).not.toBeInTheDocument();
      });
    });

    it('does not call sendDemoBookingEmail when modal is cancelled', async () => {
      await openEmailModal();
      await userEvent.click(screen.getByRole('button', { name: /Cancel/i }));
      expect(mockedService.sendDemoBookingEmail).not.toHaveBeenCalled();
    });

    it('opens with the correct booking for the second row', async () => {
      renderPage();
      await screen.findByText('Bob Smith');
      const emailButtons = screen.getAllByTitle('Send email');
      // Second button → second booking (Bob Smith)
      await userEvent.click(emailButtons[1]);
      expect(
        screen.getByRole('heading', { name: /Email Bob Smith/i }),
      ).toBeInTheDocument();
      expect(screen.getByText(/To: bob@widgets\.io/i)).toBeInTheDocument();
    });
  });
});
