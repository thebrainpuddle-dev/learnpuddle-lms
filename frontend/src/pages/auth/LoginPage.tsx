// src/pages/auth/LoginPage.tsx
//
// Tenant-scoped login page for School Admins and Teachers.
// Super admins use the separate /super-admin/login page.

import React, { useState } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import { Input } from '../../components/common/Input';
import { Button } from '../../components/common/Button';
import { Checkbox } from '../../components/common/Checkbox';
import { useAuthStore } from '../../stores/authStore';
import { useTenantStore } from '../../stores/tenantStore';
import { usePageTitle } from '../../hooks/usePageTitle';
import api from '../../config/api';
import { EnvelopeIcon, LockClosedIcon } from '@heroicons/react/24/outline';

export const LoginPage: React.FC = () => {
  usePageTitle('Login');
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { setAuth, setLoading } = useAuthStore();
  const { theme } = useTenantStore();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoadingState] = useState(false);
  const logoutReason = searchParams.get('reason');

  // Tenant name from the loaded theme (resolved from subdomain during app boot)
  const tenantName = theme?.name || 'School';
  const tenantInitial = tenantName.charAt(0).toUpperCase();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoadingState(true);
    setLoading(true);

    try {
      const response = await api.post('/users/auth/login/', {
        email,
        password,
        portal: 'tenant',
      });
      const { user, tokens } = response.data;

      // Store auth state (use localStorage if "Remember me" is checked)
      setAuth(user, tokens, rememberMe);

      // Redirect based on role
      if (user.role === 'SCHOOL_ADMIN') {
        navigate('/admin/dashboard');
      } else if (user.role === 'SUPER_ADMIN') {
        // Should not happen because backend rejects super admin on tenant portal,
        // but handle gracefully just in case.
        navigate('/super-admin/dashboard');
      } else {
        navigate('/teacher/dashboard');
      }
    } catch (err: any) {
      const detail =
        err.response?.data?.non_field_errors?.[0] ||
        err.response?.data?.detail ||
        err.response?.data?.error ||
        '';
      if (err.response?.status === 400) {
        setError(detail || 'Invalid email or password');
      } else if (err.response?.status === 403) {
        setError('Your account has been disabled');
      } else if ([502, 503, 504].includes(err.response?.status)) {
        setError('Service is temporarily unavailable. Please retry in a few seconds.');
      } else {
        setError('An error occurred. Please try again.');
      }
    } finally {
      setLoadingState(false);
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 to-secondary-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full">
        {/* Tenant Logo and Name */}
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
          <p className="text-gray-600 mt-2">Learning Management System</p>
        </div>

        {/* Login Card */}
        <div className="bg-white rounded-xl shadow-lg p-8">
          <h2 className="text-2xl font-bold text-gray-900 mb-6">
            Sign in to your account
          </h2>

          {error && (
            <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-600">{error}</p>
            </div>
          )}
          {!error && logoutReason === 'idle_timeout' && (
            <div className="mb-4 p-4 bg-amber-50 border border-amber-200 rounded-lg">
              <p className="text-sm text-amber-700">
                You were signed out after 30 minutes of inactivity.
              </p>
            </div>
          )}
          {!error && logoutReason === 'session_expired' && (
            <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm text-blue-700">Your session expired. Please sign in again.</p>
            </div>
          )}
          {!error && logoutReason === 'tenant_access_denied' && (
            <div className="mb-4 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm text-blue-700">Your session context changed. Please sign in again.</p>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            <Input
              label="Email Address"
              type="email"
              name="email"
              id="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              leftIcon={<EnvelopeIcon className="h-5 w-5 text-gray-400" />}
              placeholder="you@school.com"
            />

            <Input
              label="Password"
              type="password"
              name="password"
              id="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              leftIcon={<LockClosedIcon className="h-5 w-5 text-gray-400" />}
              placeholder="••••••••"
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
                className="text-sm font-medium text-primary-600 hover:text-primary-700"
              >
                Forgot password?
              </Link>
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              fullWidth
              loading={loading}
            >
              Sign In
            </Button>
          </form>

          <p className="mt-6 text-xs text-gray-500">
            Use your LearnPuddle account credentials to sign in.
          </p>
        </div>

        {/* Footer */}
        <p className="text-center text-sm text-gray-600 mt-8">
          Powered by LearnPuddle &copy; {new Date().getFullYear()}
        </p>
      </div>
    </div>
  );
};
