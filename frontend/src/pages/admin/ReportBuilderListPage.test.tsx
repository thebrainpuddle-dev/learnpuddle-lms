// src/pages/admin/ReportBuilderListPage.test.tsx

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { ReportBuilderListPage } from './ReportBuilderListPage';
import { reportBuilderService } from '../../services/reportBuilderService';
import { ToastProvider } from '../../components/common/Toast';

vi.mock('../../services/reportBuilderService', () => ({
  reportBuilderService: {
    listDefinitions: vi.fn(),
    deleteDefinition: vi.fn(),
    runDefinition: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

const mockedNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>(
    'react-router-dom',
  );
  return { ...actual, useNavigate: () => mockedNavigate };
});

const mockedService = reportBuilderService as unknown as {
  listDefinitions: ReturnType<typeof vi.fn>;
  deleteDefinition: ReturnType<typeof vi.fn>;
  runDefinition: ReturnType<typeof vi.fn>;
};

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ToastProvider>
          <ReportBuilderListPage />
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ReportBuilderListPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders an empty-state when no definitions exist', async () => {
    mockedService.listDefinitions.mockResolvedValue([]);
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/No reports yet/i)).toBeInTheDocument(),
    );
  });

  it('renders definitions in a table', async () => {
    mockedService.listDefinitions.mockResolvedValue([
      {
        id: 'def-1',
        name: 'Active teachers',
        description: '',
        data_source: 'teacher_progress',
        created_by: null,
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-02T00:00:00Z',
      },
    ]);
    renderPage();
    expect(await screen.findByTestId('definition-row-def-1')).toBeInTheDocument();
    expect(screen.getByText('Active teachers')).toBeInTheDocument();
    expect(screen.getByText('Teacher Progress')).toBeInTheDocument();
  });

  it('navigates to /new when the New report button is clicked', async () => {
    const user = userEvent.setup();
    mockedService.listDefinitions.mockResolvedValue([]);
    renderPage();
    await user.click(await screen.findByTestId('new-report-btn'));
    expect(mockedNavigate).toHaveBeenCalledWith('/admin/reports/builder/new');
  });
});
