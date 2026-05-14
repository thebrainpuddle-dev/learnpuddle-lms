// src/pages/superadmin/SuperAdminTemplateManagerPage.test.tsx
//
// Tests for the super-admin Template Library manager.
// Covers: list render, create form Zod validation (invalid blueprint JSON),
//         publish toggle, soft delete (unpublish), hard delete requires checkbox.

import React from 'react';
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { SuperAdminTemplateManagerPage } from './SuperAdminTemplateManagerPage';
import { courseTemplatesService } from '../../services/courseTemplatesService';
import { ToastProvider } from '../../components/common';

// ── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('../../services/courseTemplatesService', () => ({
  courseTemplatesService: {
    superAdmin: {
      listAllTemplates: vi.fn(),
      createTemplate: vi.fn(),
      getTemplate: vi.fn(),
      updateTemplate: vi.fn(),
      deleteTemplate: vi.fn(),
    },
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

const mockedSA = courseTemplatesService.superAdmin as {
  listAllTemplates: ReturnType<typeof vi.fn>;
  createTemplate: ReturnType<typeof vi.fn>;
  getTemplate: ReturnType<typeof vi.fn>;
  updateTemplate: ReturnType<typeof vi.fn>;
  deleteTemplate: ReturnType<typeof vi.fn>;
};

// ── Test data ──────────────────────────────────────────────────────────────────

const TEMPLATE_ROW = {
  id: 'tpl-super-1',
  slug: 'ib-pyp-starter',
  title: 'IB PYP Starter',
  description: '',
  category: 'IB_PYP' as const,
  language: 'en',
  estimated_hours: 8,
  level: 'BEGINNER' as const,
  thumbnail_url: '',
  is_published: true,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-10T00:00:00Z',
};

const LIST_RESPONSE = {
  count: 1,
  next: null,
  previous: null,
  results: [TEMPLATE_ROW],
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
  return render(
    <QueryClientProvider client={makeQueryClient()}>
      <ToastProvider>
        <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
          <SuperAdminTemplateManagerPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('SuperAdminTemplateManagerPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedSA.listAllTemplates.mockResolvedValue(LIST_RESPONSE);
  });

  // Test 11 — super-admin list renders rows
  it('renders template rows from the API', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('super-admin-template-manager')).toBeInTheDocument();
    });
    expect(await screen.findByTestId('templates-table')).toBeInTheDocument();
    const rows = screen.getAllByTestId('template-row');
    expect(rows).toHaveLength(1);
    expect(screen.getByText('IB PYP Starter')).toBeInTheDocument();
    expect(screen.getByText('ib-pyp-starter')).toBeInTheDocument();
  });

  // Test 12 — publish toggle calls updateTemplate
  it('calls updateTemplate to toggle publish state', async () => {
    const user = userEvent.setup();
    mockedSA.updateTemplate.mockResolvedValue({
      ...TEMPLATE_ROW,
      is_published: false,
    });
    mockedSA.listAllTemplates
      .mockResolvedValueOnce(LIST_RESPONSE)
      .mockResolvedValue({
        ...LIST_RESPONSE,
        results: [{ ...TEMPLATE_ROW, is_published: false }],
      });

    renderPage();
    await screen.findByTestId('templates-table');

    const toggleBtn = screen.getByTestId(`publish-toggle-${TEMPLATE_ROW.id}`);
    await user.click(toggleBtn);

    await waitFor(() => {
      expect(mockedSA.updateTemplate).toHaveBeenCalledWith(
        TEMPLATE_ROW.id,
        { is_published: false }, // toggling from true → false
      );
    });
  });

  // Test 13 — delete dialog defaults to soft unpublish
  it('delete dialog defaults to soft unpublish radio', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId('templates-table');

    const deleteBtn = screen.getByTestId(`delete-btn-${TEMPLATE_ROW.id}`);
    await user.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    const softRadio = screen.getByTestId('radio-soft') as HTMLInputElement;
    expect(softRadio.checked).toBe(true);
  });

  // Test 14 — hard delete requires "I understand" checkbox
  it('hard delete confirm button disabled without "I understand" checkbox', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId('templates-table');

    const deleteBtn = screen.getByTestId(`delete-btn-${TEMPLATE_ROW.id}`);
    await user.click(deleteBtn);

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    // Select hard delete
    const hardRadio = screen.getByTestId('radio-hard');
    await user.click(hardRadio);

    // Confirm button should be disabled (checkbox not ticked)
    const confirmBtn = screen.getByTestId('confirm-delete-btn');
    expect(confirmBtn).toBeDisabled();
  });

  // Test 15 — hard delete enabled after ticking checkbox
  it('hard delete confirm button enabled after ticking the "I understand" checkbox', async () => {
    const user = userEvent.setup();
    mockedSA.deleteTemplate.mockResolvedValue(null);
    renderPage();
    await screen.findByTestId('templates-table');

    const deleteBtn = screen.getByTestId(`delete-btn-${TEMPLATE_ROW.id}`);
    await user.click(deleteBtn);

    await waitFor(() => screen.getByRole('dialog'));

    await user.click(screen.getByTestId('radio-hard'));
    const checkbox = screen.getByTestId('hard-delete-checkbox');
    await user.click(checkbox);

    const confirmBtn = screen.getByTestId('confirm-delete-btn');
    expect(confirmBtn).not.toBeDisabled();

    await user.click(confirmBtn);

    await waitFor(() => {
      expect(mockedSA.deleteTemplate).toHaveBeenCalledWith(TEMPLATE_ROW.id, true);
    });
  });

  // Test 16 — soft delete calls deleteTemplate(id, false)
  it('soft delete (unpublish) calls deleteTemplate with hard=false', async () => {
    const user = userEvent.setup();
    mockedSA.deleteTemplate.mockResolvedValue({ ...TEMPLATE_ROW, is_published: false });
    renderPage();
    await screen.findByTestId('templates-table');

    const deleteBtn = screen.getByTestId(`delete-btn-${TEMPLATE_ROW.id}`);
    await user.click(deleteBtn);

    await waitFor(() => screen.getByRole('dialog'));

    // Soft is the default — just click confirm
    const confirmBtn = screen.getByTestId('confirm-delete-btn');
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(mockedSA.deleteTemplate).toHaveBeenCalledWith(TEMPLATE_ROW.id, false);
    });
  });

  // Test 17 — super-admin create: blueprint JSON Zod validation
  it('create form rejects invalid blueprint JSON', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByTestId('templates-table');

    // Open create drawer
    await user.click(screen.getByTestId('create-template-btn'));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toBeInTheDocument();

    // Fill minimum required fields
    const slugInput = await screen.findByPlaceholderText(/ib-pyp-inquiry-beginner/i);
    await user.type(slugInput, 'test-slug');

    // Find the title input using the label text
    const allTextboxes = screen.getAllByRole('textbox');
    // allTextboxes[1] is the title input (slug=0, title=1, description=textarea...)
    // Use placeholder-based fallback
    const titleInput = allTextboxes.find(
      (el) => el !== slugInput && (el as HTMLElement).tagName === 'INPUT' && (el as HTMLInputElement).type === 'text',
    ) ?? allTextboxes[1];
    await user.type(titleInput, 'Test Template');

    // Set invalid JSON in blueprint textarea using fireEvent to avoid
    // userEvent bracket-key parsing issues with '[' characters
    const blueprintArea = screen.getByTestId('blueprint-json-textarea');
    fireEvent.change(blueprintArea, { target: { value: '[1,2,3]' } }); // an array, not an object

    // Submit
    const saveBtn = screen.getByTestId('save-template-btn');
    await user.click(saveBtn);

    await waitFor(() => {
      const errors = screen.getAllByText(/Must be valid JSON/i);
      expect(errors.length).toBeGreaterThanOrEqual(1);
    });
    expect(mockedSA.createTemplate).not.toHaveBeenCalled();
  });
});
