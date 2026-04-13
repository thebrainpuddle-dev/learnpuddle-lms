import api from '../config/api';

// ── Types matching backend serializers ──────────────────────────────

export interface CertificationType {
  id: string;
  name: string;
  description: string;
  validity_months: number;
  auto_renew: boolean;
  required_course_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface CertificationTypeCreateData {
  name: string;
  description?: string;
  validity_months: number;
  auto_renew?: boolean;
  required_course_ids?: string[];
}

export interface TeacherCertification {
  id: string;
  teacher: string;
  certification_type: string;
  certification_name: string;
  teacher_name: string;
  teacher_email: string;
  issued_at: string;
  expires_at: string;
  status: 'active' | 'expired' | 'revoked' | 'pending_renewal';
  certificate_file: string | null;
  is_expired: boolean;
  days_until_expiry: number;
  issued_by: string | null;
  issued_by_name: string | null;
  revoked_reason: string;
  renewal_count: number;
  created_at: string;
  updated_at: string;
}

export interface IssueCertificationData {
  teacher_id: string;
  certification_type_id: string;
  expires_at?: string;
}

export interface ExpiryCheckItem {
  id: string;
  teacher_name: string;
  teacher_email: string;
  certification_name: string;
  expires_at: string;
  days_until_expiry?: number;
  days_since_expiry?: number;
}

export interface ExpiryCheckResult {
  expiring_soon: ExpiryCheckItem[];
  already_expired: ExpiryCheckItem[];
  threshold_days: number;
}

// ── API service ─────────────────────────────────────────────────────

export const certificationsService = {
  // CertificationType CRUD
  types: {
    async list(): Promise<CertificationType[]> {
      const res = await api.get('/certifications/types/');
      return res.data.results ?? res.data;
    },
    async create(data: CertificationTypeCreateData): Promise<CertificationType> {
      const res = await api.post('/certifications/types/create/', data);
      return res.data;
    },
    async update(id: string, data: Partial<CertificationTypeCreateData>): Promise<CertificationType> {
      const res = await api.patch(`/certifications/types/${id}/update/`, data);
      return res.data;
    },
    async delete(id: string): Promise<void> {
      await api.delete(`/certifications/types/${id}/delete/`);
    },
  },

  // TeacherCertification management
  async list(params?: { teacher_id?: string; status?: string; certification_type_id?: string }): Promise<TeacherCertification[]> {
    const res = await api.get('/certifications/', { params });
    return res.data.results ?? res.data;
  },

  async issue(data: IssueCertificationData): Promise<TeacherCertification> {
    const res = await api.post('/certifications/issue/', data);
    return res.data;
  },

  async revoke(id: string, reason?: string): Promise<TeacherCertification> {
    const res = await api.post(`/certifications/${id}/revoke/`, { reason });
    return res.data;
  },

  async renew(id: string): Promise<TeacherCertification> {
    const res = await api.post(`/certifications/${id}/renew/`);
    return res.data;
  },

  async expiryCheck(days?: number): Promise<ExpiryCheckResult> {
    const res = await api.post('/certifications/expiry-check/', { days: days ?? 30 });
    return res.data;
  },
};
