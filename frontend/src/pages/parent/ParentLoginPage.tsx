// src/pages/parent/ParentLoginPage.tsx
//
// Clean, minimal login page for parent portal.
// Parents authenticate via magic link (email-based, passwordless).
// In development mode, a demo login button is available.

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Mail, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import { useTenantStore } from '../../stores/tenantStore';
import { useParentStore } from '../../stores/parentStore';
import { parentService } from '../../services/parentService';
import { cn } from '../../lib/utils';

const IS_DEV = import.meta.env.DEV;
const DEMO_PARENT_EMAIL = 'parent@keystoneeducation.in';

export function ParentLoginPage() {
  const { theme } = useTenantStore();
  const { setSession } = useParentStore();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error' | 'demo-loading'>('idle');
  const [errorMessage, setErrorMessage] = useState('');

  const tenantName = theme?.name || 'LearnPuddle';
  const tenantInitial = tenantName.charAt(0).toUpperCase();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;

    setStatus('loading');
    setErrorMessage('');

    try {
      await parentService.requestMagicLink(email.trim());
      // Store email for verify page to use after redirect
      sessionStorage.setItem('parent_email', email.trim());
      setStatus('success');
    } catch (err: unknown) {
      setStatus('error');
      const message =
        (err as { response?: { data?: { detail?: string; error?: string } } })?.response
          ?.data?.detail ||
        (err as { response?: { data?: { detail?: string; error?: string } } })?.response
          ?.data?.error ||
        'Failed to send login link. Please try again.';
      setErrorMessage(message);
    }
  }

  async function handleDemoLogin() {
    setStatus('demo-loading');
    setErrorMessage('');

    try {
      const data = await parentService.demoLogin(DEMO_PARENT_EMAIL);

      setSession({
        session_token: data.session_token,
        refresh_token: data.refresh_token,
        expires_at: data.expires_at,
        children: data.children,
        email: data.parent_email || DEMO_PARENT_EMAIL,
      });

      navigate('/parent/dashboard', { replace: true });
    } catch (err: unknown) {
      setStatus('error');
      const message =
        (err as { response?: { data?: { detail?: string; error?: string } } })?.response
          ?.data?.detail ||
        (err as { response?: { data?: { detail?: string; error?: string } } })?.response
          ?.data?.error ||
        'Demo login failed. Make sure seed data is loaded.';
      setErrorMessage(message);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-xl border border-gray-100 p-8">
          {/* Branding */}
          <div className="text-center mb-8">
            {theme?.logo ? (
              <img
                src={theme.logo}
                alt={tenantName}
                className="h-12 w-12 rounded-full mx-auto mb-3 object-cover"
              />
            ) : (
              <div className="h-12 w-12 rounded-full bg-gradient-to-br from-indigo-600 to-indigo-500 flex items-center justify-center mx-auto mb-3 shadow-sm">
                <span className="text-white font-bold text-lg">{tenantInitial}</span>
              </div>
            )}
            <h1 className="text-xl font-bold text-gray-900">{tenantName}</h1>
            <p className="text-sm text-gray-500 mt-1">Parent Portal</p>
          </div>

          {/* Success state */}
          {status === 'success' ? (
            <div className="text-center py-4">
              <div className="h-14 w-14 rounded-full bg-green-50 flex items-center justify-center mx-auto mb-4">
                <CheckCircle2 className="h-7 w-7 text-green-500" />
              </div>
              <h2 className="text-lg font-semibold text-gray-900 mb-2">
                Check your email
              </h2>
              <p className="text-sm text-gray-500 mb-6">
                We sent a login link to <strong className="text-gray-700">{email}</strong>.
                Click the link in the email to access the parent portal.
              </p>
              <button
                onClick={() => {
                  setStatus('idle');
                  setEmail('');
                }}
                className="text-sm text-indigo-600 hover:text-indigo-700 font-medium"
              >
                Use a different email
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label
                  htmlFor="parent-email"
                  className="block text-sm font-medium text-gray-700 mb-1.5"
                >
                  Email address
                </label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
                  <input
                    id="parent-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="parent@example.com"
                    required
                    disabled={status === 'loading' || status === 'demo-loading'}
                    className="w-full pl-10 pr-4 py-2.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 disabled:bg-gray-50 disabled:text-gray-400"
                  />
                </div>
              </div>

              {/* Error message */}
              {status === 'error' && errorMessage && (
                <div className="flex items-start gap-2 p-3 bg-red-50 border border-red-100 rounded-lg">
                  <AlertCircle className="h-4 w-4 text-red-500 mt-0.5 flex-shrink-0" />
                  <p className="text-sm text-red-600">{errorMessage}</p>
                </div>
              )}

              <button
                type="submit"
                disabled={status === 'loading' || status === 'demo-loading' || !email.trim()}
                className={cn(
                  'w-full py-2.5 rounded-lg text-sm font-medium text-white transition-colors',
                  'bg-indigo-600 hover:bg-indigo-700',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                  'inline-flex items-center justify-center gap-2',
                )}
              >
                {status === 'loading' ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Sending...
                  </>
                ) : (
                  'Send Login Link'
                )}
              </button>

              {/* Demo login button (dev only) */}
              {IS_DEV && (
                <button
                  type="button"
                  onClick={handleDemoLogin}
                  disabled={status === 'loading' || status === 'demo-loading'}
                  className={cn(
                    'w-full py-2.5 rounded-lg text-sm font-medium transition-colors',
                    'bg-amber-50 text-amber-700 border border-amber-200 hover:bg-amber-100',
                    'disabled:opacity-50 disabled:cursor-not-allowed',
                    'inline-flex items-center justify-center gap-2',
                  )}
                >
                  {status === 'demo-loading' ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Logging in...
                    </>
                  ) : (
                    <>Demo Login as {DEMO_PARENT_EMAIL}</>
                  )}
                </button>
              )}
            </form>
          )}

          {/* Footer link */}
          <div className="mt-6 pt-5 border-t border-gray-100 text-center">
            <p className="text-xs text-gray-400">
              Not a parent?{' '}
              <Link
                to="/login"
                className="text-indigo-600 hover:text-indigo-700 font-medium"
              >
                Sign in as teacher or admin
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
