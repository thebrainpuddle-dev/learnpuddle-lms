// src/pages/onboarding/SignupPage.tsx
/**
 * Public tenant self-service signup page.
 * Allows new schools to create their own LMS instance.
 */

import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Button, Input } from '../../components/common';
import {
  BuildingOfficeIcon,
  EnvelopeIcon,
  UserIcon,
  LockClosedIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';
import api from '../../config/api';

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

interface SignupData {
  school_name: string;
  admin_email: string;
  admin_first_name: string;
  admin_last_name: string;
  admin_password: string;
  plan: string;
}

export const SignupPage: React.FC = () => {
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState<SignupData>({
    school_name: '',
    admin_email: '',
    admin_first_name: '',
    admin_last_name: '',
    admin_password: '',
    plan: 'FREE',
  });
  const [confirmPassword, setConfirmPassword] = useState('');
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [subdomain, setSubdomain] = useState('');

  // Fetch available plans
  const { data: plans = [] } = useQuery<Plan[]>({
    queryKey: ['plans'],
    queryFn: async () => {
      const res = await api.get('/onboarding/plans/');
      return res.data;
    },
  });

  // Check subdomain availability
  const { mutate: checkSubdomain } = useMutation({
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
    mutationFn: async (data: SignupData) => {
      const res = await api.post('/onboarding/signup/', data);
      return res.data;
    },
    onSuccess: (data) => {
      setStep(4); // Success step
    },
    onError: (error: any) => {
      const apiErrors = error.response?.data?.errors || {};
      setErrors(apiErrors);
    },
  });

  // Check subdomain when school name changes
  useEffect(() => {
    const timeout = setTimeout(() => {
      if (formData.school_name.length >= 3) {
        checkSubdomain(formData.school_name);
      }
    }, 500);
    return () => clearTimeout(timeout);
  }, [formData.school_name, checkSubdomain]);

  const updateField = (field: keyof SignupData, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    if (errors[field]) {
      setErrors(prev => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  };

  const validateStep = (stepNum: number): boolean => {
    const newErrors: Record<string, string> = {};

    if (stepNum === 1) {
      if (!formData.school_name || formData.school_name.length < 3) {
        newErrors.school_name = 'School name must be at least 3 characters';
      }
    } else if (stepNum === 2) {
      if (!formData.admin_email) {
        newErrors.admin_email = 'Email is required';
      } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.admin_email)) {
        newErrors.admin_email = 'Invalid email format';
      }
      if (!formData.admin_first_name) {
        newErrors.admin_first_name = 'First name is required';
      }
      if (!formData.admin_last_name) {
        newErrors.admin_last_name = 'Last name is required';
      }
      if (!formData.admin_password || formData.admin_password.length < 8) {
        newErrors.admin_password = 'Password must be at least 8 characters';
      }
      if (formData.admin_password !== confirmPassword) {
        newErrors.confirmPassword = 'Passwords do not match';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const nextStep = () => {
    if (validateStep(step)) {
      setStep(step + 1);
    }
  };

  const prevStep = () => {
    setStep(step - 1);
  };

  const handleSubmit = () => {
    if (validateStep(2)) {
      signup.mutate(formData);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary-50 to-secondary-50">
      {/* Header */}
      <header className="py-4 px-6">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <Link to="/" className="text-2xl font-bold text-primary-600">
            Brain LMS
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
              <Input
                label="School Name"
                value={formData.school_name}
                onChange={(e) => updateField('school_name', e.target.value)}
                leftIcon={<BuildingOfficeIcon className="w-5 h-5 text-gray-400" />}
                placeholder="Demo School"
                error={errors.school_name}
              />

              {subdomain && (
                <div className="text-sm text-gray-600">
                  Your URL will be:{' '}
                  <span className="font-medium text-primary-600">
                    {subdomain}.brainlms.com
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
                <Input
                  label="First Name"
                  value={formData.admin_first_name}
                  onChange={(e) => updateField('admin_first_name', e.target.value)}
                  leftIcon={<UserIcon className="w-5 h-5 text-gray-400" />}
                  error={errors.admin_first_name}
                />
                <Input
                  label="Last Name"
                  value={formData.admin_last_name}
                  onChange={(e) => updateField('admin_last_name', e.target.value)}
                  error={errors.admin_last_name}
                />
              </div>

              <Input
                label="Email"
                type="email"
                value={formData.admin_email}
                onChange={(e) => updateField('admin_email', e.target.value)}
                leftIcon={<EnvelopeIcon className="w-5 h-5 text-gray-400" />}
                placeholder="admin@school.com"
                error={errors.admin_email}
              />

              <Input
                label="Password"
                type="password"
                value={formData.admin_password}
                onChange={(e) => updateField('admin_password', e.target.value)}
                leftIcon={<LockClosedIcon className="w-5 h-5 text-gray-400" />}
                placeholder="Minimum 8 characters"
                error={errors.admin_password}
              />

              <Input
                label="Confirm Password"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                leftIcon={<LockClosedIcon className="w-5 h-5 text-gray-400" />}
                error={errors.confirmPassword}
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

            <div className="grid md:grid-cols-3 gap-6">
              {plans.map((plan) => (
                <div
                  key={plan.id}
                  onClick={() => updateField('plan', plan.id)}
                  className={`relative rounded-xl border-2 p-6 cursor-pointer transition-all ${
                    formData.plan === plan.id
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

            {errors.submit && (
              <p className="mt-4 text-center text-red-600">{errors.submit}</p>
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
