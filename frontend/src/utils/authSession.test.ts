import {
  buildLoginRedirectUrl,
  clearAuthArtifacts,
  SESSION_LAST_ACTIVITY_KEY,
} from './authSession';

describe('authSession utilities', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('clearAuthArtifacts removes last-activity marker', () => {
    localStorage.setItem(SESSION_LAST_ACTIVITY_KEY, String(Date.now()));
    localStorage.setItem('access_token', 'a');
    sessionStorage.setItem('refresh_token', 'r');

    clearAuthArtifacts();

    expect(localStorage.getItem(SESSION_LAST_ACTIVITY_KEY)).toBeNull();
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(sessionStorage.getItem('refresh_token')).toBeNull();
  });

  it('buildLoginRedirectUrl appends reason for session expiration states', () => {
    expect(buildLoginRedirectUrl('idle_timeout', '/admin/dashboard')).toBe('/login?reason=idle_timeout');
    expect(buildLoginRedirectUrl('session_expired', '/teacher/dashboard')).toBe('/login?reason=session_expired');
    expect(buildLoginRedirectUrl('tenant_access_denied', '/admin/courses')).toBe('/login?reason=tenant_access_denied');
  });
});
