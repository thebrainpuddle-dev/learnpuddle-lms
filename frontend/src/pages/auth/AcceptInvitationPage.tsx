import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { CheckCircleIcon, ExclamationTriangleIcon, AcademicCapIcon } from '@heroicons/react/24/outline';
import { adminTeachersService } from '../../services/adminTeachersService';

export const AcceptInvitationPage: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [accepted, setAccepted] = useState(false);

  const { data: invitation, isLoading, error } = useQuery({
    queryKey: ['invitation', token],
    queryFn: () => adminTeachersService.validateInvitation(token!),
    enabled: !!token,
    retry: false,
  });

  const acceptMut = useMutation({
    mutationFn: () => adminTeachersService.acceptInvitation(token!, password),
    onSuccess: () => setAccepted(true),
  });

  const errorMessage = (error as any)?.response?.data?.error || (error as any)?.message || 'Something went wrong.';
  const acceptError = (acceptMut.error as any)?.response?.data?.error || '';

  if (accepted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
        <div className="max-w-md w-full text-center space-y-4">
          <CheckCircleIcon className="h-16 w-16 text-green-500 mx-auto" />
          <h1 className="text-2xl font-bold text-gray-900">Account Created!</h1>
          <p className="text-gray-600">Your account has been set up successfully. You can now log in with your email and password.</p>
          <button
            onClick={() => navigate('/login')}
            className="mt-4 w-full py-2.5 px-4 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700 transition"
          >
            Go to Login
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
      <div className="max-w-md w-full">
        <div className="text-center mb-8">
          <AcademicCapIcon className="h-12 w-12 text-indigo-600 mx-auto mb-3" />
          <h1 className="text-2xl font-bold text-gray-900">Accept Invitation</h1>
        </div>

        {isLoading ? (
          <div className="bg-white rounded-xl shadow-sm border p-8 text-center">
            <div className="animate-spin h-8 w-8 border-2 border-indigo-600 border-t-transparent rounded-full mx-auto" />
            <p className="text-gray-500 mt-3">Validating invitation...</p>
          </div>
        ) : error ? (
          <div className="bg-white rounded-xl shadow-sm border p-8 text-center">
            <ExclamationTriangleIcon className="h-12 w-12 text-red-400 mx-auto mb-3" />
            <h2 className="text-lg font-semibold text-gray-900 mb-2">Invalid Invitation</h2>
            <p className="text-gray-600">{errorMessage}</p>
            <button
              onClick={() => navigate('/login')}
              className="mt-4 text-indigo-600 hover:text-indigo-800 text-sm font-medium"
            >
              Go to Login
            </button>
          </div>
        ) : invitation ? (
          <div className="bg-white rounded-xl shadow-sm border p-6 space-y-5">
            <div className="bg-indigo-50 rounded-lg p-4">
              <p className="text-sm text-indigo-700">
                You've been invited to join <strong>{invitation.school_name}</strong>
              </p>
              <p className="text-sm text-indigo-600 mt-1">Email: {invitation.email}</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
              <input type="text" value={invitation.first_name} disabled className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-gray-50 text-gray-600" />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Password *</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Confirm Password *</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Re-enter your password"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
              />
            </div>

            {acceptError && (
              <p className="text-sm text-red-600">{acceptError}</p>
            )}

            {password && confirmPassword && password !== confirmPassword && (
              <p className="text-sm text-red-600">Passwords do not match.</p>
            )}

            <button
              onClick={() => acceptMut.mutate()}
              disabled={!password || password.length < 8 || password !== confirmPassword || acceptMut.isPending}
              className="w-full py-2.5 px-4 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {acceptMut.isPending ? 'Creating Account...' : 'Create Account & Join'}
            </button>

            <p className="text-xs text-gray-400 text-center">
              Invitation expires {new Date(invitation.expires_at).toLocaleDateString()}
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
};
