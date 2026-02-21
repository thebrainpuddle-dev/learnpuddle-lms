import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ExclamationCircleIcon } from '@heroicons/react/24/outline';
import { superAdminService, type OpsIncident, type OpsTenantRow } from '../../services/superAdminService';
import { usePageTitle } from '../../hooks/usePageTitle';

const statusClasses: Record<string, string> = {
  HEALTHY: 'bg-emerald-100 text-emerald-700',
  DEGRADED: 'bg-amber-100 text-amber-700',
  DOWN: 'bg-red-100 text-red-700',
  MAINTENANCE: 'bg-slate-200 text-slate-700',
};

const qualityClasses: Record<string, string> = {
  ok: 'bg-emerald-100 text-emerald-700',
  degraded: 'bg-amber-100 text-amber-700',
  stale: 'bg-red-100 text-red-700',
};

function formatSeconds(value: number): string {
  if (value < 60) return `${value}s`;
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return `${minutes}m ${seconds}s`;
}

export const OperationsPage: React.FC = () => {
  usePageTitle('Operations');
  const queryClient = useQueryClient();
  const [search, setSearch] = React.useState('');

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ['opsOverview'],
    queryFn: superAdminService.getOpsOverview,
    refetchInterval: 10000,
  });

  const { data: tenantsData, isLoading: tenantsLoading } = useQuery({
    queryKey: ['opsTenants', search],
    queryFn: () => superAdminService.listOpsTenants({ search, page_size: 20 }),
    refetchInterval: 10000,
  });

  const { data: incidentsData } = useQuery({
    queryKey: ['opsIncidents'],
    queryFn: () => superAdminService.listOpsIncidents({ status: 'OPEN' }),
    refetchInterval: 10000,
  });

  const acknowledgeMutation = useMutation({
    mutationFn: (id: string) => superAdminService.acknowledgeIncident(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['opsOverview'] });
      queryClient.invalidateQueries({ queryKey: ['opsIncidents'] });
    },
  });

  const resolveMutation = useMutation({
    mutationFn: (id: string) => superAdminService.resolveIncident(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['opsOverview'] });
      queryClient.invalidateQueries({ queryKey: ['opsIncidents'] });
    },
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 sm:text-3xl">Operations</h1>
          <p className="mt-1 text-gray-500">Real-time tenant health, incidents, and pipeline quality.</p>
        </div>
        <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
          <div className="text-xs uppercase tracking-wide text-gray-500">Pipeline Quality</div>
          <div className="mt-2 flex items-center gap-2">
            <span className={`rounded-full px-2 py-1 text-xs font-medium ${qualityClasses[overview?.data_quality || 'stale']}`}>
              {overview?.data_quality || 'stale'}
            </span>
            <span className="text-xs text-gray-600">
              freshness {formatSeconds(overview?.data_freshness_seconds ?? 0)} | lag {formatSeconds(overview?.pipeline_lag_seconds ?? 0)}
            </span>
          </div>
        </div>
      </div>

      {overviewLoading ? (
        <div className="rounded-xl border border-gray-200 bg-white p-6 text-sm text-gray-500">Loading operations summary...</div>
      ) : (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <div className="text-xs uppercase text-gray-500">Tenants</div>
            <div className="mt-1 text-2xl font-semibold text-gray-900">{overview?.totals.tenants ?? 0}</div>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <div className="text-xs uppercase text-gray-500">Healthy</div>
            <div className="mt-1 text-2xl font-semibold text-emerald-700">{overview?.totals.healthy ?? 0}</div>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <div className="text-xs uppercase text-gray-500">Degraded</div>
            <div className="mt-1 text-2xl font-semibold text-amber-700">{overview?.totals.degraded ?? 0}</div>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <div className="text-xs uppercase text-gray-500">Down</div>
            <div className="mt-1 text-2xl font-semibold text-red-700">{overview?.totals.down ?? 0}</div>
          </div>
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <div className="text-xs uppercase text-gray-500">Maintenance</div>
            <div className="mt-1 text-2xl font-semibold text-slate-700">{overview?.totals.maintenance ?? 0}</div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <section className="rounded-xl border border-gray-200 bg-white">
          <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
            <h2 className="text-sm font-semibold text-gray-900">Open Incidents</h2>
            <span className="text-xs text-gray-500">{incidentsData?.results.length ?? 0} active</span>
          </div>
          <div className="max-h-[400px] overflow-y-auto">
            {!(incidentsData?.results.length) ? (
              <div className="px-4 py-6 text-sm text-gray-500">No open incidents.</div>
            ) : (
              incidentsData?.results.slice(0, 20).map((incident: OpsIncident) => (
                <div key={incident.id} className="border-b border-gray-100 px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className={`rounded px-2 py-0.5 text-xs font-medium ${incident.severity === 'P1' ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'}`}>
                          {incident.severity}
                        </span>
                        <span className="text-sm font-medium text-gray-900">{incident.title}</span>
                      </div>
                      <div className="mt-1 text-xs text-gray-500">
                        {incident.scope} {incident.tenant_name ? `| ${incident.tenant_name}` : ''} | {new Date(incident.started_at).toLocaleString()}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      {incident.status === 'OPEN' && (
                        <button
                          type="button"
                          onClick={() => acknowledgeMutation.mutate(incident.id)}
                          disabled={acknowledgeMutation.isPending}
                          className="rounded-md border border-gray-300 px-2 py-1 text-xs text-gray-700 hover:bg-gray-50 disabled:opacity-50"
                        >
                          Ack
                        </button>
                      )}
                      {incident.status !== 'RESOLVED' && (
                        <button
                          type="button"
                          onClick={() => resolveMutation.mutate(incident.id)}
                          disabled={resolveMutation.isPending}
                          className="rounded-md bg-slate-800 px-2 py-1 text-xs text-white hover:bg-slate-900 disabled:opacity-50"
                        >
                          Resolve
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>

        <section className="rounded-xl border border-gray-200 bg-white">
          <div className="flex flex-col gap-3 border-b border-gray-100 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-sm font-semibold text-gray-900">Tenant Health</h2>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search tenant..."
              className="w-full rounded-lg border border-gray-300 px-3 py-1.5 text-sm outline-none focus:border-indigo-500 sm:w-64"
            />
          </div>
          <div className="max-h-[400px] overflow-y-auto">
            {tenantsLoading ? (
              <div className="px-4 py-6 text-sm text-gray-500">Loading tenants...</div>
            ) : !(tenantsData?.results.length) ? (
              <div className="px-4 py-6 text-sm text-gray-500">No tenants found.</div>
            ) : (
              tenantsData?.results.map((tenant: OpsTenantRow) => (
                <div key={tenant.tenant_id} className="border-b border-gray-100 px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-gray-900">{tenant.name}</span>
                        <span className={`rounded px-2 py-0.5 text-xs font-medium ${statusClasses[tenant.status] || 'bg-gray-100 text-gray-700'}`}>
                          {tenant.status}
                        </span>
                        {tenant.active_failures_24h > 0 && (
                          <span className="inline-flex items-center gap-1 rounded bg-red-50 px-2 py-0.5 text-xs text-red-700">
                            <ExclamationCircleIcon className="h-3 w-3" />
                            {tenant.active_failures_24h} active
                          </span>
                        )}
                      </div>
                      <div className="mt-1 text-xs text-gray-500">
                        {tenant.subdomain} | last check {tenant.last_check_at ? new Date(tenant.last_check_at).toLocaleTimeString() : 'n/a'} | latency {tenant.last_latency_ms ?? '-'}ms
                      </div>
                    </div>
                    <div className="text-right text-xs text-gray-500">
                      <div>weekly failures</div>
                      <div className="font-semibold text-gray-800">
                        {Object.values(tenant.failures_week || {}).reduce((acc, value) => acc + value, 0)}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
};
