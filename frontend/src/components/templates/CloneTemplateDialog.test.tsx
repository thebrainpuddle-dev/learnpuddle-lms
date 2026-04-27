// src/components/templates/CloneTemplateDialog.test.tsx
//
// Tests for CloneTemplateDialog:
//   - clone happy path (form submit, mutation called, navigation)
//   - Zod validation: title_override > 200 chars
//   - Zod validation: module_prefix > 50 chars
//   - close button

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { CloneTemplateDialog } from './CloneTemplateDialog';
import { courseTemplatesService } from '../../services/courseTemplatesService';
import { ToastProvider } from '../common';
import type { CourseTemplateListItem } from '../../services/courseTemplatesService';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../../services/courseTemplatesService', () => ({
  courseTemplatesService: {
    tenant: {
      cloneTemplate: vi.fn(),
    },
  },
}));

const mockedClone = (courseTemplatesService.tenant.cloneTemplate as ReturnType<typeof vi.fn>);

const mockedNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockedNavigate,
  };
});

// ── Helpers ────────────────────────────────────────────────────────────────────

const TEMPLATE: CourseTemplateListItem = {
  id: 'tpl-1',
  slug: 'ib-pyp-inquiry',
  title: 'IB PYP Inquiry Approach',
  description: 'A beginner template for IB PYP teachers.',
  category: 'IB_PYP',
  language: 'en',
  estimated_hours: 6,
  level: 'BEGINNER',
  thumbnail_url: '',
  is_published: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-10T00:00:00Z',
};

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function renderDialog(template: CourseTemplateListItem | null = TEMPLATE, onClose = vi.fn()) {
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <ToastProvider>
        <MemoryRouter>
          <CloneTemplateDialog template={template} onClose={onClose} />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('CloneTemplateDialog', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  // Test 7 — clone happy path
  it('submits clone mutation and navigates on success', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    mockedClone.mockResolvedValueOnce({
      id: 'course-abc',
      title: 'Custom Title',
      slug: 'custom-title-xyz',
    });

    renderDialog(TEMPLATE, onClose);

    // The dialog should be visible
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    // Fill in title_override
    const titleInput = screen.getByLabelText(/course title/i);
    await user.clear(titleInput);
    await user.type(titleInput, 'Custom Title');

    // Submit
    const submitBtn = screen.getByRole('button', { name: /clone into my courses/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(mockedClone).toHaveBeenCalledWith('tpl-1', {
        title_override: 'Custom Title',
        module_prefix: undefined,
      });
    });

    await waitFor(() => {
      expect(mockedNavigate).toHaveBeenCalledWith('/admin/courses/course-abc/edit');
    });
  });

  // Test 8 — Zod validation: title_override max 200 chars
  it('shows validation error when title_override exceeds 200 characters', async () => {
    const user = userEvent.setup();
    renderDialog();

    const titleInput = screen.getByLabelText(/course title/i);
    const longTitle = 'A'.repeat(201);
    await user.type(titleInput, longTitle);

    const submitBtn = screen.getByRole('button', { name: /clone into my courses/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/200 characters or fewer/i)).toBeInTheDocument();
    });
    expect(mockedClone).not.toHaveBeenCalled();
  });

  // Test 9 — Zod validation: module_prefix max 50 chars
  it('shows validation error when module_prefix exceeds 50 characters', async () => {
    const user = userEvent.setup();
    renderDialog();

    const prefixInput = screen.getByLabelText(/module prefix/i);
    const longPrefix = 'P'.repeat(51);
    await user.type(prefixInput, longPrefix);

    const submitBtn = screen.getByRole('button', { name: /clone into my courses/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText(/50 characters or fewer/i)).toBeInTheDocument();
    });
    expect(mockedClone).not.toHaveBeenCalled();
  });

  // Test 10 — dialog is not rendered when template is null
  it('does not render dialog when template is null', () => {
    renderDialog(null);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
