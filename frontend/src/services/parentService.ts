import api from '../config/api';
import type {
  ParentChild,
  ParentChildOverview,
  ParentAuthResponse,
} from '../types/parent';

// Parent API uses a custom auth scheme, not JWT
function parentHeaders(): Record<string, string> {
  const token = sessionStorage.getItem('parent_session_token');
  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = `ParentToken ${token}`;
  }
  // Add tenant subdomain for local dev
  const hostname = window.location.hostname;
  if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.endsWith('.localhost')) {
    const subdomain =
      sessionStorage.getItem('tenant_subdomain') ||
      localStorage.getItem('tenant_subdomain');
    if (subdomain) {
      headers['X-Tenant-Subdomain'] = subdomain;
    }
  }
  return headers;
}

export const parentService = {
  async requestMagicLink(email: string): Promise<{ message: string }> {
    const res = await api.post('/v1/parent/auth/request-link/', { email });
    return res.data;
  },

  async verifyToken(token: string): Promise<ParentAuthResponse> {
    const res = await api.post('/v1/parent/auth/verify/', { token });
    return res.data;
  },

  async demoLogin(email: string): Promise<ParentAuthResponse> {
    const res = await api.post('/v1/parent/auth/demo-login/', { email });
    return res.data;
  },

  async refreshSession(
    refreshToken: string,
  ): Promise<{ session_token: string; refresh_token: string; expires_at: string }> {
    const res = await api.post('/v1/parent/auth/refresh/', {
      refresh_token: refreshToken,
    });
    return res.data;
  },

  async logout(): Promise<void> {
    await api.post('/v1/parent/auth/logout/', {}, { headers: parentHeaders() });
  },

  async getChildren(): Promise<ParentChild[]> {
    const res = await api.get('/v1/parent/children/', {
      headers: parentHeaders(),
    });
    return res.data;
  },

  async getChildOverview(childId: string): Promise<ParentChildOverview> {
    const res = await api.get(`/v1/parent/children/${childId}/overview/`, {
      headers: parentHeaders(),
    });
    return res.data;
  },
};
