// src/pages/auth/LoginPage.tsx
//
// Tenant-scoped login page — warm cream/golden split layout.

import React from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { Mail, Lock, ArrowRight, BookOpen, Trophy, BarChart3 } from 'lucide-react';

import { useZodForm } from '../../hooks/useZodForm';
import { FormField } from '../../components/common/FormField';
import { Button as LegacyButton } from '../../components/common/Button';
import { Checkbox } from '../../components/common/Checkbox';
import { useAuthStore } from '../../stores/authStore';
import { useTenantStore } from '../../stores/tenantStore';
import { usePageTitle } from '../../hooks/usePageTitle';
import api from '../../config/api';
import { loadTenantTheme, applyTheme } from '../../config/theme';

// ─── Zod schema ──────────────────────────────────────────────────────────────

const LoginSchema = z.object({
  identifier: z.string().min(1, 'Email or ID is required'),
  password: z.string().min(1, 'Password is required'),
});

type LoginData = z.infer<typeof LoginSchema>;

// ─── Component ───────────────────────────────────────────────────────────────

export const LoginPage: React.FC = () => {
  usePageTitle('Login');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setAuth, setLoading } = useAuthStore();
  const { theme, setTheme } = useTenantStore();
  const [rememberMe, setRememberMe] = React.useState(false);

  const logoutReason = searchParams.get('reason');
  const tenantName = theme?.name || 'LearnPuddle';
  const tenantInitial = tenantName.charAt(0).toUpperCase();

  const isWhiteLabel = theme?.whiteLabel === true;

  const form = useZodForm({
    schema: LoginSchema,
    defaultValues: { identifier: '', password: '' },
  });

  const onSubmit = form.handleSubmit(async (data: LoginData) => {
    setLoading(true);
    try {
      const response = await api.post('/users/auth/login/', {
        identifier: data.identifier,
        password: data.password,
        portal: 'tenant',
      });
      const { user, tokens } = response.data;
      setAuth(user, tokens, rememberMe);

      // Reload tenant theme now that tenant_subdomain is set in storage
      // This ensures the correct school name, logo, and colors are applied
      try {
        const tenantTheme = await loadTenantTheme();
        applyTheme(tenantTheme);
        setTheme(tenantTheme);
      } catch {
        // Theme reload is best-effort — proceed with navigation
      }

      if (user.role === 'SCHOOL_ADMIN') {
        navigate('/admin/dashboard');
      } else if (user.role === 'SUPER_ADMIN') {
        navigate('/super-admin/dashboard');
      } else if (user.role === 'STUDENT') {
        navigate('/student/dashboard');
      } else {
        navigate('/teacher/dashboard');
      }
    } catch (err: any) {
      const detail =
        err.response?.data?.non_field_errors?.[0] ||
        err.response?.data?.detail ||
        err.response?.data?.error ||
        '';

      let message: string;
      if (err.response?.status === 400) {
        message = detail || 'Invalid credentials';
      } else if (err.response?.status === 403) {
        message = detail || 'Your account has been disabled';
      } else if ([502, 503, 504].includes(err.response?.status)) {
        message = 'Service is temporarily unavailable. Please retry in a few seconds.';
      } else {
        message = 'An error occurred. Please try again.';
      }
      form.setError('root', { type: 'server', message });
    } finally {
      setLoading(false);
    }
  });

  const hasRootError = Boolean(form.formState.errors.root);

  return (
    <div className="min-h-screen flex">
      {/* ─── Left panel: Branding (hidden on mobile) ────────────────── */}
      <div
        className="hidden lg:flex lg:w-[45%] relative overflow-hidden"
        style={
          theme?.loginBgImage
            ? { backgroundImage: `url(${theme.loginBgImage})`, backgroundSize: 'cover', backgroundPosition: 'center' }
            : undefined
        }
      >
        {/* Default gradient background (no bg image) */}
        {!theme?.loginBgImage && (
          <div className="absolute inset-0 bg-gradient-to-br from-amber-50 via-orange-50 to-yellow-50" />
        )}

        {/* Gradient overlay for readability on background images */}
        {theme?.loginBgImage && (
          <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-black/30 to-black/40" />
        )}

        {/* Background pattern (no bg image only) */}
        {!theme?.loginBgImage && (
          <div className="absolute inset-0 opacity-30">
            <div className="absolute top-20 left-10 w-72 h-72 bg-accent/20 rounded-full blur-3xl" />
            <div className="absolute bottom-20 right-10 w-96 h-96 bg-orange-300/20 rounded-full blur-3xl" />
          </div>
        )}

        <div className="relative z-10 flex flex-col justify-between p-12 w-full">
          {/* Top: Logo + School Name */}
          <div className="flex items-center gap-3">
            {theme?.logo ? (
              <img
                src={theme.logo}
                alt={tenantName}
                className="h-12 w-12 rounded-full object-cover shadow-lg ring-2 ring-white/30"
              />
            ) : (
              <div className="h-12 w-12 rounded-full bg-gradient-to-br from-accent to-accent-dark flex items-center justify-center shadow-lg ring-2 ring-white/30">
                <span className="text-white font-bold text-lg">{tenantInitial}</span>
              </div>
            )}
            <span className={`text-xl font-semibold ${theme?.loginBgImage ? 'text-white drop-shadow-md' : 'text-content'}`}>
              {tenantName}
            </span>
          </div>

          {/* Center: Value props or white-label welcome */}
          <div className="space-y-8">
            {isWhiteLabel ? (
              <div>
                <h2 className={`text-4xl font-bold leading-tight ${theme?.loginBgImage ? 'text-white drop-shadow-lg' : 'text-content'}`}>
                  {theme?.welcomeMessage || `Welcome to ${tenantName}`}
                </h2>
                {theme?.schoolMotto && (
                  <p className={`mt-4 text-lg max-w-md ${theme?.loginBgImage ? 'text-white/85 drop-shadow-md' : 'text-content-secondary'}`}>
                    {theme.schoolMotto}
                  </p>
                )}
              </div>
            ) : (
              <>
                <div>
                  <h2 className={`text-4xl font-bold leading-tight ${theme?.loginBgImage ? 'text-white drop-shadow-lg' : 'text-content'}`}>
                    Train, Track,<br />
                    <span className={theme?.loginBgImage ? 'text-amber-300' : 'text-gradient'}>
                      Transform.
                    </span>
                  </h2>
                  <p className={`mt-4 text-lg max-w-md ${theme?.loginBgImage ? 'text-white/85 drop-shadow-md' : 'text-content-secondary'}`}>
                    Your complete training platform — courses, gamification, and analytics in one place.
                  </p>
                </div>

                <div className="space-y-4">
                  <FeatureRow icon={BookOpen} text="Courses with video, quizzes, and certificates" hasBg={!!theme?.loginBgImage} />
                  <FeatureRow icon={Trophy} text="Gamification with XP, badges, and streaks" hasBg={!!theme?.loginBgImage} />
                  <FeatureRow icon={BarChart3} text="Analytics and progress tracking" hasBg={!!theme?.loginBgImage} />
                </div>
              </>
            )}
          </div>

          {/* Bottom: Branding */}
          <p className={`text-sm ${theme?.loginBgImage ? 'text-white/60' : 'text-content-muted'}`}>
            {isWhiteLabel
              ? `\u00A9 ${new Date().getFullYear()} ${tenantName}`
              : 'Powered by LearnPuddle'}
          </p>
        </div>
      </div>

      {/* ─── Right panel: Login form ────────────────────────────────── */}
      <div className="flex-1 flex items-center justify-center p-6 sm:p-12 bg-white">
        <div className="w-full max-w-[420px]">
          {/* Mobile logo (hidden on desktop) */}
          <div className="lg:hidden text-center mb-8">
            {theme?.logo ? (
              <img
                src={theme.logo}
                alt={tenantName}
                className="mx-auto h-14 w-14 rounded-full object-cover mb-3"
              />
            ) : (
              <div className="mx-auto h-14 w-14 rounded-full bg-gradient-to-br from-accent to-accent-dark flex items-center justify-center mb-3">
                <span className="text-2xl font-bold text-white">{tenantInitial}</span>
              </div>
            )}
            <h1 className="text-2xl font-bold text-content">{tenantName}</h1>
          </div>

          {/* Welcome text */}
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-content">
              {theme?.welcomeMessage || `Welcome to ${tenantName}`}
            </h2>
            <p className="mt-1 text-content-secondary">
              Sign in to continue to your dashboard
            </p>
          </div>

          {/* Alerts */}
          {hasRootError && (
            <div className="mb-6 p-4 bg-danger-bg border border-danger/20 rounded-xl">
              <p className="text-sm text-danger-dark">
                {form.formState.errors.root!.message}
              </p>
            </div>
          )}

          {!hasRootError && logoutReason === 'idle_timeout' && (
            <div className="mb-6 p-4 bg-warning-bg border border-warning/20 rounded-xl">
              <p className="text-sm text-warning-dark">
                You were signed out after 30 minutes of inactivity.
              </p>
            </div>
          )}
          {!hasRootError && logoutReason === 'session_expired' && (
            <div className="mb-6 p-4 bg-info-bg border border-info/20 rounded-xl">
              <p className="text-sm text-info-dark">
                Your session expired. Please sign in again.
              </p>
            </div>
          )}
          {!hasRootError && logoutReason === 'tenant_access_denied' && (
            <div className="mb-6 p-4 bg-info-bg border border-info/20 rounded-xl">
              <p className="text-sm text-info-dark">
                Your session context changed. Please sign in again.
              </p>
            </div>
          )}

          {/* Form */}
          <form onSubmit={onSubmit} noValidate className="space-y-5">
            <FormField
              control={form.control}
              name="identifier"
              label="Email or Student/Teacher ID"
              type="text"
              id="identifier"
              autoComplete="email"
              leftIcon={<Mail className="h-5 w-5 text-content-muted" />}
              placeholder="you@school.com or KIS-S-0001"
            />

            <FormField
              control={form.control}
              name="password"
              label="Password"
              type="password"
              id="password"
              autoComplete="current-password"
              leftIcon={<Lock className="h-5 w-5 text-content-muted" />}
              placeholder="Enter your password"
            />

            <div className="flex items-center justify-between">
              <Checkbox
                id="remember-me"
                label="Remember me"
                checked={rememberMe}
                onChange={(e) => setRememberMe(e.target.checked)}
              />

              <Link
                to="/forgot-password"
                className="text-sm font-medium text-accent hover:text-accent-dark transition-colors"
              >
                Forgot password?
              </Link>
            </div>

            <LegacyButton
              type="submit"
              variant="primary"
              size="lg"
              fullWidth
              loading={form.formState.isSubmitting}
            >
              <span className="flex items-center gap-2">
                Sign In
                <ArrowRight className="h-4 w-4" />
              </span>
            </LegacyButton>
          </form>

          {/* Footer */}
          <p className="mt-8 text-center text-xs text-content-muted">
            &copy; {new Date().getFullYear()} {isWhiteLabel ? tenantName : 'LearnPuddle'}. All rights reserved.
          </p>
        </div>
      </div>
    </div>
  );
};

// ─── Sub-components ──────────────────────────────────────────────────────────

function FeatureRow({ icon: Icon, text, hasBg = false }: { icon: React.ElementType; text: string; hasBg?: boolean }) {
  return (
    <div className="flex items-center gap-4">
      <div className={`h-10 w-10 rounded-xl flex items-center justify-center flex-shrink-0 shadow-sm ${hasBg ? 'bg-white/20 backdrop-blur-sm border border-white/20' : 'bg-white/80 border border-surface-border'}`}>
        <Icon className={`h-5 w-5 ${hasBg ? 'text-white' : 'text-accent'}`} />
      </div>
      <p className={`text-sm ${hasBg ? 'text-white/85' : 'text-content-secondary'}`}>{text}</p>
    </div>
  );
}
