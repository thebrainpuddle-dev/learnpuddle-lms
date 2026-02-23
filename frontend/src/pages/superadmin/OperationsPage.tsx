import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  superAdminService,
  type OpsReplayRun,
  type OpsReplayStep,
  type OpsRouteError,
} from '../../services/superAdminService';
import { usePageTitle } from '../../hooks/usePageTitle';
import { ErrorTable } from '../../components/superadmin/ops/ErrorTable';
import { ReplayRunner } from '../../components/superadmin/ops/ReplayRunner';
import { ActionCenter } from '../../components/superadmin/ops/ActionCenter';
import { IncidentDrawer } from '../../components/superadmin/ops/IncidentDrawer';
import { TenantTimelineStrip } from '../../components/superadmin/ops/TenantTimelineStrip';

type TimeRangeOption = '24h' | '7d';

function toIsoFromRange(range: TimeRangeOption): string {
  const now = Date.now();
  const hours = range === '24h' ? 24 : 24 * 7;
  return new Date(now - hours * 60 * 60 * 1000).toISOString();
}

function inferReplayCase(error: OpsRouteError): string {
  if (error.portal === 'TEACHER') {
    if (error.tab_key.includes('quiz')) return 'teacher.quiz_detail';
    if (error.tab_key.includes('assignment')) return 'teacher.assignments_list';
    if (error.tab_key.includes('course')) return 'teacher.course_detail';
    return 'teacher.dashboard';
  }

  if (error.tab_key.includes('assignment')) return 'tenant_admin.assignments_list';
  if (error.tab_key.includes('course_editor')) return 'tenant_admin.module_create';
  if (error.tab_key.includes('courses')) return 'tenant_admin.courses_list';
  if (error.tab_key.includes('media')) return 'tenant_admin.media_list';
  if (error.tab_key.includes('reminder')) return 'tenant_admin.reminders_list';
  if (error.tab_key.includes('report')) return 'tenant_admin.reports_course_progress';
  return 'tenant_admin.dashboard_stats';
}

export const OperationsPage: React.FC = () => {
  usePageTitle('Operations Center');
  const queryClient = useQueryClient();

  const [search, setSearch] = React.useState('');
  const [timeRange, setTimeRange] = React.useState<TimeRangeOption>('24h');
  const [selectedTenantId, setSelectedTenantId] = React.useState('');
  const [portal, setPortal] = React.useState<'TENANT_ADMIN' | 'TEACHER'>('TENANT_ADMIN');
  const [selectedErrorId, setSelectedErrorId] = React.useState<string | null>(null);
  const [lockingId, setLockingId] = React.useState<string | null>(null);
  const [run, setRun] = React.useState<OpsReplayRun | null>(null);
  const [steps, setSteps] = React.useState<OpsReplayStep[]>([]);
  const [actionResult, setActionResult] = React.useState<Record<string, any> | null>(null);
  const [pendingApprovalActionId, setPendingApprovalActionId] = React.useState<string | null>(null);

  const since = React.useMemo(() => toIsoFromRange(timeRange), [timeRange]);

  const { data: overview } = useQuery({
    queryKey: ['opsOverview'],
    queryFn: superAdminService.getOpsOverview,
    refetchInterval: 10000,
  });

  const { data: tenantsData, isLoading: tenantsLoading } = useQuery({
    queryKey: ['opsTenants', search],
    queryFn: () => superAdminService.listOpsTenants({ search, page_size: 50 }),
    refetchInterval: 15000,
  });

  React.useEffect(() => {
    if (!selectedTenantId && tenantsData?.results?.length) {
      setSelectedTenantId(tenantsData.results[0].tenant_id);
    }
  }, [selectedTenantId, tenantsData]);

  const selectedTenant = React.useMemo(
    () => tenantsData?.results.find((row) => row.tenant_id === selectedTenantId),
    [tenantsData, selectedTenantId],
  );

  const { data: incidentsData } = useQuery({
    queryKey: ['opsIncidents'],
    queryFn: () => superAdminService.listOpsIncidents({ status: 'OPEN' }),
    refetchInterval: 10000,
  });

  const { data: replayCasesData } = useQuery({
    queryKey: ['opsReplayCases', portal],
    queryFn: () => superAdminService.getReplayCases({ portal }),
  });

  const { data: errorsData, isLoading: errorsLoading } = useQuery({
    queryKey: ['opsErrors', selectedTenantId, portal, since],
    queryFn: () =>
      superAdminService.getOpsErrors({
        tenant_id: selectedTenantId || undefined,
        portal,
        status_codes: '500,429',
        since,
      }),
    enabled: Boolean(selectedTenantId),
    refetchInterval: 10000,
  });

  const { data: timelineData, isLoading: timelineLoading } = useQuery({
    queryKey: ['opsTimeline', selectedTenantId, since],
    queryFn: () =>
      superAdminService.getOpsTenantTimeline(selectedTenantId, {
        from: since,
        to: new Date().toISOString(),
      }),
    enabled: Boolean(selectedTenantId),
    refetchInterval: 15000,
  });

  const { data: actionsCatalog } = useQuery({
    queryKey: ['opsActionsCatalog'],
    queryFn: superAdminService.getOpsActionsCatalog,
  });

  const { data: selectedErrorDetail, isLoading: selectedErrorLoading } = useQuery({
    queryKey: ['opsErrorDetail', selectedErrorId],
    queryFn: () => superAdminService.getOpsErrorDetail(String(selectedErrorId)),
    enabled: Boolean(selectedErrorId),
  });

  const runMutation = useMutation({
    mutationFn: (payload: {
      tenant_id: string;
      portal: 'TENANT_ADMIN' | 'TEACHER';
      cases: Array<{ case_id: string; params?: Record<string, any> }>;
      dry_run: boolean;
      priority: 'NORMAL' | 'HIGH';
    }) => superAdminService.createReplayRun(payload),
    onSuccess: async (runResponse) => {
      setRun(runResponse);
      if (runResponse.id) {
        const stepsRes = await superAdminService.getReplayRunSteps(runResponse.id);
        setSteps(stepsRes.results);
      }
      queryClient.invalidateQueries({ queryKey: ['opsErrors'] });
      queryClient.invalidateQueries({ queryKey: ['opsIncidents'] });
      queryClient.invalidateQueries({ queryKey: ['opsTimeline'] });
    },
  });

  const lockMutation = useMutation({
    mutationFn: ({ errorGroupId, note }: { errorGroupId: string; note?: string }) =>
      superAdminService.lockOpsError(errorGroupId, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['opsErrors'] });
      queryClient.invalidateQueries({ queryKey: ['opsIncidents'] });
    },
  });

  const executeActionMutation = useMutation({
    mutationFn: (payload: {
      tenant_id: string;
      action_key: string;
      target?: Record<string, any>;
      reason?: string;
      dry_run?: boolean;
    }) => superAdminService.executeOpsAction(payload),
    onSuccess: (result) => {
      setActionResult(result as Record<string, any>);
      if (result.requires_approval && result.action_log_id) {
        setPendingApprovalActionId(result.action_log_id);
      } else {
        setPendingApprovalActionId(null);
      }
      queryClient.invalidateQueries({ queryKey: ['opsTimeline'] });
    },
  });

  const approveActionMutation = useMutation({
    mutationFn: (actionId: string) =>
      superAdminService.approveOpsAction(actionId, 'Approved from Operations Center'),
    onSuccess: (result) => {
      setActionResult(result as Record<string, any>);
      setPendingApprovalActionId(null);
      queryClient.invalidateQueries({ queryKey: ['opsTimeline'] });
      queryClient.invalidateQueries({ queryKey: ['opsErrors'] });
    },
  });

  const activeErrors = errorsData?.results || [];
  const errors500 = activeErrors.filter((row) => row.status_code === 500).length;
  const errors429 = activeErrors.filter((row) => row.status_code === 429).length;

  return (
    <div className="space-y-4 sm:space-y-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 sm:text-3xl">Operations Center</h1>
          <p className="mt-1 text-gray-500">
            Production retest, error lock, and guarded unblock actions without tenant impersonation.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search tenant..."
            className="w-52 rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
          />
          <select
            value={selectedTenantId}
            onChange={(e) => setSelectedTenantId(e.target.value)}
            className="w-64 rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
            disabled={tenantsLoading}
          >
            {tenantsData?.results.map((tenant) => (
              <option key={tenant.tenant_id} value={tenant.tenant_id}>
                {tenant.name} ({tenant.subdomain})
              </option>
            ))}
          </select>
          <select
            value={portal}
            onChange={(e) => setPortal(e.target.value as 'TENANT_ADMIN' | 'TEACHER')}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="TENANT_ADMIN">Tenant Admin</option>
            <option value="TEACHER">Teacher</option>
          </select>
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value as TimeRangeOption)}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm"
          >
            <option value="24h">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs uppercase text-gray-500">Open Incidents</div>
          <div className="mt-1 text-2xl font-semibold text-gray-900">{incidentsData?.results.length ?? 0}</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs uppercase text-gray-500">Active 500 Groups</div>
          <div className="mt-1 text-2xl font-semibold text-red-700">{errors500}</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs uppercase text-gray-500">Active 429 Groups</div>
          <div className="mt-1 text-2xl font-semibold text-amber-700">{errors429}</div>
        </div>
        <div className="rounded-xl border border-gray-200 bg-white p-4">
          <div className="text-xs uppercase text-gray-500">Health Score</div>
          <div className="mt-1 text-2xl font-semibold text-indigo-700">{overview?.totals.healthy ?? 0}</div>
          <div className="text-xs text-gray-500">healthy tenants</div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <div className="xl:col-span-5">
          <ErrorTable
            errors={activeErrors}
            loading={errorsLoading}
            lockingId={lockingId}
            onSelect={(error) => setSelectedErrorId(error.id)}
            onReplay={(error) => {
              const caseId = inferReplayCase(error);
              const selectedPortal = error.portal === 'TEACHER' ? 'TEACHER' : 'TENANT_ADMIN';
              setPortal(selectedPortal);
              if (!selectedTenantId) return;
              runMutation.mutate({
                tenant_id: selectedTenantId,
                portal: selectedPortal,
                cases: [{ case_id: caseId, params: {} }],
                dry_run: true,
                priority: 'HIGH',
              });
            }}
            onLock={(errorGroupId) => {
              setLockingId(errorGroupId);
              lockMutation.mutate(
                { errorGroupId, note: 'Locked from Operations Center for focused mitigation.' },
                { onSettled: () => setLockingId(null) },
              );
            }}
          />
        </div>

        <div className="xl:col-span-4">
          <ReplayRunner
            tenantId={selectedTenantId}
            portal={portal}
            cases={replayCasesData?.results || []}
            run={run}
            steps={steps}
            running={runMutation.isPending}
            onPortalChange={setPortal}
            onRun={({ tenantId, portal: selectedPortal, caseIds, dryRun, priority, params }) => {
              runMutation.mutate({
                tenant_id: tenantId,
                portal: selectedPortal,
                cases: caseIds.map((caseId) => ({ case_id: caseId, params })),
                dry_run: dryRun,
                priority,
              });
            }}
          />
        </div>

        <div className="xl:col-span-3 space-y-3">
          <ActionCenter
            tenantId={selectedTenantId}
            actions={actionsCatalog?.results || []}
            executing={executeActionMutation.isPending}
            onExecute={({ tenantId, actionKey, dryRun, reason, target }) =>
              executeActionMutation.mutate({
                tenant_id: tenantId,
                action_key: actionKey,
                dry_run: dryRun,
                reason,
                target,
              })
            }
            lastResult={actionResult}
          />
          {pendingApprovalActionId && (
            <button
              type="button"
              onClick={() => approveActionMutation.mutate(pendingApprovalActionId)}
              disabled={approveActionMutation.isPending}
              className="w-full rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-50"
            >
              {approveActionMutation.isPending ? 'Approving...' : 'Approve Pending Action'}
            </button>
          )}
        </div>
      </div>

      <TenantTimelineStrip
        loading={timelineLoading}
        tenantName={selectedTenant?.name}
        events={timelineData?.events || []}
      />

      <IncidentDrawer
        open={Boolean(selectedErrorId)}
        loading={selectedErrorLoading}
        detail={selectedErrorDetail || null}
        onClose={() => setSelectedErrorId(null)}
      />
    </div>
  );
};

