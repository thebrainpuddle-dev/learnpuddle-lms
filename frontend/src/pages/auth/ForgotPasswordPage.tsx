// src/pages/auth/ForgotPasswordPage.tsx

import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Input } from '../../components/common/Input';
import { Button } from '../../components/common/Button';
import { useTenantStore } from '../../stores/tenantStore';
import { authService } from '../../services/authService';
import { usePageTitle } from '../../hooks/usePageTitle';
import { EnvelopeIcon, ArrowLeftIcon } from '@heroicons/react/24/outline';

export const ForgotPasswordPage: React.FC = () => {
  usePageTitle('Forgot Password');
  const { theme } = useTenantStore();
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState('');

  const tenantName = theme?.name || 'School';
  const tenantInitial = tenantName.charAt(0).toUpperCase();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await authService.requestPasswordReset(email);
      setSubmitted(true);
    } catch (err: any) {
      const detail =
        err.response?.data?.error ||
        err.response?.data?.detail ||
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
          {submitted ? (
            <div className="text-center">
              <div className="mx-auto h-12 w-12 bg-green-100 rounded-full flex items-center justify-center mb-4">
                <EnvelopeIcon className="h-6 w-6 text-green-600" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">Check your email</h2>
              <p className="text-gray-600 mb-6">
                If an account exists for <span className="font-medium">{email}</span>, we've sent password reset instructions.
              </p>
              <Link
                to="/login"
                className="text-primary-600 hover:text-primary-700 font-medium"
              >
                Back to Sign In
              </Link>
            </div>
          ) : (
            <>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                Forgot your password?
              </h2>
              <p className="text-gray-600 mb-6">
                Enter your email address and we'll send you a link to reset your password.
              </p>

              {error && (
                <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm text-red-600">{error}</p>
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

                <Button
                  type="submit"
                  variant="primary"
                  size="lg"
                  fullWidth
                  loading={loading}
                >
                  Send Reset Link
                </Button>
              </form>

              <div className="mt-6 text-center">
                <Link
                  to="/login"
                  className="inline-flex items-center text-sm font-medium text-primary-600 hover:text-primary-700"
                >
                  <ArrowLeftIcon className="h-4 w-4 mr-1" />
                  Back to Sign In
                </Link>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
