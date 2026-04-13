// src/pages/admin/SettingsPage.tsx
//
// School admin settings page — 4 sections: School Profile, Branding, Security, Academic.
// Form validation uses React Hook Form + Zod via the useZodForm hook.

import React, { useState, useRef, useEffect, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import { Button, Input, Loading, useToast } from '../../components/common';
import { FormField } from '../../components/common/FormField';
import { useZodForm } from '../../hooks/useZodForm';
import { useTenantStore } from '../../stores/tenantStore';
import { applyTheme } from '../../config/theme';
import api from '../../config/api';
import {
  PhotoIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';

// ── Types ─────────────────────────────────────────────────────────────

interface TenantSettings {
  id: string;
  name: string;
  subdomain: string;
  email: string;
  phone: string;
  address: string;
  logo: string | null;
  logo_url: string | null;
  primary_color: string;
  secondary_color: string;
  font_family: string;
  is_active: boolean;
  is_trial: boolean;
  trial_end_date: string | null;
}

interface SecuritySettings {
  password_min_length: number;
  password_require_uppercase: boolean;
  password_require_lowercase: boolean;
  password_require_numbers: boolean;
  password_require_special: boolean;
  two_factor_enabled: boolean;
  session_timeout_minutes: number;
  sso_enabled: boolean;
  sso_provider: string;
  sso_client_id: string;
  sso_client_secret: string;
}

// ── API ───────────────────────────────────────────────────────────────

const fetchTenantSettings = async (): Promise<TenantSettings> => {
  const response = await api.get('/tenants/settings/');
  return response.data;
};

const updateTenantSettings = async (data: FormData): Promise<TenantSettings> => {
  const response = await api.patch('/tenants/settings/', data);
  return response.data;
};

const fetchSecuritySettings = async (): Promise<SecuritySettings> => {
  // TODO: Update endpoint when backend is ready
  const response = await api.get('/tenants/settings/security/');
  return response.data;
};

const updateSecuritySettings = async (data: Partial<SecuritySettings>): Promise<SecuritySettings> => {
  // TODO: Update endpoint when backend is ready
  const response = await api.patch('/tenants/settings/security/', data);
  return response.data;
};

// ── Constants ─────────────────────────────────────────────────────────

const FONT_OPTIONS = [
  'Inter',
  'Roboto',
  'Open Sans',
  'Lato',
  'Montserrat',
  'Poppins',
  'Source Sans Pro',
  'Nunito',
  'Raleway',
  'Ubuntu',
];

const SESSION_TIMEOUT_OPTIONS = [
  { value: 30, label: '30 minutes' },
  { value: 60, label: '1 hour' },
  { value: 120, label: '2 hours' },
  { value: 240, label: '4 hours' },
  { value: 480, label: '8 hours' },
];

const SSO_PROVIDER_OPTIONS = [
  { value: '', label: 'Select provider...' },
  { value: 'google', label: 'Google Workspace' },
  { value: 'microsoft', label: 'Microsoft Azure AD' },
  { value: 'okta', label: 'Okta' },
  { value: 'saml', label: 'Custom SAML' },
];

// ── Zod Schemas ──────────────────────────────────────────────────────

const ProfileSchema = z.object({
  name: z.string().min(1, 'School name is required').max(200),
  email: z.string().email('Enter a valid email address').or(z.literal('')).default(''),
  phone: z.string().max(20).default(''),
  address: z.string().max(500).default(''),
});

type ProfileData = z.infer<typeof ProfileSchema>;

const BrandingSchema = z.object({
  primary_color: z
    .string()
    .regex(/^#[0-9A-Fa-f]{6}$/, 'Must be a valid hex color (e.g. #1F4788)')
    .default('#1F4788'),
  secondary_color: z
    .string()
    .regex(/^(#[0-9A-Fa-f]{6})?$/, 'Must be a valid hex color')
    .optional()
    .default(''),
  font_family: z.string().min(1).default('Inter'),
});

type BrandingData = z.infer<typeof BrandingSchema>;

const AcademicSchema = z.object({
  current_academic_year: z.string().max(20).default(''),
  id_prefix: z.string().max(10).default(''),
  white_label: z.boolean().default(false),
  welcome_message: z.string().max(200).default(''),
  school_motto: z.string().max(200).default(''),
  login_bg_image_url: z.string().url('Must be a valid URL').or(z.literal('')).default(''),
});

type AcademicData = z.infer<typeof AcademicSchema>;

// ── Tabs ──────────────────────────────────────────────────────────────

const TABS = [
  { id: 'profile' as const, label: 'School Profile' },
  { id: 'branding' as const, label: 'Branding' },
  { id: 'security' as const, label: 'Security' },
  { id: 'academic' as const, label: 'Academic' },
  { id: 'ai' as const, label: 'AI Provider' },
];

type TabId = (typeof TABS)[number]['id'];

// ── Toggle Component ─────────────────────────────────────────────────

function Toggle({
  enabled,
  onChange,
  label,
  description,
}: {
  enabled: boolean;
  onChange: (val: boolean) => void;
  label: string;
  description?: string;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex-1 mr-4">
        <p className="text-sm font-medium text-gray-700">{label}</p>
        {description && (
          <p className="text-xs text-gray-500 mt-0.5">{description}</p>
        )}
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        onClick={() => onChange(!enabled)}
        className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 ${
          enabled ? 'bg-indigo-600' : 'bg-gray-200'
        }`}
      >
        <span
          className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
            enabled ? 'translate-x-5' : 'translate-x-0'
          }`}
        />
      </button>
    </div>
  );
}

// ── Section: School Profile ──────────────────────────────────────────

function SchoolProfileSection({
  settings,
}: {
  settings: TenantSettings;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();

  const form = useZodForm({
    schema: ProfileSchema,
    defaultValues: {
      name: settings.name || '',
      email: (settings as any).email || '',
      phone: (settings as any).phone || '',
      address: (settings as any).address || '',
    },
  });

  useEffect(() => {
    form.reset({
      name: settings.name || '',
      email: (settings as any).email || '',
      phone: (settings as any).phone || '',
      address: (settings as any).address || '',
    });
  }, [settings, form]);

  const mutation = useMutation({
    mutationFn: updateTenantSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tenantSettings'] });
      toast.success('Profile saved', 'School profile has been updated.');
    },
    onError: () => {
      toast.error('Failed to save', 'Please try again.');
    },
  });

  const onSubmit = form.handleSubmit((data: ProfileData) => {
    const fd = new FormData();
    fd.append('name', data.name);
    fd.append('email', data.email || '');
    fd.append('phone', data.phone || '');
    fd.append('address', data.address || '');
    mutation.mutate(fd);
  });

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          School Profile
        </h2>

        <div className="space-y-4">
          <FormField
            control={form.control}
            name="name"
            label="School Name"
            placeholder="Enter school name"
          />

          <FormField
            control={form.control}
            name="email"
            label="Email"
            type="email"
            placeholder="admin@school.com"
          />

          <FormField
            control={form.control}
            name="phone"
            label="Phone"
            type="tel"
            placeholder="+91 98765 43210"
          />

          <Controller
            control={form.control}
            name="address"
            render={({ field, fieldState }) => (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Address
                </label>
                <textarea
                  {...field}
                  value={field.value ?? ''}
                  rows={3}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
                  placeholder="School address"
                />
                {fieldState.error && (
                  <p className="mt-1 text-sm text-red-600">
                    {fieldState.error.message}
                  </p>
                )}
              </div>
            )}
          />

          {/* Subdomain (read-only) */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Subdomain
            </label>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
              <span className="inline-flex h-10 items-center rounded-md border border-gray-300 bg-gray-50 px-3 text-sm text-gray-500 sm:rounded-l-md sm:rounded-r-none sm:border-r-0">
                https://
              </span>
              <input
                type="text"
                value={settings.subdomain || ''}
                disabled
                className="block w-full min-w-0 flex-1 rounded-md border border-gray-300 bg-gray-100 px-3 py-2 text-sm text-gray-500 cursor-not-allowed sm:rounded-none"
              />
              <span className="inline-flex h-10 items-center rounded-md border border-gray-300 bg-gray-50 px-3 text-sm text-gray-500 sm:rounded-l-none sm:rounded-r-md sm:border-l-0">
                .
                {(
                  process.env.REACT_APP_PLATFORM_DOMAIN || 'learnpuddle.com'
                ).replace(':3000', '')}
              </span>
            </div>
            <p className="mt-1 text-xs text-gray-500">
              Contact support to change your subdomain
            </p>
          </div>
        </div>
      </div>

      <div className="flex justify-end">
        <Button
          type="submit"
          variant="primary"
          className="w-full sm:w-auto"
          loading={mutation.isPending}
        >
          Save Profile
        </Button>
      </div>
    </form>
  );
}

// ── Section: Branding ────────────────────────────────────────────────

function BrandingSection({ settings }: { settings: TenantSettings }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { setTheme } = useTenantStore();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(
    settings.logo_url || null
  );

  const form = useZodForm({
    schema: BrandingSchema,
    defaultValues: {
      primary_color: settings.primary_color || '#1F4788',
      secondary_color: settings.secondary_color || '',
      font_family: settings.font_family || 'Inter',
    },
  });

  const watchedValues = form.watch();

  useEffect(() => {
    form.reset({
      primary_color: settings.primary_color || '#1F4788',
      secondary_color: settings.secondary_color || '',
      font_family: settings.font_family || 'Inter',
    });
    if (settings.logo_url) {
      setLogoPreview(settings.logo_url);
    }
  }, [settings, form]);

  const mutation = useMutation({
    mutationFn: updateTenantSettings,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['tenantSettings'] });
      queryClient.invalidateQueries({ queryKey: ['tenantTheme'] });

      const newTheme = {
        name: data.name,
        subdomain: data.subdomain,
        logo: data.logo_url || undefined,
        primaryColor: data.primary_color,
        secondaryColor: data.secondary_color || data.primary_color,
        fontFamily: data.font_family || 'Inter',
        tenantFound: true,
      };
      setTheme(newTheme);
      applyTheme(newTheme);

      toast.success('Branding saved', 'Your branding has been updated.');
    },
    onError: () => {
      toast.error('Failed to save branding', 'Please try again.');
    },
  });

  const handleLogoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setLogoFile(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setLogoPreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const onSubmit = form.handleSubmit((data: BrandingData) => {
    const fd = new FormData();
    fd.append('primary_color', data.primary_color);
    fd.append('secondary_color', data.secondary_color || '');
    fd.append('font_family', data.font_family);

    if (logoFile) {
      fd.append('logo', logoFile);
    }

    mutation.mutate(fd);
  });

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      <div data-tour="admin-settings-branding" className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Branding</h2>

        <div className="space-y-6">
          {/* Logo Upload */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              School Logo
            </label>
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:space-x-4">
              <div
                className="w-24 h-24 border-2 border-dashed border-gray-300 rounded-lg flex items-center justify-center overflow-hidden bg-gray-50 cursor-pointer hover:border-indigo-500 transition-colors"
                onClick={() => fileInputRef.current?.click()}
              >
                {logoPreview ? (
                  <img
                    src={logoPreview}
                    alt="Logo preview"
                    className="w-full h-full object-contain"
                  />
                ) : (
                  <PhotoIcon className="h-10 w-10 text-gray-400" />
                )}
              </div>
              <div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => fileInputRef.current?.click()}
                >
                  Upload Logo
                </Button>
                <p className="mt-1 text-xs text-gray-500">
                  PNG, JPG up to 2MB
                </p>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/jpg"
                onChange={handleLogoChange}
                className="hidden"
              />
            </div>
          </div>

          {/* Colors */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Controller
              control={form.control}
              name="primary_color"
              render={({ field, fieldState }) => (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Primary Color
                  </label>
                  <div className="flex items-center space-x-2">
                    <input
                      type="color"
                      value={field.value}
                      onChange={(e) => field.onChange(e.target.value)}
                      className="h-10 w-14 rounded border border-gray-300 cursor-pointer"
                    />
                    <input
                      type="text"
                      value={field.value}
                      onChange={(e) => field.onChange(e.target.value)}
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
                      placeholder="#1F4788"
                    />
                  </div>
                  {fieldState.error && (
                    <p className="mt-1 text-sm text-red-600">
                      {fieldState.error.message}
                    </p>
                  )}
                </div>
              )}
            />

            <Controller
              control={form.control}
              name="secondary_color"
              render={({ field, fieldState }) => (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Secondary Color
                  </label>
                  <div className="flex items-center space-x-2">
                    <input
                      type="color"
                      value={field.value || watchedValues.primary_color}
                      onChange={(e) => field.onChange(e.target.value)}
                      className="h-10 w-14 rounded border border-gray-300 cursor-pointer"
                    />
                    <input
                      type="text"
                      value={field.value || ''}
                      onChange={(e) => field.onChange(e.target.value)}
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
                      placeholder="#2E5C8A"
                    />
                  </div>
                  {fieldState.error && (
                    <p className="mt-1 text-sm text-red-600">
                      {fieldState.error.message}
                    </p>
                  )}
                </div>
              )}
            />
          </div>

          {/* Font Family */}
          <Controller
            control={form.control}
            name="font_family"
            render={({ field }) => (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Font Family
                </label>
                <select
                  value={field.value}
                  onChange={(e) => field.onChange(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
                >
                  {FONT_OPTIONS.map((font) => (
                    <option key={font} value={font} style={{ fontFamily: font }}>
                      {font}
                    </option>
                  ))}
                </select>
              </div>
            )}
          />

          {/* Live Preview */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Preview
            </label>
            <div
              className="p-4 rounded-lg border border-gray-200"
              style={{ fontFamily: watchedValues.font_family }}
            >
              <div className="flex items-center mb-3">
                {logoPreview && (
                  <img
                    src={logoPreview}
                    alt="Logo"
                    className="h-8 w-auto mr-2"
                  />
                )}
                <span
                  className="text-lg font-bold"
                  style={{ color: watchedValues.primary_color }}
                >
                  {settings.name || 'School Name'}
                </span>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:space-x-2">
                <button
                  type="button"
                  className="px-4 py-2 rounded-lg text-white text-sm font-medium"
                  style={{ backgroundColor: watchedValues.primary_color }}
                >
                  Primary Button
                </button>
                <button
                  type="button"
                  className="px-4 py-2 rounded-lg text-white text-sm font-medium"
                  style={{
                    backgroundColor:
                      watchedValues.secondary_color ||
                      watchedValues.primary_color,
                  }}
                >
                  Secondary Button
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="flex justify-end">
        <Button
          type="submit"
          variant="primary"
          className="w-full sm:w-auto"
          loading={mutation.isPending}
        >
          Save Branding
        </Button>
      </div>
    </form>
  );
}

// ── Section: Security ────────────────────────────────────────────────

function SecuritySection() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [securityData, setSecurityData] = useState<SecuritySettings>({
    password_min_length: 8,
    password_require_uppercase: true,
    password_require_lowercase: true,
    password_require_numbers: true,
    password_require_special: false,
    two_factor_enabled: false,
    session_timeout_minutes: 60,
    sso_enabled: false,
    sso_provider: '',
    sso_client_id: '',
    sso_client_secret: '',
  });

  const { isLoading } = useQuery({
    queryKey: ['securitySettings'],
    queryFn: fetchSecuritySettings,
    // Use retry: false since the endpoint may not exist yet
    retry: false,
  });

  // Attempt to load saved security settings (will use defaults if endpoint not ready)
  useEffect(() => {
    fetchSecuritySettings()
      .then((data) => setSecurityData(data))
      .catch(() => {
        // Security settings endpoint may not exist yet — defaults are already set
      });
  }, []);

  const mutation = useMutation({
    mutationFn: updateSecuritySettings,
    onSuccess: (data) => {
      setSecurityData(data);
      queryClient.invalidateQueries({ queryKey: ['securitySettings'] });
      toast.success('Security saved', 'Security settings have been updated.');
    },
    onError: () => {
      toast.error('Failed to save', 'Please try again.');
    },
  });

  const handleSave = () => {
    mutation.mutate(securityData);
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loading />
      </div>
    );
  }

  return (
    <div data-tour="security-2fa-section" className="space-y-6">
      {/* Password Policy */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Password Policy
        </h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Minimum Password Length
            </label>
            <select
              value={securityData.password_min_length}
              onChange={(e) =>
                setSecurityData((prev) => ({
                  ...prev,
                  password_min_length: Number(e.target.value),
                }))
              }
              className="w-full sm:w-48 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
            >
              {[6, 8, 10, 12, 14, 16].map((len) => (
                <option key={len} value={len}>
                  {len} characters
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-3">
            <Toggle
              enabled={securityData.password_require_uppercase}
              onChange={(val) =>
                setSecurityData((prev) => ({
                  ...prev,
                  password_require_uppercase: val,
                }))
              }
              label="Require uppercase letters"
              description="Passwords must contain at least one uppercase letter (A-Z)"
            />
            <Toggle
              enabled={securityData.password_require_lowercase}
              onChange={(val) =>
                setSecurityData((prev) => ({
                  ...prev,
                  password_require_lowercase: val,
                }))
              }
              label="Require lowercase letters"
              description="Passwords must contain at least one lowercase letter (a-z)"
            />
            <Toggle
              enabled={securityData.password_require_numbers}
              onChange={(val) =>
                setSecurityData((prev) => ({
                  ...prev,
                  password_require_numbers: val,
                }))
              }
              label="Require numbers"
              description="Passwords must contain at least one number (0-9)"
            />
            <Toggle
              enabled={securityData.password_require_special}
              onChange={(val) =>
                setSecurityData((prev) => ({
                  ...prev,
                  password_require_special: val,
                }))
              }
              label="Require special characters"
              description="Passwords must contain at least one special character (!@#$%^&*)"
            />
          </div>
        </div>
      </div>

      {/* Two-Factor Authentication */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Two-Factor Authentication
        </h2>
        <Toggle
          enabled={securityData.two_factor_enabled}
          onChange={(val) =>
            setSecurityData((prev) => ({ ...prev, two_factor_enabled: val }))
          }
          label="Enable 2FA for all teachers"
          description="When enabled, all teachers will be required to set up two-factor authentication on their next login"
        />
      </div>

      {/* Session Timeout */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Session Management
        </h2>
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">
            Session Timeout
          </label>
          <p className="text-xs text-gray-500 mb-2">
            Automatically log out inactive users after this duration
          </p>
          <select
            value={securityData.session_timeout_minutes}
            onChange={(e) =>
              setSecurityData((prev) => ({
                ...prev,
                session_timeout_minutes: Number(e.target.value),
              }))
            }
            className="w-full sm:w-48 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
          >
            {SESSION_TIMEOUT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* SSO Configuration */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Single Sign-On (SSO)
        </h2>
        <div className="space-y-4">
          <Toggle
            enabled={securityData.sso_enabled}
            onChange={(val) =>
              setSecurityData((prev) => ({ ...prev, sso_enabled: val }))
            }
            label="Enable SSO"
            description="Allow teachers to sign in using their organizational identity provider"
          />

          {securityData.sso_enabled && (
            <div className="space-y-4 pt-4 border-t border-gray-100">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  SSO Provider
                </label>
                <select
                  value={securityData.sso_provider}
                  onChange={(e) =>
                    setSecurityData((prev) => ({
                      ...prev,
                      sso_provider: e.target.value,
                    }))
                  }
                  className="w-full sm:w-64 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
                >
                  {SSO_PROVIDER_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {securityData.sso_provider && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Client ID
                    </label>
                    <input
                      type="text"
                      value={securityData.sso_client_id}
                      onChange={(e) =>
                        setSecurityData((prev) => ({
                          ...prev,
                          sso_client_id: e.target.value,
                        }))
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
                      placeholder="Enter client ID"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Client Secret
                    </label>
                    <input
                      type="password"
                      value={securityData.sso_client_secret}
                      onChange={(e) =>
                        setSecurityData((prev) => ({
                          ...prev,
                          sso_client_secret: e.target.value,
                        }))
                      }
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
                      placeholder="Enter client secret"
                    />
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Save button */}
      <div className="flex justify-end">
        <Button
          type="button"
          variant="primary"
          className="w-full sm:w-auto"
          loading={mutation.isPending}
          onClick={handleSave}
        >
          Save Security Settings
        </Button>
      </div>
    </div>
  );
}

// ── Section: Academic ─────────────────────────────────────────────────

function AcademicSection({
  settings,
}: {
  settings: TenantSettings;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();

  const form = useZodForm({
    schema: AcademicSchema,
    defaultValues: {
      current_academic_year: (settings as any).current_academic_year || '',
      id_prefix: (settings as any).id_prefix || '',
      white_label: (settings as any).white_label || false,
      welcome_message: (settings as any).welcome_message || '',
      school_motto: (settings as any).school_motto || '',
      login_bg_image_url: (settings as any).login_bg_image_url || '',
    },
  });

  useEffect(() => {
    form.reset({
      current_academic_year: (settings as any).current_academic_year || '',
      id_prefix: (settings as any).id_prefix || '',
      white_label: (settings as any).white_label || false,
      welcome_message: (settings as any).welcome_message || '',
      school_motto: (settings as any).school_motto || '',
      login_bg_image_url: (settings as any).login_bg_image_url || '',
    });
  }, [settings, form]);

  const mutation = useMutation({
    mutationFn: updateTenantSettings,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tenantSettings'] });
      toast.success('Academic settings saved', 'Academic configuration has been updated.');
    },
    onError: () => {
      toast.error('Failed to save', 'Please try again.');
    },
  });

  const onSubmit = form.handleSubmit((data: AcademicData) => {
    const fd = new FormData();
    fd.append('current_academic_year', data.current_academic_year || '');
    fd.append('id_prefix', data.id_prefix || '');
    fd.append('white_label', String(data.white_label));
    fd.append('welcome_message', data.welcome_message || '');
    fd.append('school_motto', data.school_motto || '');
    fd.append('login_bg_image_url', data.login_bg_image_url || '');
    mutation.mutate(fd);
  });

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      {/* Academic Configuration */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Academic Configuration
        </h2>

        <div className="space-y-4">
          <FormField
            control={form.control}
            name="current_academic_year"
            label="Current Academic Year"
            placeholder="2026-27"
          />

          <div>
            <FormField
              control={form.control}
              name="id_prefix"
              label="ID Prefix"
              placeholder="KIS"
              maxLength={10}
            />
            <p className="mt-1 text-xs text-gray-500">
              Used for auto-generated student/teacher IDs (e.g., KIS-S-0001)
            </p>
          </div>
        </div>
      </div>

      {/* White-Label Branding */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          White-Label Branding
        </h2>

        <div className="space-y-4">
          <Controller
            control={form.control}
            name="white_label"
            render={({ field }) => (
              <Toggle
                enabled={field.value}
                onChange={field.onChange}
                label="White Label"
                description="Enable custom branding on the login page"
              />
            )}
          />

          <FormField
            control={form.control}
            name="welcome_message"
            label="Welcome Message"
            placeholder="Welcome to Keystone Learning"
          />

          <FormField
            control={form.control}
            name="school_motto"
            label="School Motto"
            placeholder="Powered by the Idea-Loom Model"
          />

          <div>
            <FormField
              control={form.control}
              name="login_bg_image_url"
              label="Login Background Image URL"
              placeholder="https://example.com/bg.jpg"
            />
            <p className="mt-1 text-xs text-gray-500">
              URL for the login page background image (white-label only)
            </p>
          </div>
        </div>
      </div>

      <div className="flex justify-end">
        <Button
          type="submit"
          variant="primary"
          className="w-full sm:w-auto"
          loading={mutation.isPending}
        >
          Save Academic Settings
        </Button>
      </div>
    </form>
  );
}

// ── Section: AI Provider ──────────────────────────────────────────────

interface AIProviderConfig {
  llm_provider: string;
  llm_model: string;
  llm_api_key: string;
  llm_base_url: string;
  tts_provider: string;
  tts_api_key: string;
  tts_voice_id: string;
  image_provider: string;
  image_api_key: string;
  maic_enabled: boolean;
  max_classrooms_per_teacher: number;
}

const AI_DEFAULT: AIProviderConfig = {
  llm_provider: 'openai',
  llm_model: 'gpt-4o',
  llm_api_key: '',
  llm_base_url: '',
  tts_provider: 'disabled',
  tts_api_key: '',
  tts_voice_id: '',
  image_provider: 'disabled',
  image_api_key: '',
  maic_enabled: false,
  max_classrooms_per_teacher: 20,
};

const LLM_PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'google', label: 'Google' },
  { value: 'openrouter', label: 'OpenRouter' },
  { value: 'azure', label: 'Azure OpenAI' },
];

const TTS_PROVIDERS = [
  { value: 'disabled', label: 'Disabled' },
  { value: 'openai', label: 'OpenAI TTS' },
  { value: 'elevenlabs', label: 'ElevenLabs' },
  { value: 'azure', label: 'Azure TTS' },
  { value: 'edge', label: 'Edge TTS' },
];

const IMAGE_PROVIDERS = [
  { value: 'disabled', label: 'Disabled' },
  { value: 'openai', label: 'OpenAI (DALL-E)' },
  { value: 'stability', label: 'Stability AI' },
];

function AIProviderSection() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [config, setConfig] = useState<AIProviderConfig>(AI_DEFAULT);
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null);

  const { isLoading } = useQuery({
    queryKey: ['aiProviderSettings'],
    queryFn: async () => {
      const res = await api.get('/tenants/settings/ai/');
      return res.data as AIProviderConfig;
    },
    retry: false,
  });

  useEffect(() => {
    api.get('/tenants/settings/ai/')
      .then((res) => setConfig({ ...AI_DEFAULT, ...res.data }))
      .catch(() => {
        // AI settings endpoint may not exist yet — defaults are set
      });
  }, []);

  const saveMutation = useMutation({
    mutationFn: async (data: AIProviderConfig) => {
      const res = await api.patch('/tenants/settings/ai/', data);
      return res.data;
    },
    onSuccess: (data) => {
      setConfig({ ...AI_DEFAULT, ...data });
      queryClient.invalidateQueries({ queryKey: ['aiProviderSettings'] });
      toast.success('AI settings saved', 'AI provider configuration has been updated.');
    },
    onError: () => {
      toast.error('Failed to save', 'Please try again.');
    },
  });

  const testMutation = useMutation({
    mutationFn: async () => {
      const res = await api.post('/tenants/settings/ai/test/', {
        llm_provider: config.llm_provider,
        llm_model: config.llm_model,
        llm_api_key: config.llm_api_key,
        llm_base_url: config.llm_base_url,
      });
      return res.data as { ok: boolean; message: string };
    },
    onSuccess: (data) => {
      setTestResult(data);
    },
    onError: () => {
      setTestResult({ ok: false, message: 'Connection test failed. Check your credentials.' });
    },
  });

  const handleSave = () => {
    saveMutation.mutate(config);
  };

  const update = (field: keyof AIProviderConfig, value: string | boolean | number) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
    setTestResult(null);
  };

  if (isLoading) {
    return (
      <div className="flex justify-center py-12">
        <Loading />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* LLM Provider */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">LLM Provider</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Provider</label>
            <select
              value={config.llm_provider}
              onChange={(e) => update('llm_provider', e.target.value)}
              className="w-full sm:w-64 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
            >
              {LLM_PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Model Name</label>
            <input
              type="text"
              value={config.llm_model}
              onChange={(e) => update('llm_model', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
              placeholder="e.g., gpt-4o, claude-sonnet-4-20250514, gemini-pro"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">API Key</label>
            <input
              type="password"
              value={config.llm_api_key}
              onChange={(e) => update('llm_api_key', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
              placeholder="sk-..."
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Base URL <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <input
              type="text"
              value={config.llm_base_url}
              onChange={(e) => update('llm_base_url', e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
              placeholder="https://api.openai.com/v1"
            />
            <p className="mt-1 text-xs text-gray-500">
              Override the default API base URL (for Azure, proxies, or self-hosted models)
            </p>
          </div>

          {/* Test Connection */}
          <div className="flex items-center gap-3 pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              loading={testMutation.isPending}
              onClick={() => testMutation.mutate()}
            >
              Test Connection
            </Button>
            {testResult && (
              <div className={`flex items-center gap-1.5 text-sm ${testResult.ok ? 'text-green-600' : 'text-red-600'}`}>
                {testResult.ok ? (
                  <CheckCircleIcon className="h-4 w-4" />
                ) : (
                  <ExclamationTriangleIcon className="h-4 w-4" />
                )}
                <span>{testResult.message}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* TTS Provider */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Text-to-Speech</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">TTS Provider</label>
            <select
              value={config.tts_provider}
              onChange={(e) => update('tts_provider', e.target.value)}
              className="w-full sm:w-64 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
            >
              {TTS_PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>

          {config.tts_provider !== 'disabled' && config.tts_provider !== 'edge' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">TTS API Key</label>
              <input
                type="password"
                value={config.tts_api_key}
                onChange={(e) => update('tts_api_key', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
                placeholder="TTS API key"
              />
            </div>
          )}

          {config.tts_provider !== 'disabled' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Voice ID</label>
              <input
                type="text"
                value={config.tts_voice_id}
                onChange={(e) => update('tts_voice_id', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
                placeholder="e.g., alloy, TX3LPaxmHKxFdv7VOQHJ"
              />
            </div>
          )}
        </div>
      </div>

      {/* Image Provider */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Image Generation</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Image Provider</label>
            <select
              value={config.image_provider}
              onChange={(e) => update('image_provider', e.target.value)}
              className="w-full sm:w-64 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
            >
              {IMAGE_PROVIDERS.map((p) => (
                <option key={p.value} value={p.value}>{p.label}</option>
              ))}
            </select>
          </div>

          {config.image_provider !== 'disabled' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Image API Key</label>
              <input
                type="password"
                value={config.image_api_key}
                onChange={(e) => update('image_api_key', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
                placeholder="Image generation API key"
              />
            </div>
          )}
        </div>
      </div>

      {/* MAIC Settings */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">AI Classroom (MAIC)</h2>
        <div className="space-y-4">
          <Toggle
            enabled={config.maic_enabled}
            onChange={(val) => update('maic_enabled', val)}
            label="Enable AI Classroom"
            description="Allow teachers to create AI-powered interactive classrooms"
          />

          {config.maic_enabled && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Max Classrooms per Teacher
              </label>
              <input
                type="number"
                min={1}
                max={100}
                value={config.max_classrooms_per_teacher}
                onChange={(e) => update('max_classrooms_per_teacher', Number(e.target.value) || 20)}
                className="w-full sm:w-32 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-indigo-500 focus:border-indigo-500"
              />
              <p className="mt-1 text-xs text-gray-500">
                Maximum number of AI Classrooms each teacher can create
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Save button */}
      <div className="flex justify-end">
        <Button
          type="button"
          variant="primary"
          className="w-full sm:w-auto"
          loading={saveMutation.isPending}
          onClick={handleSave}
        >
          Save AI Settings
        </Button>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────

export const SettingsPage: React.FC = () => {
  usePageTitle('Settings');
  const [searchParams] = useSearchParams();
  const initialTab = useMemo(() => {
    const t = searchParams.get('tab');
    return t && TABS.some((tab) => tab.id === t) ? (t as TabId) : 'profile';
  }, []);
  const [activeTab, setActiveTab] = useState<TabId>(initialTab);

  const {
    data: settings,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['tenantSettings'],
    queryFn: fetchTenantSettings,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loading />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <div className="flex items-center">
          <ExclamationTriangleIcon className="h-5 w-5 text-red-500 mr-2" />
          <p className="text-red-700">
            Failed to load settings. Please try again.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="mt-1 text-gray-500">
          Manage your school profile, branding, security, and academic settings
        </p>
      </div>

      {/* Tab navigation */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === tab.id
                  ? 'border-indigo-500 text-indigo-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      {activeTab === 'profile' && settings && (
        <SchoolProfileSection settings={settings} />
      )}
      {activeTab === 'branding' && settings && (
        <BrandingSection settings={settings} />
      )}
      {activeTab === 'security' && <SecuritySection />}
      {activeTab === 'academic' && settings && (
        <AcademicSection settings={settings} />
      )}
      {activeTab === 'ai' && <AIProviderSection />}
    </div>
  );
};
