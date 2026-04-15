import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { CourseEditorPage } from './CourseEditorPage';
import api from '../../config/api';
import { useTenantStore } from '../../stores/tenantStore';

vi.mock('../../stores/tenantStore');
vi.mock('../../config/api', () => ({
  __esModule: true,
  default: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('../../components/common', async () => {
  const actual = await vi.importActual('../../components/common');
  return {
    ...actual,
    useToast: () => ({
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
    }),
  };
});

const mockedApi = api as unknown as { [K in keyof typeof api]: ReturnType<typeof vi.fn> };
const mockedUseTenantStore = useTenantStore as unknown as ReturnType<typeof vi.fn>;

const LocationProbe: React.FC = () => {
  const location = useLocation();
  return <div data-testid="search">{location.search}</div>;
};

describe('CourseEditorPage tab URL stability', () => {
  beforeEach(() => {
    vi.clearAllMocks();

    mockedUseTenantStore.mockReturnValue({
      hasFeature: vi.fn(() => true),
    });

    mockedApi.get.mockImplementation(async (url: string) => {
      if (url === '/courses/abc/') {
        return {
          data: {
            id: 'abc',
            title: 'Demo Course',
            slug: 'demo-course',
            description: 'Demo',
            thumbnail: null,
            thumbnail_url: null,
            is_mandatory: false,
            deadline: null,
            estimated_hours: 0,
            assigned_to_all: true,
            assigned_groups: [],
            assigned_teachers: [],
            is_published: false,
            modules: [],
          },
        } as any;
      }
      if (url === '/courses/abc/assignments/') {
        return { data: [] } as any;
      }
      if (url.startsWith('/courses/abc/assignments/')) {
        return {
          data: {
            id: 'assignment-1',
            title: 'Generated Assignment',
            description: '',
            instructions: '',
            due_date: null,
            max_score: '100',
            passing_score: '70',
            is_mandatory: true,
            is_active: true,
            scope_type: 'COURSE',
            module_id: null,
            module_title: null,
            assignment_type: 'QUIZ',
            generation_source: 'MANUAL',
            generation_metadata: {},
            questions: [],
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-01-01T00:00:00Z',
          },
        } as any;
      }
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

  it('maps unknown tab param to details on edit routes', async () => {
    renderPage('/admin/courses/abc?tab=assignment');

    expect(await screen.findByRole('button', { name: 'Save Changes' })).toBeInTheDocument();

    // 'assignment' is not a valid tab, so it normalizes to 'details'
    await waitFor(() => {
      expect(screen.getByTestId('search')).toHaveTextContent('?tab=details');
    });
  });

  it('changes URL tab param when selecting audience tab', async () => {
    renderPage('/admin/courses/abc?tab=details');

    expect(await screen.findByRole('button', { name: 'Save Changes' })).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Course Audience' }));

    await waitFor(() => {
      expect(screen.getByTestId('search')).toHaveTextContent('?tab=audience');
    });
  });

  it('removes the reusable-assets helper text in content form', async () => {
    renderPage('/admin/courses/abc?tab=content');

    expect(await screen.findByRole('button', { name: 'Save Changes' })).toBeInTheDocument();

    await waitFor(() => {
      expect(
        screen.queryByText(/Need reusable assets across courses/i),
      ).not.toBeInTheDocument();
    });
  });
});
