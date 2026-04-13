// src/pages/auth/ResetPasswordPage.tsx

import React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { LockClosedIcon, CheckCircleIcon } from '@heroicons/react/24/outline';

import { useZodForm } from '../../hooks/useZodForm';
import { FormField } from '../../components/common/FormField';
import { Button } from '../../components/common/Button';
import { useTenantStore } from '../../stores/tenantStore';
import { authService } from '../../services/authService';
import { usePageTitle } from '../../hooks/usePageTitle';

// ─── Zod schema ──────────────────────────────────────────────────────────────

const ResetPasswordSchema = z
  .object({
    password: z
      .string()
      .min(8, 'Password must be at least 8 characters')
      .max(128),
    confirmPassword: z.string().min(1, 'Please confirm your password'),
  })
  .refine((data) => data.password === data.confirmPassword, {
    path: ['confirmPassword'],
    message: 'Passwords do not match',
  });

type ResetPasswordData = z.infer<typeof ResetPasswordSchema>;

// ─── Component ───────────────────────────────────────────────────────────────

export const ResetPasswordPage: React.FC = () => {
  usePageTitle('Reset Password');
  const { theme } = useTenantStore();
  const [searchParams] = useSearchParams();
  const uid = searchParams.get('uid') || '';
  const token = searchParams.get('token') || '';
  const [success, setSuccess] = React.useState(false);

  const tenantName = theme?.name || 'School';
  const tenantInitial = tenantName.charAt(0).toUpperCase();

  const isInvalidLink = !uid || !token;

  const form = useZodForm({
    schema: ResetPasswordSchema,
    defaultValues: { password: '', confirmPassword: '' },
  });

  const onSubmit = form.handleSubmit(async (data: ResetPasswordData) => {
    try {
      await authService.confirmPasswordReset(uid, token, data.password);
      setSuccess(true);
    } catch (err: any) {
      const errData = err.response?.data;
      const detail =
        errData?.error ||
        errData?.detail ||
        (Array.isArray(errData?.details) && errData.details.join(' ')) ||
        'An error occurred. Please try again.';
      form.setError('root', { type: 'server', message: detail });
    }
  });

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 to-secondary-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        {/* Tenant Logo */}
        <div className="text-center mb-8">
          {theme?.logo ? (
            <img
              src={theme.logo}
              alt={tenantName}
              className="mx-auto h-16 w-auto object-contain mb-4"
            />
          ) : (
            <div className="mx-auto h-16 w-16 bg-primary-600 rounded-full flex items-center justify-center mb-4">
              <span className="text-2xl font-bold text-white">{tenantInitial}</span>
            </div>
          )}
          <h1 className="text-3xl font-bold text-gray-900">{tenantName}</h1>
        </div>

        <div className="bg-white rounded-xl shadow-lg p-8">
          {isInvalidLink ? (
            <div className="text-center">
              <h2 className="text-2xl font-bold text-gray-900 mb-2">Invalid Reset Link</h2>
              <p className="text-gray-600 mb-6">
                This password reset link is invalid or has expired. Please request a new one.
              </p>
              <Link
                to="/forgot-password"
                className="text-primary-600 hover:text-primary-700 font-medium"
              >
                Request New Reset Link
              </Link>
            </div>
          ) : success ? (
            <div className="text-center">
              <div className="mx-auto h-12 w-12 bg-green-100 rounded-full flex items-center justify-center mb-4">
                <CheckCircleIcon className="h-6 w-6 text-green-600" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">Password Reset</h2>
              <p className="text-gray-600 mb-6">
                Your password has been successfully reset. You can now sign in with your new password.
              </p>
              <Link
                to="/login"
                className="inline-flex items-center justify-center px-6 py-3 bg-primary-600 text-white font-medium rounded-lg hover:bg-primary-700 transition-colors"
              >
                Sign In
              </Link>
            </div>
          ) : (
            <>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                Set new password
              </h2>
              <p className="text-gray-600 mb-6">
                Enter your new password below.
              </p>

              {form.formState.errors.root?.message && (
                <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm text-red-600">
                    {form.formState.errors.root.message}
                  </p>
                </div>
              )}

              <form onSubmit={onSubmit} noValidate className="space-y-6">
                <FormField
                  control={form.control}
                  name="password"
                  label="New Password"
                  type="password"
                  id="password"
                  autoComplete="new-password"
                  leftIcon={<LockClosedIcon className="h-5 w-5 text-gray-400" />}
                  placeholder="••••••••"
                  helperText="Must be at least 8 characters"
                />

                <FormField
                  control={form.control}
                  name="confirmPassword"
                  label="Confirm New Password"
                  type="password"
                  id="confirmPassword"
                  autoComplete="new-password"
                  leftIcon={<LockClosedIcon className="h-5 w-5 text-gray-400" />}
                  placeholder="••••••••"
                />

                <Button
                  type="submit"
                  variant="primary"
                  size="lg"
                  fullWidth
                  loading={form.formState.isSubmitting}
                >
                  Reset Password
                </Button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
