// src/pages/admin/CreateTeacherPage.tsx
//
// School-admin page for creating a new teacher account.
// Form validation is handled by React Hook Form + Zod for type-safe,
// declarative validation. Server-side field errors from Django REST Framework
// are merged back into the form state via `setError`.

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import axios from 'axios';

import { useZodForm } from '../../hooks/useZodForm';
import { FormField } from '../../components/common/FormField';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common';
import { adminTeachersService } from '../../services/adminTeachersService';
import { usePageTitle } from '../../hooks/usePageTitle';

// ─── Zod schema ─────────────────────────────────────────────────────────────

const CreateTeacherSchema = z
  .object({
    first_name: z.string().min(1, 'First name is required').max(150),
    last_name: z.string().min(1, 'Last name is required').max(150),
    email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
    password: z
      .string()
      .min(8, 'Password must be at least 8 characters')
      .max(128),
    password_confirm: z.string().min(1, 'Please confirm the password'),
    employee_id: z.string().max(50).optional().or(z.literal('')),
    department: z.string().max(100).optional().or(z.literal('')),
  })
  .refine((data) => data.password === data.password_confirm, {
    path: ['password_confirm'],
    message: 'Passwords do not match',
  });

type CreateTeacherData = z.infer<typeof CreateTeacherSchema>;

// ─── Component ───────────────────────────────────────────────────────────────

export const CreateTeacherPage: React.FC = () => {
  usePageTitle('Create Teacher');
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const form = useZodForm({
    schema: CreateTeacherSchema,
    defaultValues: {
      first_name: '',
      last_name: '',
      email: '',
      password: '',
      password_confirm: '',
      employee_id: '',
      department: '',
    },
  });

  const mutation = useMutation({
    mutationFn: (data: CreateTeacherData) =>
      adminTeachersService.createTeacher(data),

    onSuccess: async (_, data) => {
      await queryClient.invalidateQueries({ queryKey: ['adminTeachers'] });
      toast.success(
        'Teacher created',
        `${data.first_name} ${data.last_name} has been added.`,
      );
      navigate('/admin/teachers');
    },

    onError: (error) => {
      // Merge Django REST Framework field-level errors into RHF state
      if (axios.isAxiosError(error) && error.response?.data) {
        const serverErrors = error.response.data as Record<string, string[]>;
        let hasFieldError = false;

        (Object.keys(serverErrors) as Array<keyof CreateTeacherData>).forEach(
          (field) => {
            const messages = serverErrors[field as string];
            if (Array.isArray(messages) && messages.length > 0) {
              form.setError(field, { type: 'server', message: messages[0] });
              hasFieldError = true;
            }
          },
        );

        const firstError = Object.values(serverErrors).flat()[0];
        if (firstError) {
          toast.error('Validation error', String(firstError));
        } else if (!hasFieldError) {
          toast.error(
            'Validation error',
            'Please check the form and correct any errors.',
          );
        }
      } else {
        const message =
          error instanceof Error ? error.message : 'Please try again.';
        toast.error('Failed to create teacher', message);
      }
    },
  });

  const onSubmit = form.handleSubmit((data) => mutation.mutate(data));

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Create Teacher</h1>
        <p className="mt-1 text-sm text-gray-500">
          Create a new teacher under this tenant.
        </p>
      </div>

      <form onSubmit={onSubmit} noValidate className="card space-y-4">
        {/* Name row */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <FormField
            control={form.control}
            name="first_name"
            label="First name"
            autoComplete="given-name"
          />
          <FormField
            control={form.control}
            name="last_name"
            label="Last name"
            autoComplete="family-name"
          />
        </div>

        {/* Email */}
        <FormField
          control={form.control}
          name="email"
          label="Email"
          type="email"
          autoComplete="email"
          placeholder="teacher@school.com"
        />

        {/* Passwords */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <FormField
            control={form.control}
            name="password"
            label="Password"
            type="password"
            autoComplete="new-password"
            helperText="Must be at least 8 characters"
          />
          <FormField
            control={form.control}
            name="password_confirm"
            label="Confirm password"
            type="password"
            autoComplete="new-password"
          />
        </div>

        {/* Optional fields */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <FormField
            control={form.control}
            name="employee_id"
            label="Employee ID"
          />
          <FormField
            control={form.control}
            name="department"
            label="Department"
          />
        </div>

        {/* Non-field / root errors surfaced by the server */}
        {form.formState.errors.root?.message && (
          <p className="text-sm text-red-600">
            {form.formState.errors.root.message}
          </p>
        )}

        <div className="flex items-center justify-end gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate('/admin/teachers')}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            className="bg-primary-600 hover:bg-primary-700"
            loading={mutation.isPending}
          >
            Create
          </Button>
        </div>
      </form>
    </div>
  );
};
