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
] as const;

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

  async impersonate(tenantId: string) {
    const res = await api.post(`/super-admin/tenants/${tenantId}/impersonate/`);
    return res.data as { tokens: { access: string; refresh: string }; user_email: string; tenant_subdomain: string };
  },
};
