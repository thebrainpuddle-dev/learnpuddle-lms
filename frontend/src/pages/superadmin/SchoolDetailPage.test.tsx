import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { SchoolDetailPage } from './SchoolDetailPage';
import { superAdminService } from '../../services/superAdminService';

jest.mock('../../services/superAdminService', () => ({
  PLAN_OPTIONS: ['FREE', 'STARTER', 'PRO', 'ENTERPRISE'],
  FEATURE_FLAGS: [
    { key: 'feature_video_upload', label: 'Video Upload' },
    { key: 'feature_auto_quiz', label: 'Auto Quiz Generation' },
  ],
  superAdminService: {
    getTenant: jest.fn(),
    getTenantUsage: jest.fn(),
    updateTenant: jest.fn(),
    applyPlan: jest.fn(),
    resetAdminPassword: jest.fn(),
    impersonate: jest.fn(),
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

const LocationProbe: React.FC = () => {
  const location = useLocation();
  return <div data-testid="search">{location.search}</div>;
};

const mockSuperAdminService = superAdminService as jest.Mocked<typeof superAdminService>;

const tenantResponse = {
  id: 'tenant-1',
  name: 'Phoenix Greens',
  slug: 'phoenix-greens',
  subdomain: 'phoenixgreens',
  email: 'ops@phoenixgreens.learnpuddle.com',
  is_active: true,
  is_trial: true,
  trial_end_date: null,
  plan: 'STARTER',
  plan_started_at: null,
  plan_expires_at: null,
  max_teachers: 100,
  max_courses: 100,
  max_storage_mb: 10240,
  max_video_duration_minutes: 120,
  primary_color: '#1F4788',
  secondary_color: '#2E5C8A',
  font_family: 'Inter',
  logo: null,
  teacher_count: 5,
  admin_count: 1,
  course_count: 8,
  created_at: '2026-02-10T00:00:00Z',
  updated_at: '2026-02-10T00:00:00Z',
  phone: '',
  address: '',
  feature_video_upload: true,
  feature_auto_quiz: true,
  feature_transcripts: true,
  feature_reminders: true,
  feature_custom_branding: true,
  feature_reports_export: true,
  feature_groups: true,
  feature_certificates: true,
  internal_notes: 'Initial tenant notes',
  published_course_count: 6,
  admin_email: 'admin@learnpuddle.com',
  admin_name: 'Admin User',
};

const usageResponse = {
  teachers: { used: 5, limit: 100 },
  courses: { used: 8, limit: 100 },
  storage_mb: { used: 512, limit: 10240 },
};

describe('SchoolDetailPage tab URL stability', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    mockSuperAdminService.getTenant.mockResolvedValue(tenantResponse);
    mockSuperAdminService.getTenantUsage.mockResolvedValue(usageResponse);
    mockSuperAdminService.updateTenant.mockResolvedValue(tenantResponse);
    mockSuperAdminService.applyPlan.mockResolvedValue({ ok: true });
    mockSuperAdminService.resetAdminPassword.mockResolvedValue({
      message: 'Password reset',
      email: 'admin@learnpuddle.com',
    });
    mockSuperAdminService.impersonate.mockResolvedValue({
      user_email: 'admin@learnpuddle.com',
      tenant_subdomain: 'phoenixgreens',
      tokens: { access: 'a', refresh: 'r' },
    });
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
              path="/super-admin/schools/:tenantId"
              element={
                <>
                  <LocationProbe />
                  <SchoolDetailPage />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };

  it('sanitizes invalid tab to overview and keeps URL stable', async () => {
    renderPage('/super-admin/schools/tenant-1?tab=invalid');

    expect(await screen.findByText('Phoenix Greens')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('search')).toHaveTextContent('?tab=overview');
    });

    expect(screen.getByText('Usage')).toBeInTheDocument();
  });

  it('updates URL via tab clicks without bouncing back', async () => {
    renderPage('/super-admin/schools/tenant-1?tab=overview');

    expect(await screen.findByText('Phoenix Greens')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Plan & Limits' }));

    await waitFor(() => {
      expect(screen.getByTestId('search')).toHaveTextContent('?tab=plan');
    });

    expect(screen.getByText('Subscription Plan')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('search')).toHaveTextContent('?tab=plan');
    });
  });
});
