// src/pages/auth/ResetPasswordPage.tsx

import React, { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Input } from '../../components/common/Input';
import { Button } from '../../components/common/Button';
import { useTenantStore } from '../../stores/tenantStore';
import { authService } from '../../services/authService';
import { usePageTitle } from '../../hooks/usePageTitle';
import { LockClosedIcon, CheckCircleIcon } from '@heroicons/react/24/outline';

export const ResetPasswordPage: React.FC = () => {
  usePageTitle('Reset Password');
  const { theme } = useTenantStore();
  const [searchParams] = useSearchParams();
  const uid = searchParams.get('uid') || '';
  const token = searchParams.get('token') || '';

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');

  const tenantName = theme?.name || 'School';
  const tenantInitial = tenantName.charAt(0).toUpperCase();

  const isInvalidLink = !uid || !token;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (password !== confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters');
      return;
    }

    setLoading(true);

    try {
      await authService.confirmPasswordReset(uid, token, password);
      setSuccess(true);
    } catch (err: any) {
      const data = err.response?.data;
      const detail =
        data?.error ||
        data?.detail ||
        (data?.details && data.details.join(' ')) ||
        'An error occurred. Please try again.';
      setError(detail);
    } finally {
      setLoading(false);
    }
  };

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

              {error && (
                <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm text-red-600">{error}</p>
                </div>
              )}

              <form onSubmit={handleSubmit} className="space-y-6">
                <Input
                  label="New Password"
                  type="password"
                  name="password"
                  id="password"
                  autoComplete="new-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  leftIcon={<LockClosedIcon className="h-5 w-5 text-gray-400" />}
                  placeholder="••••••••"
                />

                <Input
                  label="Confirm New Password"
                  type="password"
                  name="confirmPassword"
                  id="confirmPassword"
                  autoComplete="new-password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  leftIcon={<LockClosedIcon className="h-5 w-5 text-gray-400" />}
                  placeholder="••••••••"
                />

                <Button
                  type="submit"
                  variant="primary"
                  size="lg"
                  fullWidth
                  loading={loading}
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
