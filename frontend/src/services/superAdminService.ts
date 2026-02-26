import api from '../config/api';

export interface PlatformStats {
  total_tenants: number;
  active_tenants: number;
  trial_tenants: number;
  total_users: number;
  total_teachers: number;
  plan_distribution?: Record<string, number>;
  recent_onboards?: Array<{ id: string; name: string; subdomain: string; created_at: string }>;
  schools_near_limits?: Array<{ id: string; name: string; resource: string; used: number; limit: number }>;
}

export interface TenantListItem {
  id: string;
  name: string;
  slug: string;
  subdomain: string;
  email: string;
  is_active: boolean;
  is_trial: boolean;
  trial_end_date: string | null;
  plan: string;
  plan_started_at: string | null;
  plan_expires_at: string | null;
  max_teachers: number;
  max_courses: number;
  max_storage_mb: number;
  primary_color: string;
  logo: string | null;
  teacher_count: number;
  admin_count: number;
  course_count: number;
  created_at: string;
  updated_at: string;
}

export interface TenantDetail extends TenantListItem {
  phone: string;
  address: string;
  secondary_color: string;
  font_family: string;
  max_video_duration_minutes: number;
  feature_video_upload: boolean;
  feature_auto_quiz: boolean;
  feature_transcripts: boolean;
  feature_reminders: boolean;
  feature_custom_branding: boolean;
  feature_reports_export: boolean;
  feature_groups: boolean;
  feature_certificates: boolean;
  feature_teacher_authoring?: boolean;
  internal_notes: string;
  published_course_count: number;
  admin_email: string | null;
  admin_name: string | null;
}

export interface TenantUsage {
  teachers: { used: number; limit: number };
  courses: { used: number; limit: number };
  storage_mb: { used: number; limit: number };
}

export type OpsDataQuality = 'ok' | 'degraded' | 'stale';

export interface OpsReadMeta {
  generated_at: string;
  data_freshness_seconds: number;
  pipeline_lag_seconds: number;
  data_quality: OpsDataQuality;
}

export interface OpsOverview extends OpsReadMeta {
  refresh_seconds: number;
  totals: {
    tenants: number;
    healthy: number;
    degraded: number;
    down: number;
    maintenance: number;
  };
  mttr_targets: {
    p1_minutes: number;
    p2_minutes: number;
  };
  open_incidents: Array<{
    id: string;
    severity: 'P1' | 'P2';
    status: 'OPEN' | 'ACKED' | 'RESOLVED';
    title: string;
    started_at: string;
    tenant_id: string | null;
    tenant_name: string | null;
    owner_email: string | null;
    scope: 'GLOBAL' | 'TENANT';
  }>;
  top_failure_categories: Array<{
    category: string;
    count: number;
  }>;
}

export interface OpsTenantRow {
  tenant_id: string;
  name: string;
  subdomain: string;
  status: 'HEALTHY' | 'DEGRADED' | 'DOWN' | 'MAINTENANCE';
  last_check_at: string | null;
  last_latency_ms: number | null;
  active_failures_24h: number;
  failures_week: Record<string, number>;
  maintenance_mode: boolean;
}

export interface OpsTenantsResponse extends OpsReadMeta {
  count: number;
  next: string | null;
  previous: string | null;
  results: OpsTenantRow[];
}

export interface OpsIncident {
  id: string;
  severity: 'P1' | 'P2';
  scope: 'GLOBAL' | 'TENANT';
  status: 'OPEN' | 'ACKED' | 'RESOLVED';
  rule_id: string;
  title: string;
  description: string;
  tenant_id: string | null;
  tenant_name: string | null;
  owner_email: string | null;
  started_at: string;
  acknowledged_at: string | null;
  resolved_at: string | null;
  mttr_seconds: number | null;
  last_seen_at: string;
  metadata: Record<string, any>;
}

export interface OpsIncidentsResponse extends OpsReadMeta {
  results: OpsIncident[];
}

export interface OpsReplayCase {
  case_id: string;
  label: string;
  portal: 'TENANT_ADMIN' | 'TEACHER';
  tab: string;
  method: string;
  endpoint: string;
  supports_params: boolean;
  payload_defaults?: Record<string, any>;
  query_defaults?: Record<string, any>;
}

export interface OpsReplayRun {
  id: string;
  tenant_id: string;
  tenant_name: string;
  portal: 'TENANT_ADMIN' | 'TEACHER';
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  priority: 'NORMAL' | 'HIGH';
  dry_run: boolean;
  requested_cases: Array<string | { case_id: string; params?: Record<string, any> }>;
  summary: Record<string, any>;
  incident_links: string[];
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  actor_email: string | null;
  queued?: boolean;
}

export interface OpsReplayStep {
  id: string;
  run_id: string;
  case_id: string;
  case_label: string;
  endpoint: string;
  method: string;
  request_payload: Record<string, any>;
  response_status: number | null;
  response_excerpt: string;
  latency_ms: number | null;
  pass_fail: boolean;
  error_group_id: string | null;
  created_at: string;
}

export interface OpsRouteError {
  id: string;
  tenant_id: string | null;
  tenant_name: string | null;
  portal: 'SUPER_ADMIN' | 'TENANT_ADMIN' | 'TEACHER' | 'UNKNOWN';
  tab_key: string;
  route_path: string;
  component_name: string;
  endpoint: string;
  method: string;
  status_code: number;
  fingerprint: string;
  first_seen_at: string;
  last_seen_at: string;
  last_request_id: string;
  total_count: number;
  count_1h: number;
  count_24h: number;
  sample_payload: Record<string, any>;
  sample_response_excerpt: string;
  sample_error_message: string;
  is_locked: boolean;
  locked_at: string | null;
  locked_by: string | null;
}

export interface OpsActionCatalogItem {
  key: string;
  label: string;
  description: string;
  risk: 'low' | 'medium' | 'high';
  requires_approval: boolean;
  required_target_keys: string[];
}

export interface OnboardPayload {
  school_name: string;
  admin_email: string;
  admin_first_name: string;
  admin_last_name: string;
  admin_password: string;
  subdomain?: string;
}

export const PLAN_OPTIONS = ['FREE', 'STARTER', 'PRO', 'ENTERPRISE'] as const;

export const FEATURE_FLAGS = [
  { key: 'feature_video_upload', label: 'Video Upload' },
  { key: 'feature_auto_quiz', label: 'Auto Quiz Generation' },
  { key: 'feature_transcripts', label: 'Transcripts' },
  { key: 'feature_reminders', label: 'Reminders' },
  { key: 'feature_custom_branding', label: 'Custom Branding' },
  { key: 'feature_reports_export', label: 'Reports Export' },
  { key: 'feature_groups', label: 'Groups' },
  { key: 'feature_certificates', label: 'Certificates' },
  { key: 'feature_teacher_authoring', label: 'Teacher Authoring' },
] as const;

export interface DemoBooking {
  id: string;
  name: string;
  email: string;
  company: string;
  phone: string;
  source: 'cal_webhook' | 'manual';
  cal_event_id: string;
  scheduled_at: string | null;
  notes: string;
  status: 'scheduled' | 'completed' | 'cancelled' | 'no_show';
  followup_sent_at: string | null;
  created_at: string;
  created_by: string | null;
}

export const superAdminService = {
  async getStats(): Promise<PlatformStats> {
    const res = await api.get('/super-admin/stats/');
    return res.data;
  },

  async listTenants(params?: { search?: string; is_active?: boolean; is_trial?: boolean; page?: number }) {
    const res = await api.get('/super-admin/tenants/', { params });
    return res.data as { count: number; results: TenantListItem[] };
  },

  async getTenant(id: string): Promise<TenantDetail> {
    const res = await api.get(`/super-admin/tenants/${id}/`);
    return res.data;
  },

  async updateTenant(id: string, data: Record<string, any>) {
    const res = await api.patch(`/super-admin/tenants/${id}/`, data);
    return res.data;
  },

  async getTenantUsage(id: string): Promise<TenantUsage> {
    const res = await api.get(`/super-admin/tenants/${id}/usage/`);
    return res.data;
  },

  async applyPlan(id: string, plan: string, overrides?: Record<string, any>) {
    const res = await api.post(`/super-admin/tenants/${id}/apply-plan/`, { plan, ...overrides });
    return res.data;
  },

  async resetAdminPassword(id: string, newPassword?: string) {
    const res = await api.post(`/super-admin/tenants/${id}/reset-admin-password/`, { new_password: newPassword });
    return res.data as { message: string; email: string };
  },

  async onboardSchool(data: OnboardPayload) {
    const res = await api.post('/super-admin/tenants/', data);
    return res.data as { tenant: TenantListItem; admin_email: string; subdomain: string };
  },

  async sendEmail(tenantId: string, data: { to?: string; subject: string; body: string }) {
    const res = await api.post(`/super-admin/tenants/${tenantId}/send-email/`, data);
    return res.data as { sent: boolean; to: string; subject: string };
  },

  async bulkSendEmail(data: { tenant_ids: string[]; subject: string; body: string }) {
    const res = await api.post('/super-admin/bulk-email/', data);
    return res.data as { queued: number; skipped: Array<{ tenant_id: string; reason: string }> };
  },

  async listDemoBookings(params?: { search?: string; status?: string; page?: number }) {
    const res = await api.get('/super-admin/demo-bookings/', { params });
    return res.data as { count: number; results: DemoBooking[] };
  },

  async createDemoBooking(data: { name: string; email: string; scheduled_at: string; company?: string; phone?: string; notes?: string }) {
    const res = await api.post('/super-admin/demo-bookings/', data);
    return res.data as DemoBooking;
  },

  async updateDemoBooking(id: string, data: Partial<DemoBooking>) {
    const res = await api.patch(`/super-admin/demo-bookings/${id}/`, data);
    return res.data as DemoBooking;
  },

  async deleteDemoBooking(id: string) {
    const res = await api.delete(`/super-admin/demo-bookings/${id}/`);
    return res.data;
  },

  async sendDemoBookingEmail(id: string, data: { subject: string; body: string }) {
    const res = await api.post(`/super-admin/demo-bookings/${id}/send-email/`, data);
    return res.data as { sent: boolean; to: string };
  },

  async impersonate(tenantId: string) {
    const res = await api.post(`/super-admin/tenants/${tenantId}/impersonate/`);
    return res.data as { tokens: { access: string; refresh: string }; user_email: string; tenant_subdomain: string };
  },

  async getOpsOverview(): Promise<OpsOverview> {
    const res = await api.get('/super-admin/ops/overview/');
    return res.data;
  },

  async listOpsTenants(params?: { search?: string; status?: string; category?: string; page?: number; page_size?: number }) {
    const res = await api.get('/super-admin/ops/tenants/', { params });
    return res.data as OpsTenantsResponse;
  },

  async getOpsTenantTimeline(tenantId: string, params?: { from?: string; to?: string }) {
    const res = await api.get(`/super-admin/ops/tenants/${tenantId}/timeline/`, { params });
    return res.data as OpsReadMeta & {
      tenant_id: string;
      status_series: Array<{ ts: string; status: string; latency_ms?: number }>;
      category_counts: Array<Record<string, any>>;
      events: Array<{
        ts: string;
        category: string;
        severity: string;
        status: string;
        message: string;
        payload: Record<string, any>;
      }>;
    };
  },

  async listOpsIncidents(params?: { status?: string; severity?: string }) {
    const res = await api.get('/super-admin/ops/incidents/', { params });
    return res.data as OpsIncidentsResponse;
  },

  async acknowledgeIncident(id: string) {
    const res = await api.post(`/super-admin/ops/incidents/${id}/acknowledge/`);
    return res.data as { ok: boolean };
  },

  async resolveIncident(id: string) {
    const res = await api.post(`/super-admin/ops/incidents/${id}/resolve/`);
    return res.data as { ok: boolean };
  },

  async getReplayCases(params?: { portal?: 'TENANT_ADMIN' | 'TEACHER' }) {
    const res = await api.get('/super-admin/ops/replay-cases/', { params });
    return res.data as OpsReadMeta & { results: OpsReplayCase[] };
  },

  async createReplayRun(data: {
    tenant_id: string;
    portal: 'TENANT_ADMIN' | 'TEACHER';
    cases: Array<string | { case_id: string; params?: Record<string, any> }>;
    dry_run: boolean;
    priority?: 'NORMAL' | 'HIGH';
    async?: boolean;
  }) {
    const normalizedCases = data.cases.map((entry) => (typeof entry === 'string' ? { case_id: entry } : entry));
    const res = await api.post('/super-admin/ops/replay-runs/', { ...data, cases: normalizedCases });
    return res.data as OpsReplayRun;
  },

  async getReplayRun(runId: string) {
    const res = await api.get(`/super-admin/ops/replay-runs/${runId}/`);
    return res.data as OpsReplayRun;
  },

  async getReplayRunSteps(runId: string) {
    const res = await api.get(`/super-admin/ops/replay-runs/${runId}/steps/`);
    return res.data as { run_id: string; results: OpsReplayStep[] };
  },

  async cancelReplayRun(runId: string) {
    const res = await api.post(`/super-admin/ops/replay-runs/${runId}/cancel/`);
    return res.data as { ok: boolean; status: string };
  },

  async getOpsErrors(params?: {
    tenant_id?: string;
    status_codes?: string;
    portal?: string;
    tab?: string;
    since?: string;
    until?: string;
    is_locked?: boolean;
  }) {
    const res = await api.get('/super-admin/ops/errors/', { params });
    return res.data as OpsReadMeta & { results: OpsRouteError[] };
  },

  async getOpsErrorDetail(errorGroupId: string) {
    const res = await api.get(`/super-admin/ops/errors/${errorGroupId}/`);
    return res.data as {
      error_group: OpsRouteError;
      recent_replay_steps: Array<{
        id: string;
        run_id: string;
        run_status: string;
        case_id: string;
        response_status: number | null;
        created_at: string;
      }>;
    };
  },

  async lockOpsError(errorGroupId: string, note?: string) {
    const res = await api.post(`/super-admin/ops/errors/${errorGroupId}/lock/`, { note });
    return res.data as { ok: boolean; error_group_id: string; incident_id: string; incident_status: string };
  },

  async getOpsActionsCatalog() {
    const res = await api.get('/super-admin/ops/actions/catalog/');
    return res.data as { results: OpsActionCatalogItem[] };
  },

  async executeOpsAction(data: {
    tenant_id: string;
    action_key: string;
    target?: Record<string, any>;
    reason?: string;
    dry_run?: boolean;
  }) {
    const res = await api.post('/super-admin/ops/actions/execute/', {
      ...data,
      target: data.target || {},
      dry_run: data.dry_run ?? true,
    });
    return res.data as {
      requires_approval: boolean;
      action_log_id: string;
      approval_id?: string;
      status: string;
      result?: Record<string, any>;
    };
  },

  async approveOpsAction(actionId: string, approval_note?: string) {
    const res = await api.post(`/super-admin/ops/actions/${actionId}/approve/`, { approval_note });
    return res.data as { action_log_id: string; status: string; result: Record<string, any> };
  },
};
