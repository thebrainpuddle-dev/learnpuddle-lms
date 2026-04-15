// src/pages/parent/ParentVerifyPage.tsx
//
// Token exchange page for parent magic link authentication.
// Reads token from URL, verifies with backend, stores session, redirects.

import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate, Link } from 'react-router-dom';
import { Loader2, AlertCircle, ShieldX } from 'lucide-react';
import { parentService } from '../../services/parentService';
import { useParentStore } from '../../stores/parentStore';

export function ParentVerifyPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { setSession } = useParentStore();
  const [status, setStatus] = useState<'verifying' | 'error'>('verifying');
  const [errorMessage, setErrorMessage] = useState('');

  const token = searchParams.get('token');

  useEffect(() => {
    if (!token) {
      setStatus('error');
      setErrorMessage('No verification token found in the URL.');
      return;
    }

    let cancelled = false;

    async function verify() {
      try {
        const data = await parentService.verifyToken(token!);
        if (cancelled) return;

        // Use email from backend response, fallback to sessionStorage
        const email =
          data.parent_email || sessionStorage.getItem('parent_email') || '';

        setSession({
          session_token: data.session_token,
          refresh_token: data.refresh_token,
          expires_at: data.expires_at,
          children: data.children,
          email,
        });

        navigate('/parent/dashboard', { replace: true });
      } catch (err: unknown) {
        if (cancelled) return;
        setStatus('error');
        const message =
          (err as { response?: { data?: { detail?: string; error?: string } } })
            ?.response?.data?.detail ||
          (err as { response?: { data?: { detail?: string; error?: string } } })
            ?.response?.data?.error ||
          'Verification failed. The link may have expired.';
        setErrorMessage(message);
      }
    }

    verify();
    return () => {
      cancelled = true;
    };
  }, [token, searchParams, navigate, setSession]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-xl border border-gray-100 p-8 text-center">
          {status === 'verifying' ? (
            <>
              <Loader2 className="h-10 w-10 text-indigo-500 animate-spin mx-auto mb-4" />
              <h2 className="text-lg font-semibold text-gray-900 mb-2">
                Verifying your link...
              </h2>
              <p className="text-sm text-gray-500">
                Please wait while we verify your login link.
              </p>
            </>
          ) : (
            <>
              <div className="h-14 w-14 rounded-full bg-red-50 flex items-center justify-center mx-auto mb-4">
                {token ? (
                  <AlertCircle className="h-7 w-7 text-red-500" />
                ) : (
                  <ShieldX className="h-7 w-7 text-red-500" />
                )}
              </div>
              <h2 className="text-lg font-semibold text-gray-900 mb-2">
                Verification Failed
              </h2>
              <p className="text-sm text-gray-500 mb-6">{errorMessage}</p>
              <Link
                to="/parent"
                className="inline-flex items-center justify-center px-5 py-2.5 rounded-lg text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
              >
                Request New Link
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
