// src/pages/auth/SuperAdminLoginPage.tsx

import React from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import {
  EnvelopeIcon,
  LockClosedIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline';

import { useZodForm } from '../../hooks/useZodForm';
import { Button } from '../../components/common/Button';
import { useAuthStore } from '../../stores/authStore';
import { usePageTitle } from '../../hooks/usePageTitle';
import api from '../../config/api';

// ─── Zod schema ──────────────────────────────────────────────────────────────

const SuperAdminLoginSchema = z.object({
  email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});

type SuperAdminLoginData = z.infer<typeof SuperAdminLoginSchema>;

// ─── Component ───────────────────────────────────────────────────────────────

export const SuperAdminLoginPage: React.FC = () => {
  usePageTitle('Super Admin Login');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setAuth, setLoading } = useAuthStore();

  const logoutReason = searchParams.get('reason');

  const form = useZodForm({
    schema: SuperAdminLoginSchema,
    defaultValues: { email: '', password: '' },
  });

  const onSubmit = form.handleSubmit(async (data: SuperAdminLoginData) => {
    setLoading(true);
    try {
      const response = await api.post('/users/auth/login/', {
        email: data.email,
        password: data.password,
        portal: 'super_admin',
      });
      const { user, tokens } = response.data;

      if (user.role !== 'SUPER_ADMIN') {
        form.setError('root', {
          type: 'server',
          message: 'This portal is for platform administrators only.',
        });
        return;
      }

      setAuth(user, tokens);
      navigate('/super-admin/dashboard');
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
        message = 'Access denied';
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
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="mx-auto h-16 w-16 bg-indigo-600 rounded-2xl flex items-center justify-center mb-4 shadow-lg shadow-indigo-500/30">
            <ShieldCheckIcon className="h-9 w-9 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white sm:text-3xl">Command Center</h1>
          <p className="text-slate-400 mt-2">LearnPuddle Platform Administration</p>
        </div>

        {/* Login Card */}
        <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl shadow-2xl p-5 sm:p-8">
          <h2 className="text-xl font-semibold text-white mb-6">
            Platform Admin Sign In
          </h2>

          {hasRootError && (
            <div className="mb-4 p-4 bg-red-500/10 border border-red-500/20 rounded-lg">
              <p className="text-sm text-red-300">
                {form.formState.errors.root!.message}
              </p>
            </div>
          )}
          {!hasRootError && logoutReason === 'idle_timeout' && (
            <div className="mb-4 p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg">
              <p className="text-sm text-amber-300">
                You were signed out after 30 minutes of inactivity.
              </p>
            </div>
          )}
          {!hasRootError && logoutReason === 'session_expired' && (
            <div className="mb-4 p-4 bg-sky-500/10 border border-sky-500/20 rounded-lg">
              <p className="text-sm text-sky-300">Session expired. Please sign in again.</p>
            </div>
          )}
          {!hasRootError && logoutReason === 'tenant_access_denied' && (
            <div className="mb-4 p-4 bg-sky-500/10 border border-sky-500/20 rounded-lg">
              <p className="text-sm text-sky-300">Session context changed. Please sign in again.</p>
            </div>
          )}

          <form onSubmit={onSubmit} noValidate className="space-y-5">
            {/* Email — using Controller directly for the custom dark-theme input */}
            <div>
              <label htmlFor="superadmin-email" className="block text-sm font-medium text-slate-300 mb-1.5">
                Email Address
              </label>
              <div className="relative">
                <EnvelopeIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-500" />
                <Controller
                  control={form.control}
                  name="email"
                  render={({ field, fieldState }) => (
                    <>
                      <input
                        {...field}
                        id="superadmin-email"
                        type="email"
                        autoComplete="email"
                        placeholder="admin@lms.com"
                        aria-invalid={fieldState.invalid}
                        className="w-full pl-10 pr-4 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-slate-500 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors aria-[invalid=true]:border-red-500"
                      />
                      {fieldState.error && (
                        <p className="mt-1 text-xs text-red-400">{fieldState.error.message}</p>
                      )}
                    </>
                  )}
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label htmlFor="superadmin-password" className="block text-sm font-medium text-slate-300 mb-1.5">
                Password
              </label>
              <div className="relative">
                <LockClosedIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-slate-500" />
                <Controller
                  control={form.control}
                  name="password"
                  render={({ field, fieldState }) => (
                    <>
                      <input
                        {...field}
                        id="superadmin-password"
                        type="password"
                        autoComplete="current-password"
                        placeholder="••••••••"
                        aria-invalid={fieldState.invalid}
                        className="w-full pl-10 pr-4 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-slate-500 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors aria-[invalid=true]:border-red-500"
                      />
                      {fieldState.error && (
                        <p className="mt-1 text-xs text-red-400">{fieldState.error.message}</p>
                      )}
                    </>
                  )}
                />
              </div>
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              fullWidth
              loading={form.formState.isSubmitting}
              className="!bg-indigo-600 hover:!bg-indigo-700"
            >
              Sign In to Command Center
            </Button>
          </form>
        </div>

        <p className="text-center text-sm text-slate-500 mt-8">
          Not a platform admin?{' '}
          <a href="/login" className="text-indigo-400 hover:text-indigo-300 font-medium">
            Go to school login
          </a>
        </p>
      </div>
    </div>
  );
};
