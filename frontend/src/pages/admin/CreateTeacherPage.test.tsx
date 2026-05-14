// src/pages/admin/CreateTeacherPage.test.tsx
//
// FE-046: Comprehensive tests for the Admin CreateTeacherPage.
// Covers: page structure, form fields, required-field Zod validation, password
// mismatch, successful submission (service call + toast + navigate), server
// field-level errors, generic errors, cancel navigation, loading state, and
// the Create button type attribute.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

import { CreateTeacherPage } from './CreateTeacherPage';
import { ToastProvider } from '../../components/common';
import { adminTeachersService } from '../../services/adminTeachersService';

// ── Module mocks ───────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/adminTeachersService', () => ({
  adminTeachersService: {
    createTeacher: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

const mockToast = { success: vi.fn(), error: vi.fn() };

vi.mock('../../components/common', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../components/common')>();
  return { ...actual, useToast: () => mockToast };
});

// ── Typed service reference ────────────────────────────────────────────────────

const svc = adminTeachersService as {
  createTeacher: ReturnType<typeof vi.fn>;
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function renderPage() {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <CreateTeacherPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

// ── Default mock setup ─────────────────────────────────────────────────────────

beforeEach(() => {
  vi.resetAllMocks();
  mockNavigate.mockReset();
  mockToast.success.mockReset();
  mockToast.error.mockReset();
});

// ─────────────────────────────────────────────────────────────────────────────
// 1. PAGE STRUCTURE
// ─────────────────────────────────────────────────────────────────────────────

describe('CreateTeacherPage — page structure', () => {
  it('renders the "Create Teacher" heading', () => {
    renderPage();
    expect(
      screen.getByRole('heading', { name: /create teacher/i }),
    ).toBeInTheDocument();
  });

  it('renders the subtitle "Create a new teacher under this tenant"', () => {
    renderPage();
    expect(
      screen.getByText('Create a new teacher under this tenant.'),
    ).toBeInTheDocument();
  });

  it('renders all required form labels', () => {
    renderPage();
    expect(screen.getByText('First name')).toBeInTheDocument();
    expect(screen.getByText('Last name')).toBeInTheDocument();
    expect(screen.getByText('Email')).toBeInTheDocument();
    expect(screen.getByText('Password')).toBeInTheDocument();
    expect(screen.getByText('Confirm password')).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 2. FORM FIELDS
// ─────────────────────────────────────────────────────────────────────────────

describe('CreateTeacherPage — form fields', () => {
  it('renders the email field with placeholder "teacher@school.com"', () => {
    renderPage();
    expect(
      screen.getByPlaceholderText('teacher@school.com'),
    ).toBeInTheDocument();
  });

  it('renders the "Employee ID" field (optional)', () => {
    renderPage();
    expect(screen.getByText('Employee ID')).toBeInTheDocument();
  });

  it('renders the "Department" field (optional)', () => {
    renderPage();
    expect(screen.getByText('Department')).toBeInTheDocument();
  });

  it('renders "Must be at least 8 characters" helper text on Password field', () => {
    renderPage();
    expect(
      screen.getByText('Must be at least 8 characters'),
    ).toBeInTheDocument();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 3. REQUIRED FIELD VALIDATION
// ─────────────────────────────────────────────────────────────────────────────

describe('CreateTeacherPage — required field validation', () => {
  it('submitting empty form shows "First name is required" error', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() => {
      expect(screen.getByText('First name is required')).toBeInTheDocument();
    });
    expect(svc.createTeacher).not.toHaveBeenCalled();
  });

  it('submitting empty form shows an email validation error', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() => {
      // Zod fires either "Email is required" (empty string) or
      // "Enter a valid email address" depending on mode; match both.
      const emailError = screen.queryByText('Email is required')
        ?? screen.queryByText('Enter a valid email address');
      expect(emailError).toBeInTheDocument();
    });
    expect(svc.createTeacher).not.toHaveBeenCalled();
  });

  it('submitting empty form shows "Password must be at least 8 characters" error', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() => {
      expect(
        screen.getByText('Password must be at least 8 characters'),
      ).toBeInTheDocument();
    });
    expect(svc.createTeacher).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 4. PASSWORD MISMATCH VALIDATION
// ─────────────────────────────────────────────────────────────────────────────

describe('CreateTeacherPage — password mismatch validation', () => {
  it('shows "Passwords do not match" when passwords differ', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/first name/i), 'Jane');
    await user.type(screen.getByLabelText(/last name/i), 'Doe');
    await user.type(screen.getByPlaceholderText('teacher@school.com'), 'jane@school.com');
    await user.type(screen.getByLabelText(/^password$/i), 'StrongPass1');
    await user.type(screen.getByLabelText(/confirm password/i), 'DifferentPass1');

    await user.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() => {
      expect(screen.getByText('Passwords do not match')).toBeInTheDocument();
    });
    expect(svc.createTeacher).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 5. SUCCESSFUL SUBMISSION
// ─────────────────────────────────────────────────────────────────────────────

describe('CreateTeacherPage — successful submission', () => {
  const VALID_PAYLOAD = {
    first_name: 'Jane',
    last_name: 'Doe',
    email: 'jane@school.com',
    password: 'StrongPass1',
    password_confirm: 'StrongPass1',
    employee_id: '',
    department: '',
  };

  async function fillAndSubmitValidForm(user: ReturnType<typeof userEvent.setup>) {
    await user.type(screen.getByLabelText(/first name/i), VALID_PAYLOAD.first_name);
    await user.type(screen.getByLabelText(/last name/i), VALID_PAYLOAD.last_name);
    await user.type(screen.getByPlaceholderText('teacher@school.com'), VALID_PAYLOAD.email);
    await user.type(screen.getByLabelText(/^password$/i), VALID_PAYLOAD.password);
    await user.type(screen.getByLabelText(/confirm password/i), VALID_PAYLOAD.password_confirm);
    await user.click(screen.getByRole('button', { name: /create/i }));
  }

  it('calls adminTeachersService.createTeacher with the correct form data', async () => {
    svc.createTeacher.mockResolvedValue({ id: 'u-1', ...VALID_PAYLOAD });
    const user = userEvent.setup();
    renderPage();

    await fillAndSubmitValidForm(user);

    await waitFor(() => {
      expect(svc.createTeacher).toHaveBeenCalledWith(
        expect.objectContaining({
          first_name: 'Jane',
          last_name: 'Doe',
          email: 'jane@school.com',
          password: 'StrongPass1',
          password_confirm: 'StrongPass1',
        }),
      );
    });
  });

  it('shows success toast with teacher name after submission', async () => {
    svc.createTeacher.mockResolvedValue({ id: 'u-1', ...VALID_PAYLOAD });
    const user = userEvent.setup();
    renderPage();

    await fillAndSubmitValidForm(user);

    await waitFor(() => {
      expect(mockToast.success).toHaveBeenCalledWith(
        'Teacher created',
        expect.stringContaining('Jane Doe'),
      );
    });
  });

  it('navigates to /admin/teachers on success', async () => {
    svc.createTeacher.mockResolvedValue({ id: 'u-1', ...VALID_PAYLOAD });
    const user = userEvent.setup();
    renderPage();

    await fillAndSubmitValidForm(user);

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/admin/teachers');
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 6. SERVER ERROR — FIELD-LEVEL
// ─────────────────────────────────────────────────────────────────────────────

describe('CreateTeacherPage — server field-level errors', () => {
  function makeAxiosError(data: Record<string, string[]>) {
    // Simulate an Axios error object that passes `axios.isAxiosError()`.
    const err = new Error('Request failed') as any;
    err.isAxiosError = true;
    err.response = { data };
    return err;
  }

  async function fillAndSubmitEmail(
    user: ReturnType<typeof userEvent.setup>,
    email = 'existing@school.com',
  ) {
    await user.type(screen.getByLabelText(/first name/i), 'Jane');
    await user.type(screen.getByLabelText(/last name/i), 'Doe');
    await user.type(screen.getByPlaceholderText('teacher@school.com'), email);
    await user.type(screen.getByLabelText(/^password$/i), 'StrongPass1');
    await user.type(screen.getByLabelText(/confirm password/i), 'StrongPass1');
    await user.click(screen.getByRole('button', { name: /create/i }));
  }

  it('server email error is shown inline on the email field', async () => {
    svc.createTeacher.mockRejectedValue(
      makeAxiosError({ email: ['A user with this email already exists.'] }),
    );
    const user = userEvent.setup();
    renderPage();

    await fillAndSubmitEmail(user);

    await waitFor(() => {
      expect(
        screen.getByText('A user with this email already exists.'),
      ).toBeInTheDocument();
    });
  });

  it('server email error also triggers toast.error with the error message', async () => {
    svc.createTeacher.mockRejectedValue(
      makeAxiosError({ email: ['A user with this email already exists.'] }),
    );
    const user = userEvent.setup();
    renderPage();

    await fillAndSubmitEmail(user);

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith(
        'Validation error',
        'A user with this email already exists.',
      );
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 7. SERVER ERROR — GENERIC
// ─────────────────────────────────────────────────────────────────────────────

describe('CreateTeacherPage — generic server error', () => {
  it('generic Error triggers toast.error("Failed to create teacher", ...)', async () => {
    svc.createTeacher.mockRejectedValue(new Error('Network Error'));
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/first name/i), 'Jane');
    await user.type(screen.getByLabelText(/last name/i), 'Doe');
    await user.type(screen.getByPlaceholderText('teacher@school.com'), 'jane@school.com');
    await user.type(screen.getByLabelText(/^password$/i), 'StrongPass1');
    await user.type(screen.getByLabelText(/confirm password/i), 'StrongPass1');
    await user.click(screen.getByRole('button', { name: /create/i }));

    await waitFor(() => {
      expect(mockToast.error).toHaveBeenCalledWith(
        'Failed to create teacher',
        expect.any(String),
      );
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 8. CANCEL BUTTON
// ─────────────────────────────────────────────────────────────────────────────

describe('CreateTeacherPage — cancel button', () => {
  it('clicking Cancel navigates to /admin/teachers without submitting', async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(mockNavigate).toHaveBeenCalledWith('/admin/teachers');
    expect(svc.createTeacher).not.toHaveBeenCalled();
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 9. LOADING STATE
// ─────────────────────────────────────────────────────────────────────────────

describe('CreateTeacherPage — loading state', () => {
  it('Create button is disabled while the mutation is pending', async () => {
    // Never resolves — keeps mutation in isPending state.
    svc.createTeacher.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/first name/i), 'Jane');
    await user.type(screen.getByLabelText(/last name/i), 'Doe');
    await user.type(screen.getByPlaceholderText('teacher@school.com'), 'jane@school.com');
    await user.type(screen.getByLabelText(/^password$/i), 'StrongPass1');
    await user.type(screen.getByLabelText(/confirm password/i), 'StrongPass1');
    await user.click(screen.getByRole('button', { name: /create/i }));

    // The Button component sets disabled={loading} when mutation.isPending is true.
    await waitFor(() => {
      const createBtn = screen.getByRole('button', { name: /create/i });
      expect(createBtn).toBeDisabled();
    });
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// 10. FORM SUBMIT BUTTON TYPE
// ─────────────────────────────────────────────────────────────────────────────

describe('CreateTeacherPage — submit button', () => {
  it('Create button has type="submit"', () => {
    renderPage();
    const createBtn = screen.getByRole('button', { name: /create/i });
    expect(createBtn).toHaveAttribute('type', 'submit');
  });
});
