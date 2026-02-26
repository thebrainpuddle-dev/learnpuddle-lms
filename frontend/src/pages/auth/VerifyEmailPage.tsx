import React from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import api from '../../config/api';

type VerifyState = 'loading' | 'success' | 'error';

export const VerifyEmailPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [state, setState] = React.useState<VerifyState>('loading');
  const [message, setMessage] = React.useState('Verifying your email...');

  React.useEffect(() => {
    const uid = searchParams.get('uid') || '';
    const token = searchParams.get('token') || '';

    if (!uid || !token) {
      setState('error');
      setMessage('Invalid verification link.');
      return;
    }

    api.post('/users/auth/verify-email/', { uid, token })
      .then((res) => {
        setState('success');
        setMessage(res.data?.message || 'Email verified successfully.');
      })
      .catch((err: any) => {
        setState('error');
        setMessage(
          err?.response?.data?.error ||
          err?.response?.data?.detail ||
          'Verification link is invalid or expired.'
        );
      });
  }, [searchParams]);

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="max-w-md w-full bg-white border border-gray-200 rounded-xl shadow-sm p-8 text-center">
        <h1 className="text-2xl font-bold text-gray-900 mb-3">Email Verification</h1>
        {state === 'loading' && (
          <div className="mb-4 flex items-center justify-center">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
          </div>
        )}
        <p className="text-gray-600 mb-6">{message}</p>
        <Link
          to="/login"
          className="inline-flex items-center justify-center px-4 py-2 bg-primary-600 text-white rounded-lg hover:bg-primary-700 transition-colors"
        >
          Go to Login
        </Link>
      </div>
    </div>
  );
};
