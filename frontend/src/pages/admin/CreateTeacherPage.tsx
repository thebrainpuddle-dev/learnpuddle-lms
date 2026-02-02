import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { useToast } from '../../components/common';
import { adminTeachersService } from '../../services/adminTeachersService';
import axios from 'axios';

// Type for field-level validation errors from backend
interface FieldErrors {
  [key: string]: string[];
}

// Helper to extract first error message for a field
function getFieldError(errors: FieldErrors | null, field: string): string | undefined {
  if (!errors || !errors[field]) return undefined;
  return errors[field][0];
}

export const CreateTeacherPage: React.FC = () => {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [fieldErrors, setFieldErrors] = useState<FieldErrors | null>(null);

  const [form, setForm] = useState({
    email: '',
    first_name: '',
    last_name: '',
    password: '',
    password_confirm: '',
    employee_id: '',
    department: '',
  });

  const mutation = useMutation({
    mutationFn: () => adminTeachersService.createTeacher(form),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['adminTeachers'] });
      toast.success('Teacher created', `${form.first_name} ${form.last_name} has been added.`);
      navigate('/admin/teachers');
    },
    onError: (error) => {
      // Extract field-level errors from axios response
      if (axios.isAxiosError(error) && error.response?.data) {
        setFieldErrors(error.response.data as FieldErrors);
        toast.error('Validation error', 'Please check the form and correct any errors.');
      } else {
        setFieldErrors(null);
        toast.error('Failed to create teacher', 'Please try again.');
      }
    },
  });

  // Clear field error when user types
  const handleChange = (field: string, value: string) => {
    setForm({ ...form, [field]: value });
    if (fieldErrors && fieldErrors[field]) {
      setFieldErrors({ ...fieldErrors, [field]: [] });
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Create Teacher</h1>
        <p className="mt-1 text-sm text-gray-500">Create a new teacher under this tenant.</p>
      </div>

      <div className="card space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="First name"
            value={form.first_name}
            onChange={(e) => handleChange('first_name', e.target.value)}
            error={getFieldError(fieldErrors, 'first_name')}
          />
          <Input
            label="Last name"
            value={form.last_name}
            onChange={(e) => handleChange('last_name', e.target.value)}
            error={getFieldError(fieldErrors, 'last_name')}
          />
        </div>
        <Input
          label="Email"
          type="email"
          value={form.email}
          onChange={(e) => handleChange('email', e.target.value)}
          error={getFieldError(fieldErrors, 'email')}
        />
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="Password"
            type="password"
            value={form.password}
            onChange={(e) => handleChange('password', e.target.value)}
            error={getFieldError(fieldErrors, 'password')}
            helperText="Must be at least 8 characters"
          />
          <Input
            label="Confirm password"
            type="password"
            value={form.password_confirm}
            onChange={(e) => handleChange('password_confirm', e.target.value)}
            error={getFieldError(fieldErrors, 'password_confirm')}
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Input
            label="Employee ID"
            value={form.employee_id}
            onChange={(e) => handleChange('employee_id', e.target.value)}
            error={getFieldError(fieldErrors, 'employee_id')}
          />
          <Input
            label="Department"
            value={form.department}
            onChange={(e) => handleChange('department', e.target.value)}
            error={getFieldError(fieldErrors, 'department')}
          />
        </div>

        {/* Show non-field errors (e.g., general errors) */}
        {mutation.isError && fieldErrors?.non_field_errors && (
          <div className="text-sm text-red-600">
            {fieldErrors.non_field_errors[0]}
          </div>
        )}

        <div className="flex items-center justify-end gap-3">
          <Button variant="outline" onClick={() => navigate('/admin/teachers')}>
            Cancel
          </Button>
          <Button
            variant="primary"
            className="bg-primary-600 hover:bg-primary-700"
            loading={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            Create
          </Button>
        </div>
      </div>
    </div>
  );
};

