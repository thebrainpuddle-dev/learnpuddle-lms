import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { OperationsPage } from './OperationsPage';
import { superAdminService } from '../../services/superAdminService';

vi.mock('../../hooks/usePageTitle', () => ({
  usePageTitle: vi.fn(),
}));

describe('OperationsPage', () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });

  beforeEach(() => {
    vi.spyOn(superAdminService, 'getOpsOverview').mockResolvedValue({
      generated_at: new Date().toISOString(),
      data_freshness_seconds: 5,
      pipeline_lag_seconds: 5,
      data_quality: 'ok',
      refresh_seconds: 10,
      totals: { tenants: 1, healthy: 1, degraded: 0, down: 0, maintenance: 0 },
      mttr_targets: { p1_minutes: 15, p2_minutes: 60 },
      open_incidents: [],
      top_failure_categories: [],
    });
    vi.spyOn(superAdminService, 'listOpsTenants').mockResolvedValue({
      generated_at: new Date().toISOString(),
      data_freshness_seconds: 5,
      pipeline_lag_seconds: 5,
      data_quality: 'ok',
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          tenant_id: 'tenant-1',
          name: 'Alpha School',
          subdomain: 'alpha',
          status: 'HEALTHY',
          last_check_at: new Date().toISOString(),
          last_latency_ms: 120,
          active_failures_24h: 0,
          failures_week: {},
          maintenance_mode: false,
        },
      ],
    });
    vi.spyOn(superAdminService, 'listOpsIncidents').mockResolvedValue({
      generated_at: new Date().toISOString(),
      data_freshness_seconds: 5,
      pipeline_lag_seconds: 5,
      data_quality: 'ok',
      results: [],
    });
    vi.spyOn(superAdminService, 'getReplayCases').mockResolvedValue({
      generated_at: new Date().toISOString(),
      data_freshness_seconds: 5,
      pipeline_lag_seconds: 5,
      data_quality: 'ok',
      results: [
        {
          case_id: 'tenant_admin.dashboard_stats',
          label: 'Tenant Dashboard Stats',
          portal: 'TENANT_ADMIN',
          tab: 'dashboard',
          method: 'GET',
          endpoint: '/api/tenants/stats/',
          supports_params: false,
        },
      ],
    });
    vi.spyOn(superAdminService, 'getOpsErrors').mockResolvedValue({
      generated_at: new Date().toISOString(),
      data_freshness_seconds: 5,
      pipeline_lag_seconds: 5,
      data_quality: 'ok',
      results: [],
    });
    vi.spyOn(superAdminService, 'getOpsTenantTimeline').mockResolvedValue({
      generated_at: new Date().toISOString(),
      data_freshness_seconds: 5,
      pipeline_lag_seconds: 5,
      data_quality: 'ok',
      tenant_id: 'tenant-1',
      status_series: [],
      category_counts: [],
      events: [],
    });
    vi.spyOn(superAdminService, 'getOpsActionsCatalog').mockResolvedValue({
      results: [
        {
          key: 'recompute_tenant_analytics',
          label: 'Recompute Tenant Analytics',
          description: 'Warm analytics caches',
          risk: 'low',
          requires_approval: false,
          required_target_keys: [],
        },
      ],
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    queryClient.clear();
  });

  it('renders operations center sections', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <OperationsPage />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Operations Center/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/Problematic Errors/i)).toBeInTheDocument();
    expect(screen.getByText(/Replay Runner/i)).toBeInTheDocument();
    expect(screen.getByText(/Action Center/i)).toBeInTheDocument();
    expect(screen.getByText(/Tenant Timeline/i)).toBeInTheDocument();
  });
});

