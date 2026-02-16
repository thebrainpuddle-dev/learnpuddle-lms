// pages/auth/SSOCallbackPage.tsx
/**
 * SSO callback handler page.
 *
 * Receives a one-time code from the OAuth callback, exchanges it for
 * JWT tokens via a secure POST request, then stores them.
 * Tokens are NEVER exposed in URL parameters.
 */

import React, { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Loading } from '../../components/common';
import api from '../../config/api';

export const SSOCallbackPage: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get('code');
    const errorParam = searchParams.get('error');

    if (errorParam) {
      setError(errorParam === 'sso_failed' ? 'SSO login failed. Please try again.' : errorParam);
      return;
    }

    if (!code) {
      setError('Invalid SSO response. Missing authorization code.');
      return;
    }

    // Exchange the one-time code for tokens via secure POST
    const exchangeCode = async () => {
      try {
        const response = await api.post('/users/auth/sso/token-exchange/', { code });
        const { access_token, refresh_token } = response.data;

        // Store tokens
        sessionStorage.setItem('access_token', access_token);
        sessionStorage.setItem('refresh_token', refresh_token);

        // Redirect to dashboard
        navigate('/dashboard', { replace: true });
      } catch {
        setError('Failed to complete sign in. The link may have expired.');
      }
    };

    exchangeCode();
  }, [searchParams, navigate]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="bg-white p-8 rounded-lg shadow-md max-w-md text-center">
          <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg
              className="w-8 h-8 text-red-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </div>
          <h1 className="text-xl font-semibold text-gray-900 mb-2">Sign In Failed</h1>
          <p className="text-gray-600 mb-6">{error}</p>
          <button
            onClick={() => navigate('/login')}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
          >
            Return to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="text-center">
        <Loading />
        <p className="mt-4 text-gray-600">Completing sign in...</p>
      </div>
    </div>
  );
};

export default SSOCallbackPage;
