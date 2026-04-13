// src/pages/onboarding/SignupPage.tsx
/**
 * Public tenant self-service signup page.
 * Allows new schools to create their own LMS instance.
 *
 * Form management uses React Hook Form + Zod for type-safe validation.
 */

import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import { Button, Input } from '../../components/common';
import { FormField } from '../../components/common/FormField';
import { useZodForm } from '../../hooks/useZodForm';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  BuildingOfficeIcon,
  EnvelopeIcon,
  UserIcon,
  LockClosedIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';
import api from '../../config/api';

// ── Types ─────────────────────────────────────────────────────────────

interface Plan {
  id: string;
  name: string;
  price: number;
  price_yearly: number;
  max_teachers: number;
  max_courses: number;
  max_storage_mb: number;
  features: string[];
  recommended: boolean;
}

// ── Zod Schema ────────────────────────────────────────────────────────

const SignupSchema = z
  .object({
    school_name: z.string().min(3, 'School name must be at least 3 characters'),
    admin_email: z.string().min(1, 'Email is required').email('Invalid email format'),
    admin_first_name: z.string().min(1, 'First name is required'),
    admin_last_name: z.string().min(1, 'Last name is required'),
    admin_password: z.string().min(8, 'Password must be at least 8 characters'),
    confirm_password: z.string().min(1, 'Please confirm your password'),
    plan: z.string().default('FREE'),
  })
  .refine((data) => data.admin_password === data.confirm_password, {
    path: ['confirm_password'],
    message: 'Passwords do not match',
  });

type SignupData = z.infer<typeof SignupSchema>;

// ── Component ─────────────────────────────────────────────────────────

export const SignupPage: React.FC = () => {
  usePageTitle('Sign Up');
  const [step, setStep] = useState(1);
  const [subdomain, setSubdomain] = useState('');

  const form = useZodForm({
    schema: SignupSchema,
    defaultValues: {
      school_name: '',
      admin_email: '',
      admin_first_name: '',
      admin_last_name: '',
      admin_password: '',
      confirm_password: '',
      plan: 'FREE',
    },
  });

  const watchedSchoolName = form.watch('school_name');
  const watchedPlan = form.watch('plan');

  // Fetch available plans
  const { data: plans = [] } = useQuery<Plan[]>({
    queryKey: ['plans'],
    queryFn: async () => {
      const res = await api.get('/onboarding/plans/');
      return res.data;
    },
  });

  // Check subdomain availability
  const checkSubdomain = useMutation({
    mutationFn: async (name: string) => {
      const res = await api.get(`/onboarding/check-subdomain/?name=${encodeURIComponent(name)}`);
      return res.data;
    },
    onSuccess: (data) => {
      setSubdomain(data.suggested_subdomain);
    },
  });

  // Submit signup
  const signup = useMutation({
    mutationFn: async (data: Omit<SignupData, 'confirm_password'>) => {
      const res = await api.post('/onboarding/signup/', data);
      return res.data;
    },
    onSuccess: () => {
      setStep(4);
    },
    onError: (error: any) => {
      const apiErrors = error.response?.data?.errors || {};
      // Merge server errors into form state
      (Object.keys(apiErrors) as Array<keyof SignupData>).forEach((field) => {
        const msg = apiErrors[field as string];
        if (typeof msg === 'string') {
          form.setError(field, { type: 'server', message: msg });
        } else if (Array.isArray(msg) && msg.length > 0) {
          form.setError(field, { type: 'server', message: msg[0] });
        }
      });
    },
  });

  // Check subdomain when school name changes
  useEffect(() => {
    const timeout = setTimeout(() => {
      if (watchedSchoolName && watchedSchoolName.length >= 3) {
        checkSubdomain.mutate(watchedSchoolName);
      }
    }, 500);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watchedSchoolName]);

  // Validate only specific step fields before proceeding
  const nextStep = async () => {
    let valid = false;
    if (step === 1) {
      valid = await form.trigger(['school_name']);
    } else if (step === 2) {
      valid = await form.trigger([
        'admin_email',
        'admin_first_name',
        'admin_last_name',
        'admin_password',
        'confirm_password',
      ]);
    }
    if (valid) {
      setStep(step + 1);
    }
  };

  const prevStep = () => {
    setStep(step - 1);
  };

  const handleSubmit = async () => {
    const valid = await form.trigger();
    if (valid) {
      const values = form.getValues();
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const { confirm_password, ...payload } = values;
      signup.mutate(payload);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 to-secondary-50">
      {/* Header */}
      <header className="py-4 px-6">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <Link to="/" className="text-2xl font-bold text-primary-600">
            LearnPuddle
          </Link>
          <Link to="/login" className="text-sm text-gray-600 hover:text-primary-600">
            Already have an account? Sign in
          </Link>
        </div>
      </header>

      <main className="max-w-4xl mx-auto py-12 px-4">
        {/* Progress indicator */}
        <div className="mb-8">
          <div className="flex items-center justify-center space-x-4">
            {[1, 2, 3].map((s) => (
              <React.Fragment key={s}>
                <div
                  className={`w-10 h-10 rounded-full flex items-center justify-center text-sm font-medium ${
                    s < step
                      ? 'bg-primary-600 text-white'
                      : s === step
                      ? 'bg-primary-100 text-primary-600 border-2 border-primary-600'
                      : 'bg-gray-200 text-gray-500'
                  }`}
                >
                  {s < step ? <CheckCircleIcon className="w-6 h-6" /> : s}
                </div>
                {s < 3 && (
                  <div
                    className={`w-24 h-1 ${
                      s < step ? 'bg-primary-600' : 'bg-gray-200'
                    }`}
                  />
                )}
              </React.Fragment>
            ))}
          </div>
          <div className="flex justify-center mt-2 space-x-12">
            <span className="text-xs text-gray-600">School Info</span>
            <span className="text-xs text-gray-600">Admin Account</span>
            <span className="text-xs text-gray-600">Select Plan</span>
          </div>
        </div>

        {/* Step 1: School Information */}
        {step === 1 && (
          <div className="bg-white rounded-xl shadow-lg p-8 max-w-md mx-auto">
            <h2 className="text-2xl font-bold text-gray-900 mb-2">
              Create your school's LMS
            </h2>
            <p className="text-gray-600 mb-6">
              Start by entering your school or organization name.
            </p>

            <div className="space-y-4">
              <FormField
                control={form.control}
                name="school_name"
                label="School Name"
                leftIcon={<BuildingOfficeIcon className="w-5 h-5 text-gray-400" />}
                placeholder="Demo School"
              />

              {subdomain && (
                <div className="text-sm text-gray-600">
                  Your URL will be:{' '}
                  <span className="font-medium text-primary-600">
                    {subdomain}.{(process.env.REACT_APP_PLATFORM_DOMAIN || 'learnpuddle.com').replace(':3000', '')}
                  </span>
                </div>
              )}
            </div>

            <div className="mt-8">
              <Button
                onClick={nextStep}
                variant="primary"
                size="lg"
                fullWidth
              >
                Continue
              </Button>
            </div>
          </div>
        )}

        {/* Step 2: Admin Account */}
        {step === 2 && (
          <div className="bg-white rounded-xl shadow-lg p-8 max-w-md mx-auto">
            <h2 className="text-2xl font-bold text-gray-900 mb-2">
              Create admin account
            </h2>
            <p className="text-gray-600 mb-6">
              This will be the administrator account for your school.
            </p>

            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="admin_first_name"
                  label="First Name"
                  leftIcon={<UserIcon className="w-5 h-5 text-gray-400" />}
                />
                <FormField
                  control={form.control}
                  name="admin_last_name"
                  label="Last Name"
                />
              </div>

              <FormField
                control={form.control}
                name="admin_email"
                label="Email"
                type="email"
                leftIcon={<EnvelopeIcon className="w-5 h-5 text-gray-400" />}
                placeholder="admin@school.com"
              />

              <FormField
                control={form.control}
                name="admin_password"
                label="Password"
                type="password"
                leftIcon={<LockClosedIcon className="w-5 h-5 text-gray-400" />}
                placeholder="Minimum 8 characters"
              />

              <FormField
                control={form.control}
                name="confirm_password"
                label="Confirm Password"
                type="password"
                leftIcon={<LockClosedIcon className="w-5 h-5 text-gray-400" />}
              />
            </div>

            <div className="mt-8 flex space-x-4">
              <Button onClick={prevStep} variant="outline" size="lg">
                Back
              </Button>
              <Button onClick={nextStep} variant="primary" size="lg" fullWidth>
                Continue
              </Button>
            </div>
          </div>
        )}

        {/* Step 3: Plan Selection */}
        {step === 3 && (
          <div className="bg-white rounded-xl shadow-lg p-8">
            <h2 className="text-2xl font-bold text-gray-900 mb-2 text-center">
              Choose your plan
            </h2>
            <p className="text-gray-600 mb-8 text-center">
              Start free and upgrade anytime. All plans include a 14-day trial.
            </p>

            <Controller
              control={form.control}
              name="plan"
              render={({ field }) => (
                <div className="grid md:grid-cols-3 gap-6">
                  {plans.map((plan) => (
                    <div
                      key={plan.id}
                      onClick={() => field.onChange(plan.id)}
                      className={`relative rounded-xl border-2 p-6 cursor-pointer transition-all ${
                        field.value === plan.id
                          ? 'border-primary-600 bg-primary-50'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      {plan.recommended && (
                        <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                          <span className="bg-primary-600 text-white text-xs px-3 py-1 rounded-full">
                            Recommended
                          </span>
                        </div>
                      )}

                      <h3 className="text-lg font-semibold text-gray-900">
                        {plan.name}
                      </h3>
                      <div className="mt-2">
                        <span className="text-3xl font-bold text-gray-900">
                          ${plan.price}
                        </span>
                        <span className="text-gray-500">/month</span>
                      </div>

                      <ul className="mt-4 space-y-2">
                        {plan.features.map((feature, i) => (
                          <li key={i} className="flex items-start text-sm">
                            <CheckCircleIcon className="w-5 h-5 text-green-500 mr-2 flex-shrink-0" />
                            <span className="text-gray-600">{feature}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ))}
                </div>
              )}
            />

            <div className="mt-8 flex justify-center space-x-4">
              <Button onClick={prevStep} variant="outline" size="lg">
                Back
              </Button>
              <Button
                onClick={handleSubmit}
                variant="primary"
                size="lg"
                loading={signup.isPending}
              >
                Create Account
              </Button>
            </div>

            {form.formState.errors.root?.message && (
              <p className="mt-4 text-center text-red-600">
                {form.formState.errors.root.message}
              </p>
            )}
          </div>
        )}

        {/* Step 4: Success */}
        {step === 4 && signup.data && (
          <div className="bg-white rounded-xl shadow-lg p-8 max-w-md mx-auto text-center">
            <div className="w-16 h-16 bg-green-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <CheckCircleIcon className="w-10 h-10 text-green-600" />
            </div>

            <h2 className="text-2xl font-bold text-gray-900 mb-2">
              Account Created!
            </h2>
            <p className="text-gray-600 mb-6">
              {signup.data.message}
            </p>

            <div className="bg-gray-50 rounded-lg p-4 mb-6">
              <p className="text-sm text-gray-600 mb-1">Your school URL:</p>
              <a
                href={signup.data.login_url}
                className="text-primary-600 font-medium hover:underline"
              >
                {signup.data.login_url}
              </a>
            </div>

            <a
              href={signup.data.login_url}
              className="w-full inline-flex items-center justify-center px-4 py-3 bg-primary-600 text-white font-medium rounded-lg hover:bg-primary-700 transition-colors"
            >
              Go to Login
            </a>
          </div>
        )}
      </main>
    </div>
  );
};

export default SignupPage;
