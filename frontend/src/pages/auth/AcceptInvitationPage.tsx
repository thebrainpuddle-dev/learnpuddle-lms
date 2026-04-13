import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { z } from 'zod';
import { CheckCircleIcon, ExclamationTriangleIcon, AcademicCapIcon } from '@heroicons/react/24/outline';

import { useZodForm } from '../../hooks/useZodForm';
import { FormField } from '../../components/common/FormField';
import { adminTeachersService } from '../../services/adminTeachersService';

// ─── Zod schema ──────────────────────────────────────────────────────────────

const AcceptInvitationSchema = z
  .object({
    password: z
      .string()
      .min(8, 'Password must be at least 8 characters')
      .max(128),
    confirmPassword: z.string().min(1, 'Please confirm your password'),
  })
  .refine((d) => d.password === d.confirmPassword, {
    path: ['confirmPassword'],
    message: 'Passwords do not match',
  });

type AcceptInvitationData = z.infer<typeof AcceptInvitationSchema>;

// ─── Component ───────────────────────────────────────────────────────────────

export const AcceptInvitationPage: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const [accepted, setAccepted] = useState(false);

  const form = useZodForm({
    schema: AcceptInvitationSchema,
    defaultValues: { password: '', confirmPassword: '' },
  });

  const { data: invitation, isLoading, error } = useQuery({
    queryKey: ['invitation', token],
    queryFn: () => adminTeachersService.validateInvitation(token!),
    enabled: !!token,
    retry: false,
  });

  const acceptMut = useMutation({
    mutationFn: (password: string) =>
      adminTeachersService.acceptInvitation(token!, password),
    onSuccess: () => setAccepted(true),
    onError: (err: any) => {
      const message =
        err?.response?.data?.error ||
        (err?.response?.data?.details as string[])?.join(' ') ||
        'Failed to create account. Please try again.';
      form.setError('root', { type: 'server', message });
    },
  });

  const onSubmit = form.handleSubmit((data: AcceptInvitationData) => {
    acceptMut.mutate(data.password);
  });

  const errorMessage =
    (error as any)?.response?.data?.error ||
    (error as any)?.message ||
    'Something went wrong.';

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
          <form onSubmit={onSubmit} noValidate className="bg-white rounded-xl shadow-sm border p-6 space-y-5">
            <div className="bg-indigo-50 rounded-lg p-4">
              <p className="text-sm text-indigo-700">
                You've been invited to join <strong>{invitation.school_name}</strong>
              </p>
              <p className="text-sm text-indigo-600 mt-1">Email: {invitation.email}</p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">First Name</label>
              <input
                type="text"
                value={invitation.first_name}
                disabled
                className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm bg-gray-50 text-gray-600"
              />
            </div>

            <FormField
              control={form.control}
              name="password"
              label="Password"
              type="password"
              autoComplete="new-password"
              placeholder="Choose a strong password"
              helperText="Must be at least 8 characters"
            />

            <FormField
              control={form.control}
              name="confirmPassword"
              label="Confirm Password"
              type="password"
              autoComplete="new-password"
              placeholder="Re-enter your password"
            />

            {form.formState.errors.root?.message && (
              <p className="text-sm text-red-600">
                {form.formState.errors.root.message}
              </p>
            )}

            <button
              type="submit"
              disabled={acceptMut.isPending || form.formState.isSubmitting}
              className="w-full py-2.5 px-4 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700 transition disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {acceptMut.isPending ? 'Creating Account...' : 'Create Account & Join'}
            </button>

            <p className="text-xs text-gray-400 text-center">
              Invitation expires {new Date(invitation.expires_at).toLocaleDateString()}
            </p>
          </form>
        ) : null}
      </div>
    </div>
  );
};
