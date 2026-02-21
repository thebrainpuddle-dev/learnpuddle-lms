import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { CourseEditorPage } from './CourseEditorPage';
import api from '../../config/api';
import { useTenantStore } from '../../stores/tenantStore';

jest.mock('../../stores/tenantStore');
jest.mock('../../config/api', () => ({
  __esModule: true,
  default: {
    get: jest.fn(),
    post: jest.fn(),
    patch: jest.fn(),
    delete: jest.fn(),
  },
}));

jest.mock('../../components/common', () => ({
  ...jest.requireActual('../../components/common'),
  useToast: () => ({
    success: jest.fn(),
    error: jest.fn(),
    warning: jest.fn(),
    info: jest.fn(),
  }),
}));

const mockedApi = api as jest.Mocked<typeof api>;
const mockedUseTenantStore = useTenantStore as unknown as jest.Mock;

const LocationProbe: React.FC = () => {
  const location = useLocation();
  return <div data-testid="search">{location.search}</div>;
};

describe('CourseEditorPage tab URL stability', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    mockedUseTenantStore.mockReturnValue({
      hasFeature: jest.fn(() => true),
    });

    mockedApi.get.mockImplementation(async (url: string) => {
      if (url === '/teachers/') {
        return { data: { results: [] } } as any;
      }
      if (url === '/teacher-groups/') {
        return { data: { results: [] } } as any;
      }
      return { data: {} } as any;
    });
    mockedApi.post.mockResolvedValue({ data: {} } as any);
    mockedApi.patch.mockResolvedValue({ data: {} } as any);
    mockedApi.delete.mockResolvedValue({ data: {} } as any);
  });

  const renderPage = (path: string) => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
      },
    });

    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route
              path="/admin/courses/:courseId"
              element={
                <>
                  <LocationProbe />
                  <CourseEditorPage />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  it('normalizes new-course content tab to details', async () => {
    renderPage('/admin/courses/new?tab=content');

    expect(await screen.findByRole('button', { name: 'Create Course' })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('search')).toHaveTextContent('?tab=details');
    });
  });

  it('changes only URL tab param when selecting assignment tab', async () => {
    renderPage('/admin/courses/new?tab=details');

    expect(await screen.findByRole('button', { name: 'Create Course' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Assignment' }));

    await waitFor(() => {
      expect(screen.getByTestId('search')).toHaveTextContent('?tab=assignment');
    });

    await waitFor(() => {
      expect(screen.getByTestId('search')).toHaveTextContent('?tab=assignment');
    });
  });
});
