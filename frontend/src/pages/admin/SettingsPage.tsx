// src/pages/admin/SettingsPage.tsx
//
// School admin settings page — 6 sections: School Profile, Branding, Security,
// Academic, Mode & Labels, AI Provider.
// Form validation uses React Hook Form + Zod via the useZodForm hook.
//
// Security section (FE-006) uses the correct backend APIs:
//   - Password Policy: GET/PATCH /users/admin/password-policy/
//   - SAML SSO (feature-gated): GET/PATCH /users/admin/saml-config/
//   - 2FA / Session: remain on /tenants/settings/security/ (pending backend)
//
// Mode & Labels section (FE-015 / TASK-020):
//   - GET/PATCH /tenants/settings/  (mode + mode_label_overrides fields)

import React, { Fragment, useState, useRef, useEffect, useMemo } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { z } from 'zod';
import { Controller, useWatch } from 'react-hook-form';
import { Button, Input, Loading, useToast, ConfirmDialog } from '../../components/common';
import { FormField } from '../../components/common/FormField';
import { useZodForm } from '../../hooks/useZodForm';
import { useTenantStore } from '../../stores/tenantStore';
import { applyTheme } from '../../config/theme';
import api from '../../config/api';
import {
  PhotoIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ClipboardDocumentIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ShieldCheckIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  adminSettingsService,
  type PasswordPolicy,
  type SAMLConfig,
  type SAMLDefaultRole,
  type TenantModeSettings,
} from '../../services/adminSettingsService';
import {
  EDUCATION_DEFAULTS,
  CORPORATE_DEFAULTS,
  type TenantMode,
  type ModeLabelKey,
  type ModeLabels,
} from '../../stores/tenantStore';
import { buildSpUrls } from '../../utils/samlUrls';

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

// SecuritySettings (2FA / session) — legacy interface kept for the
// existing /tenants/settings/security/ endpoint until backend migrates it.
interface LegacySecuritySettings {
  two_factor_enabled: boolean;
  session_timeout_minutes: number;
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

// Legacy 2FA/session settings — endpoint may not be implemented yet.
const fetchLegacySecuritySettings = async (): Promise<LegacySecuritySettings> => {
  const response = await api.get('/tenants/settings/security/');
  return response.data;
};

const updateLegacySecuritySettings = async (
  data: Partial<LegacySecuritySettings>,
): Promise<LegacySecuritySettings> => {
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

// ── Password Policy Schema ────────────────────────────────────────────

const PasswordPolicySchema = z.object({
  min_length: z.coerce.number().int().min(6, 'Minimum 6').max(128, 'Maximum 128'),
  require_uppercase: z.boolean(),
  require_lowercase: z.boolean(),
  require_digit: z.boolean(),
  require_special: z.boolean(),
  prevent_common: z.boolean(),
  prevent_reuse_last_n: z.coerce.number().int().min(0).max(50),
  max_age_days: z.coerce.number().int().min(0, 'Use 0 for never').max(3650),
  lockout_threshold: z.coerce.number().int().min(1).max(100),
  lockout_duration_minutes: z.coerce.number().int().min(1).max(1440),
});

type PasswordPolicyData = z.infer<typeof PasswordPolicySchema>;

// ── SAML Config Schema ────────────────────────────────────────────────

const SAMLConfigSchema = z.object({
  enabled: z.boolean(),
  idp_metadata_xml: z.string(),
  idp_entity_id: z.string().max(500),
  idp_sso_url: z.string().url('Must be a valid URL').or(z.literal('')),
  idp_slo_url: z.string().url('Must be a valid URL').or(z.literal('')),
  idp_x509_cert: z.string(), // single cert for UI; sent as idp_x509_certs[0] on submit
  auto_provision: z.boolean(),
  default_role: z.enum(['TEACHER', 'HOD', 'IB_COORDINATOR', 'SCHOOL_ADMIN', 'STUDENT']),
  allowed_email_domains: z.string(),
  // Attribute mapping
  attr_email: z.string(),
  attr_first_name: z.string(),
  attr_last_name: z.string(),
  attr_groups: z.string(),
  attr_role: z.string(),
});

type SAMLConfigFormData = z.infer<typeof SAMLConfigSchema>;

// ── Tabs ──────────────────────────────────────────────────────────────

const TABS = [
  { id: 'profile' as const, label: 'School Profile' },
  { id: 'branding' as const, label: 'Branding' },
  { id: 'security' as const, label: 'Security' },
  { id: 'academic' as const, label: 'Academic' },
  { id: 'mode' as const, label: 'Mode & Labels' },
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
//
// Composed of three independent sub-cards:
//   1. PasswordPolicyCard  — GET/PATCH /users/admin/password-policy/
//   2. TwoFactor+Session   — GET/PATCH /tenants/settings/security/ (legacy)
//   3. SAMLSSOCard         — GET/PATCH /users/admin/saml-config/ (feature-gated)

// ── Helper: CopyableField ─────────────────────────────────────────────

function CopyableField({ label, value }: { label: string; value: string }) {
  const toast = useToast();
  const copy = () => {
    navigator.clipboard.writeText(value).then(() =>
      toast.success('Copied', `${label} copied to clipboard.`),
    );
  };
  return (
    <div>
      <p className="text-xs font-medium text-gray-500 mb-1">{label}</p>
      <div className="flex items-center gap-2">
        <code className="flex-1 min-w-0 truncate bg-gray-50 border border-gray-200 rounded-md px-3 py-2 text-xs text-gray-700 font-mono select-all">
          {value}
        </code>
        <button
          type="button"
          onClick={copy}
          title={`Copy ${label}`}
          className="flex-shrink-0 p-2 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
        >
          <ClipboardDocumentIcon className="h-4 w-4" aria-hidden="true" />
          <span className="sr-only">Copy {label}</span>
        </button>
      </div>
    </div>
  );
}

// ── Sub-card 1: Password Policy ───────────────────────────────────────

function PasswordPolicyCard() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const { data: policy, isLoading } = useQuery<PasswordPolicy>({
    queryKey: ['passwordPolicy'],
    queryFn: adminSettingsService.getPasswordPolicy,
    retry: false,
  });

  const form = useZodForm({
    schema: PasswordPolicySchema,
    defaultValues: {
      min_length: 12,
      require_uppercase: true,
      require_lowercase: true,
      require_digit: true,
      require_special: false,
      prevent_common: true,
      prevent_reuse_last_n: 5,
      max_age_days: 0,
      lockout_threshold: 5,
      lockout_duration_minutes: 15,
    },
  });

  // Sync server data → form once loaded
  useEffect(() => {
    if (policy) {
      form.reset({
        min_length: policy.min_length,
        require_uppercase: policy.require_uppercase,
        require_lowercase: policy.require_lowercase,
        require_digit: policy.require_digit,
        require_special: policy.require_special,
        prevent_common: policy.prevent_common,
        prevent_reuse_last_n: policy.prevent_reuse_last_n,
        max_age_days: policy.max_age_days,
        lockout_threshold: policy.lockout_threshold,
        lockout_duration_minutes: policy.lockout_duration_minutes,
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [policy]);

  const mutation = useMutation({
    mutationFn: adminSettingsService.updatePasswordPolicy,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['passwordPolicy'] });
      toast.success('Password policy saved', 'Policy has been updated.');
    },
    onError: () => {
      toast.error('Failed to save', 'Please try again.');
    },
  });

  const onSubmit = form.handleSubmit((data: PasswordPolicyData) => {
    mutation.mutate(data);
  });

  if (isLoading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6 flex justify-center">
        <Loading />
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
      <h2 className="text-lg font-semibold text-gray-900 mb-4">Password Policy</h2>

      <div className="space-y-5">
        {/* Min length */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <Controller
            control={form.control}
            name="min_length"
            render={({ field, fieldState }) => (
              <div>
                <label htmlFor="min_length" className="block text-sm font-medium text-gray-700 mb-1">
                  Minimum Length
                </label>
                <input
                  id="min_length"
                  type="number"
                  min={6}
                  max={128}
                  {...field}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
                />
                {fieldState.error && (
                  <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                )}
              </div>
            )}
          />
          <Controller
            control={form.control}
            name="max_age_days"
            render={({ field, fieldState }) => (
              <div>
                <label htmlFor="max_age_days" className="block text-sm font-medium text-gray-700 mb-1">
                  Max Age (days)
                  <span className="ml-1 text-xs text-gray-400 font-normal">0 = never expires</span>
                </label>
                <input
                  id="max_age_days"
                  type="number"
                  min={0}
                  {...field}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
                />
                {fieldState.error && (
                  <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                )}
              </div>
            )}
          />
        </div>

        {/* Character requirements */}
        <div>
          <p className="text-sm font-medium text-gray-700 mb-3">Character Requirements</p>
          <div className="space-y-3">
            {(
              [
                ['require_uppercase', 'Require uppercase letters', 'A-Z'],
                ['require_lowercase', 'Require lowercase letters', 'a-z'],
                ['require_digit', 'Require numbers', '0-9'],
                ['require_special', 'Require special characters', '!@#$%^&*'],
              ] as const
            ).map(([name, label, example]) => (
              <Controller
                key={name}
                control={form.control}
                name={name}
                render={({ field }) => (
                  <Toggle
                    enabled={field.value}
                    onChange={field.onChange}
                    label={label}
                    description={`Passwords must contain at least one: ${example}`}
                  />
                )}
              />
            ))}
          </div>
        </div>

        {/* Security options */}
        <div>
          <p className="text-sm font-medium text-gray-700 mb-3">Security Options</p>
          <div className="space-y-3">
            <Controller
              control={form.control}
              name="prevent_common"
              render={({ field }) => (
                <Toggle
                  enabled={field.value}
                  onChange={field.onChange}
                  label="Block common passwords"
                  description="Reject passwords found in common password lists"
                />
              )}
            />
          </div>
        </div>

        {/* Reuse + lockout */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <Controller
            control={form.control}
            name="prevent_reuse_last_n"
            render={({ field, fieldState }) => (
              <div>
                <label htmlFor="prevent_reuse_last_n" className="block text-sm font-medium text-gray-700 mb-1">
                  Prevent reuse of last N
                  <span className="ml-1 text-xs text-gray-400 font-normal">0 = off</span>
                </label>
                <input
                  id="prevent_reuse_last_n"
                  type="number"
                  min={0}
                  max={50}
                  {...field}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
                />
                {fieldState.error && (
                  <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                )}
              </div>
            )}
          />
          <Controller
            control={form.control}
            name="lockout_threshold"
            render={({ field, fieldState }) => (
              <div>
                <label htmlFor="lockout_threshold" className="block text-sm font-medium text-gray-700 mb-1">
                  Lockout after N attempts
                </label>
                <input
                  id="lockout_threshold"
                  type="number"
                  min={1}
                  max={100}
                  {...field}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
                />
                {fieldState.error && (
                  <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                )}
              </div>
            )}
          />
          <Controller
            control={form.control}
            name="lockout_duration_minutes"
            render={({ field, fieldState }) => (
              <div>
                <label htmlFor="lockout_duration_minutes" className="block text-sm font-medium text-gray-700 mb-1">
                  Lockout duration (min)
                </label>
                <input
                  id="lockout_duration_minutes"
                  type="number"
                  min={1}
                  max={1440}
                  {...field}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
                />
                {fieldState.error && (
                  <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                )}
              </div>
            )}
          />
        </div>
      </div>

      <div className="mt-6 flex justify-end">
        <Button
          type="submit"
          variant="primary"
          className="w-full sm:w-auto"
          loading={mutation.isPending}
        >
          Save Password Policy
        </Button>
      </div>
    </form>
  );
}

// ── Sub-card 2: 2FA + Session ─────────────────────────────────────────

function TwoFactorSessionCard() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [data, setData] = useState<LegacySecuritySettings>({
    two_factor_enabled: false,
    session_timeout_minutes: 60,
  });

  // Best-effort load — endpoint may not exist yet
  useEffect(() => {
    fetchLegacySecuritySettings()
      .then(setData)
      .catch(() => {});
  }, []);

  const mutation = useMutation({
    mutationFn: updateLegacySecuritySettings,
    onSuccess: (updated) => {
      setData(updated);
      queryClient.invalidateQueries({ queryKey: ['legacySecuritySettings'] });
      toast.success('Settings saved', '2FA and session settings updated.');
    },
    onError: () => {
      toast.error('Failed to save', 'Please try again.');
    },
  });

  return (
    <div className="space-y-4">
      {/* 2FA */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Two-Factor Authentication</h2>
        <Toggle
          enabled={data.two_factor_enabled}
          onChange={(val) => {
            const next = { ...data, two_factor_enabled: val };
            setData(next);
            mutation.mutate({ two_factor_enabled: val });
          }}
          label="Require 2FA for all teachers"
          description="Teachers will be prompted to set up an authenticator app on their next login"
        />
      </div>

      {/* Session timeout */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Session Management</h2>
        <div>
          <label htmlFor="session_timeout" className="block text-sm font-medium text-gray-700 mb-1">
            Session Timeout
          </label>
          <p className="text-xs text-gray-500 mb-2">
            Automatically log out inactive users after this duration
          </p>
          <select
            id="session_timeout"
            value={data.session_timeout_minutes}
            onChange={(e) => {
              const val = Number(e.target.value);
              const next = { ...data, session_timeout_minutes: val };
              setData(next);
              mutation.mutate({ session_timeout_minutes: val });
            }}
            className="w-full sm:w-48 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
          >
            {SESSION_TIMEOUT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

// ── Sub-card 3: SAML 2.0 SSO ─────────────────────────────────────────

const SAML_ROLE_OPTIONS: { value: SAMLDefaultRole; label: string }[] = [
  { value: 'TEACHER', label: 'Teacher' },
  { value: 'HOD', label: 'Head of Department' },
  { value: 'IB_COORDINATOR', label: 'IB Coordinator' },
  { value: 'SCHOOL_ADMIN', label: 'School Admin' },
  { value: 'STUDENT', label: 'Student' },
];


function SAMLSSOCard({ subdomain }: { subdomain: string }) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [parsing, setParsing] = useState(false);

  const {
    data: samlConfig,
    isLoading,
    isError,
    error,
  } = useQuery<SAMLConfig>({
    queryKey: ['samlConfig'],
    queryFn: adminSettingsService.getSAMLConfig,
    retry: false,
  });

  const form = useZodForm({
    schema: SAMLConfigSchema,
    defaultValues: {
      enabled: false,
      idp_metadata_xml: '',
      idp_entity_id: '',
      idp_sso_url: '',
      idp_slo_url: '',
      idp_x509_cert: '',
      auto_provision: false,
      default_role: 'TEACHER' as SAMLDefaultRole,
      allowed_email_domains: '',
      attr_email: 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress',
      attr_first_name: 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname',
      attr_last_name: 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname',
      attr_groups: 'http://schemas.microsoft.com/ws/2008/06/identity/claims/groups',
      attr_role: '',
    },
  });

  // Sync server data → form once loaded
  useEffect(() => {
    if (samlConfig) {
      form.reset({
        enabled: samlConfig.enabled,
        idp_metadata_xml: samlConfig.idp_metadata_xml,
        idp_entity_id: samlConfig.idp_entity_id,
        idp_sso_url: samlConfig.idp_sso_url,
        idp_slo_url: samlConfig.idp_slo_url,
        idp_x509_cert: samlConfig.idp_x509_certs?.[0] ?? '',
        auto_provision: samlConfig.auto_provision,
        default_role: samlConfig.default_role,
        allowed_email_domains: samlConfig.allowed_email_domains,
        attr_email: samlConfig.attribute_mapping?.email ?? 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress',
        attr_first_name: samlConfig.attribute_mapping?.first_name ?? 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname',
        attr_last_name: samlConfig.attribute_mapping?.last_name ?? 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname',
        attr_groups: samlConfig.attribute_mapping?.groups ?? 'http://schemas.microsoft.com/ws/2008/06/identity/claims/groups',
        attr_role: samlConfig.attribute_mapping?.role ?? '',
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [samlConfig]);

  const mutation = useMutation({
    mutationFn: adminSettingsService.updateSAMLConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['samlConfig'] });
      toast.success('SAML SSO saved', 'Configuration has been updated.');
    },
    onError: (err: unknown) => {
      const msg =
        typeof err === 'object' &&
        err !== null &&
        'response' in err &&
        typeof (err as { response?: { data?: { error?: string } } }).response?.data?.error === 'string'
          ? (err as { response: { data: { error: string } } }).response.data.error
          : 'Please try again.';
      toast.error('Failed to save SAML config', msg);
    },
  });

  const enabledValue = useWatch({ control: form.control, name: 'enabled' });

  const onSubmit = form.handleSubmit((data: SAMLConfigFormData) => {
    // Note: idp_metadata_xml is intentionally excluded from the save payload.
    // It is only sent in handleParseMetadata so the backend can parse it and
    // auto-fill the IdP fields. Including it here would cause the backend to
    // re-parse it on every save and silently clobber any manual edits.
    const payload = {
      enabled: data.enabled,
      idp_entity_id: data.idp_entity_id,
      idp_sso_url: data.idp_sso_url,
      idp_slo_url: data.idp_slo_url,
      idp_x509_certs: data.idp_x509_cert ? [data.idp_x509_cert] : [],
      auto_provision: data.auto_provision,
      default_role: data.default_role,
      allowed_email_domains: data.allowed_email_domains,
      attribute_mapping: {
        ...(data.attr_email ? { email: data.attr_email } : {}),
        ...(data.attr_first_name ? { first_name: data.attr_first_name } : {}),
        ...(data.attr_last_name ? { last_name: data.attr_last_name } : {}),
        ...(data.attr_groups ? { groups: data.attr_groups } : {}),
        ...(data.attr_role ? { role: data.attr_role } : {}),
      },
    };
    mutation.mutate(payload);
  });

  /** Send the metadata XML to the backend for parsing (fills idp_entity_id, urls, certs). */
  const handleParseMetadata = async () => {
    const xml = form.getValues('idp_metadata_xml');
    if (!xml.trim()) {
      toast.error('No metadata', 'Paste the IdP metadata XML first.');
      return;
    }
    setParsing(true);
    try {
      const updated = await adminSettingsService.updateSAMLConfig({ idp_metadata_xml: xml });
      form.setValue('idp_entity_id', updated.idp_entity_id);
      form.setValue('idp_sso_url', updated.idp_sso_url);
      form.setValue('idp_slo_url', updated.idp_slo_url);
      form.setValue('idp_x509_cert', updated.idp_x509_certs?.[0] ?? '');
      queryClient.invalidateQueries({ queryKey: ['samlConfig'] });
      toast.success('Metadata parsed', 'IdP fields auto-filled from metadata.');
    } catch {
      toast.error('Parse failed', 'Check that the XML is valid IdP metadata.');
    } finally {
      setParsing(false);
    }
  };

  const spUrls = buildSpUrls(subdomain, samlConfig?.sp_entity_id ?? '');

  if (isLoading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6 flex justify-center">
        <Loading />
      </div>
    );
  }

  // Extract HTTP status from AxiosError-shaped errors.
  const samlErrorStatus =
    (error as { response?: { status?: number } } | null)?.response?.status;

  if (isError) {
    const is403 = samlErrorStatus === 403;
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        {/* Header — still shown so admins know which card errored */}
        <div className="flex items-center gap-3 mb-4">
          <ShieldCheckIcon className="h-5 w-5 text-blue-600 flex-shrink-0" aria-hidden="true" />
          <div>
            <h2 className="text-lg font-semibold text-gray-900">SAML 2.0 Single Sign-On</h2>
          </div>
        </div>
        <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4">
          <ExclamationTriangleIcon
            className="h-5 w-5 text-red-500 flex-shrink-0 mt-0.5"
            aria-hidden="true"
          />
          <div>
            <p className="text-sm font-medium text-red-800">
              {is403
                ? 'SAML SSO is not enabled for this school'
                : 'Failed to load SAML configuration'}
            </p>
            <p className="mt-1 text-xs text-red-700">
              {is403
                ? 'Contact LearnPuddle support to enable SAML SSO for your account.'
                : 'Please refresh the page or try again later. If the problem persists, contact support.'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={onSubmit} noValidate className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <ShieldCheckIcon className="h-5 w-5 text-blue-600 flex-shrink-0" aria-hidden="true" />
        <div className="flex-1">
          <h2 className="text-lg font-semibold text-gray-900">SAML 2.0 Single Sign-On</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Connect LearnPuddle to your organization's identity provider (Okta, Azure AD, Google Workspace, etc.)
          </p>
        </div>
      </div>

      {/* Enable toggle */}
      <div className="mb-6">
        <Controller
          control={form.control}
          name="enabled"
          render={({ field }) => (
            <Toggle
              enabled={field.value}
              onChange={field.onChange}
              label="Enable SAML SSO"
              description="Teachers can sign in with their organizational credentials via SAML"
            />
          )}
        />
      </div>

      {enabledValue && (
        <div className="space-y-6 pt-5 border-t border-gray-100">

          {/* SP Metadata (read-only — give to IdP admin) */}
          <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
            <p className="text-sm font-medium text-blue-900 mb-3">
              Service Provider (SP) Details — Configure in your IdP
            </p>
            <div className="space-y-3">
              <CopyableField label="SP Entity ID" value={spUrls.entityId} />
              <CopyableField label="ACS URL (Assertion Consumer Service)" value={spUrls.acsUrl} />
              <CopyableField label="SLS URL (Single Logout Service)" value={spUrls.slsUrl} />
              <CopyableField label="SP Metadata URL" value={spUrls.metadataUrl} />
            </div>
          </div>

          {/* IdP Metadata XML (paste + auto-parse) */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              IdP Metadata XML
              <span className="ml-1 text-xs text-gray-400 font-normal">
                — paste here to auto-fill fields below
              </span>
            </label>
            <Controller
              control={form.control}
              name="idp_metadata_xml"
              render={({ field }) => (
                <textarea
                  {...field}
                  rows={4}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-xs font-mono focus:ring-blue-500 focus:border-blue-500 resize-y"
                  placeholder="<EntityDescriptor xmlns=&quot;urn:oasis:names:tc:SAML:2.0:metadata&quot; ...>"
                  spellCheck={false}
                />
              )}
            />
            <div className="mt-2 flex justify-end">
              <Button
                type="button"
                variant="secondary"
                className="text-sm"
                onClick={handleParseMetadata}
                loading={parsing}
              >
                <ArrowPathIcon className="h-4 w-4 mr-1.5" aria-hidden="true" />
                Parse &amp; Auto-fill
              </Button>
            </div>
          </div>

          {/* Manual IdP fields */}
          <div className="space-y-4">
            <p className="text-sm font-medium text-gray-700">IdP Configuration (Manual)</p>
            <div className="grid grid-cols-1 gap-4">
              <Controller
                control={form.control}
                name="idp_entity_id"
                render={({ field, fieldState }) => (
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">IdP Entity ID</label>
                    <input
                      {...field}
                      type="text"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
                      placeholder="https://idp.example.com/entity"
                    />
                    {fieldState.error && (
                      <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                    )}
                  </div>
                )}
              />
              <Controller
                control={form.control}
                name="idp_sso_url"
                render={({ field, fieldState }) => (
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      IdP SSO URL
                      <span className="ml-1 text-xs text-gray-400 font-normal">(SAML login endpoint)</span>
                    </label>
                    <input
                      {...field}
                      type="url"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
                      placeholder="https://idp.example.com/sso/saml"
                    />
                    {fieldState.error && (
                      <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                    )}
                  </div>
                )}
              />
              <Controller
                control={form.control}
                name="idp_slo_url"
                render={({ field, fieldState }) => (
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      IdP SLO URL
                      <span className="ml-1 text-xs text-gray-400 font-normal">(Single Logout endpoint — optional)</span>
                    </label>
                    <input
                      {...field}
                      type="url"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
                      placeholder="https://idp.example.com/slo/saml"
                    />
                    {fieldState.error && (
                      <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                    )}
                  </div>
                )}
              />
              <Controller
                control={form.control}
                name="idp_x509_cert"
                render={({ field }) => (
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">
                      IdP X.509 Certificate (PEM)
                      <span className="ml-1 text-xs text-gray-400 font-normal">
                        — used to verify assertion signatures
                      </span>
                    </label>
                    <textarea
                      {...field}
                      rows={4}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-xs font-mono focus:ring-blue-500 focus:border-blue-500 resize-y"
                      placeholder="-----BEGIN CERTIFICATE-----&#10;MIICpDCCAYwCCQD...&#10;-----END CERTIFICATE-----"
                      spellCheck={false}
                    />
                  </div>
                )}
              />
            </div>
          </div>

          {/* Provisioning */}
          <div className="space-y-4">
            <p className="text-sm font-medium text-gray-700">User Provisioning</p>
            <Controller
              control={form.control}
              name="auto_provision"
              render={({ field }) => (
                <Toggle
                  enabled={field.value}
                  onChange={field.onChange}
                  label="Auto-provision new users"
                  description="Automatically create accounts for users who authenticate via SAML but don't yet have a LearnPuddle account"
                />
              )}
            />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Controller
                control={form.control}
                name="default_role"
                render={({ field }) => (
                  <div>
                    <label htmlFor="default_role" className="block text-xs font-medium text-gray-600 mb-1">
                      Default role for new users
                    </label>
                    <select
                      id="default_role"
                      {...field}
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
                    >
                      {SAML_ROLE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              />
              <Controller
                control={form.control}
                name="allowed_email_domains"
                render={({ field }) => (
                  <div>
                    <label htmlFor="allowed_email_domains" className="block text-xs font-medium text-gray-600 mb-1">
                      Allowed email domains
                      <span className="ml-1 text-xs text-gray-400 font-normal">comma-separated; empty = any</span>
                    </label>
                    <input
                      id="allowed_email_domains"
                      {...field}
                      type="text"
                      className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-blue-500 focus:border-blue-500"
                      placeholder="school.edu, district.org"
                    />
                  </div>
                )}
              />
            </div>
          </div>

          {/* Advanced: attribute mapping */}
          <div>
            <button
              type="button"
              onClick={() => setShowAdvanced((v) => !v)}
              className="flex items-center gap-1.5 text-sm font-medium text-gray-600 hover:text-gray-900 cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
            >
              {showAdvanced ? (
                <ChevronUpIcon className="h-4 w-4" aria-hidden="true" />
              ) : (
                <ChevronDownIcon className="h-4 w-4" aria-hidden="true" />
              )}
              Advanced: Attribute Mapping
            </button>

            {showAdvanced && (
              <div className="mt-3 bg-gray-50 border border-gray-200 rounded-lg p-4 space-y-3">
                <p className="text-xs text-gray-500 mb-3">
                  Map SAML attribute URIs (from the IdP's assertion) to LearnPuddle user fields.
                  Leave blank to skip mapping for a field.
                </p>
                {(
                  [
                    ['attr_email', 'Email (required)', 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress'],
                    ['attr_first_name', 'First name', 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname'],
                    ['attr_last_name', 'Last name', 'http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname'],
                    ['attr_groups', 'Groups', 'http://schemas.microsoft.com/ws/2008/06/identity/claims/groups'],
                    ['attr_role', 'Role', ''],
                  ] as const
                ).map(([name, label, placeholder]) => (
                  <Controller
                    key={name}
                    control={form.control}
                    name={name}
                    render={({ field }) => (
                      <div className="flex items-center gap-3">
                        <span className="w-28 flex-shrink-0 text-xs font-medium text-gray-600">{label}</span>
                        <input
                          {...field}
                          type="text"
                          className="flex-1 min-w-0 px-3 py-1.5 border border-gray-300 rounded-md text-xs font-mono focus:ring-blue-500 focus:border-blue-500"
                          placeholder={placeholder || 'SAML attribute URI'}
                        />
                      </div>
                    )}
                  />
                ))}
              </div>
            )}
          </div>

          {/* Existing SP cert status */}
          {samlConfig?.sp_private_key_configured && (
            <div className="flex items-center gap-2 text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded-md px-3 py-2">
              <CheckCircleIcon className="h-4 w-4 text-emerald-500 flex-shrink-0" aria-hidden="true" />
              SP signing certificate and private key are configured.
            </div>
          )}
        </div>
      )}

      <div className="mt-6 flex justify-end">
        <Button
          type="submit"
          variant="primary"
          className="w-full sm:w-auto"
          loading={mutation.isPending}
        >
          Save SAML Configuration
        </Button>
      </div>
    </form>
  );
}

// ── Sub-card 4: SCIM 2.0 Token Management (FE-032 / TASK-023) ───────────────

const CreateTokenSchema = z.object({
  name: z
    .string()
    .min(1, 'Token name is required')
    .max(64, 'Token name must be 64 characters or fewer')
    .regex(/^[\w\s\-()]+$/, 'Only letters, numbers, spaces, hyphens, and parentheses are allowed'),
});
type CreateTokenFormData = z.infer<typeof CreateTokenSchema>;

/** Modal shown once after token creation to let the admin copy the raw value. */
function TokenRevealModal({
  tokenValue,
  onClose,
}: {
  tokenValue: string;
  onClose: () => void;
}) {
  const toast = useToast();
  const [copied, setCopied] = React.useState(false);

  const handleCopy = () => {
    Promise.resolve(navigator.clipboard.writeText(tokenValue))
      .then(() => {
        setCopied(true);
        toast.success('Token copied', 'Paste it into your IdP / HR system now — it cannot be retrieved again.');
      })
      .catch(() => {
        toast.error('Copy failed', 'Clipboard access was denied — please select and copy the token manually.');
      });
  };

  return (
    <Transition show as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/40" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-150"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
                <div className="flex items-start gap-4">
                  <div className="flex-shrink-0 p-2 rounded-full bg-green-100">
                    <CheckCircleIcon className="h-6 w-6 text-green-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <Dialog.Title className="text-lg font-semibold text-gray-900">
                      Token created — copy it now
                    </Dialog.Title>
                    <p className="mt-1 text-sm text-gray-500">
                      This token will not be shown again. Copy it and configure your
                      IdP or directory system immediately.
                    </p>
                  </div>
                </div>

                <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 p-3 flex items-start gap-2">
                  <ExclamationTriangleIcon className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-amber-700">
                    This is your only opportunity to view the raw token. It is stored as a
                    one-way hash — once you close this dialog it cannot be recovered.
                  </p>
                </div>

                <div className="mt-4">
                  <p className="text-xs font-medium text-gray-500 mb-1">Bearer token</p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 block break-all rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs font-mono text-gray-800 select-all">
                      {tokenValue}
                    </code>
                    <button
                      type="button"
                      onClick={handleCopy}
                      className="flex-shrink-0 p-2 rounded-lg border border-gray-200 hover:bg-gray-50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                      aria-label="Copy token to clipboard"
                    >
                      <ClipboardDocumentIcon
                        className={`h-4 w-4 ${copied ? 'text-green-600' : 'text-gray-500'}`}
                      />
                    </button>
                  </div>
                </div>

                <div className="mt-6 flex justify-end">
                  <Button variant="secondary" onClick={onClose} className="w-full sm:w-auto">
                    I've copied the token
                  </Button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

function SCIMTokenCard({ subdomain }: { subdomain: string }) {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [showCreateForm, setShowCreateForm] = React.useState(false);
  const [revealToken, setRevealToken] = React.useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = React.useState<{ id: string; name: string } | null>(null);

  const scimEndpoint = subdomain
    ? `https://${subdomain}.learnpuddle.com/scim/v2/`
    : `https://<your-school>.learnpuddle.com/scim/v2/`;

  // ── Queries & Mutations ─────────────────────────────────────────────
  const { data, isLoading, isError } = useQuery({
    queryKey: ['scim-tokens'],
    queryFn: adminSettingsService.listSCIMTokens,
  });

  const form = useZodForm({
    schema: CreateTokenSchema,
    defaultValues: { name: '' },
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => adminSettingsService.createSCIMToken(name),
    onSuccess: (created) => {
      // Guard: if a token is already being shown, don't overwrite it before the
      // admin has had a chance to copy it. This prevents rapid double-submit from
      // silently discarding the first token's plaintext value.
      if (revealToken) return;
      queryClient.invalidateQueries({ queryKey: ['scim-tokens'] });
      form.reset();
      setShowCreateForm(false);
      setRevealToken(created.token);
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof Error ? err.message : 'An error occurred creating the token.';
      toast.error('Failed to create SCIM token', msg);
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (tokenId: string) => adminSettingsService.revokeSCIMToken(tokenId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scim-tokens'] });
      toast.success('Token revoked', 'The SCIM token has been deactivated.');
    },
    onError: (err: unknown) => {
      const msg =
        err instanceof Error ? err.message : 'An error occurred revoking the token.';
      toast.error('Failed to revoke token', msg);
    },
  });

  const onCreateSubmit = form.handleSubmit((data: CreateTokenFormData) => {
    createMutation.mutate(data.name);
  });

  // ── Render ──────────────────────────────────────────────────────────
  const tokens = data?.results ?? [];

  return (
    <>
      <div className="rounded-xl border border-gray-200 bg-white p-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-base font-semibold text-gray-900">SCIM 2.0 Provisioning</h3>
            <p className="mt-1 text-sm text-gray-500">
              Manage bearer tokens for automated user provisioning via SCIM 2.0.
              Configure your Identity Provider (Okta, Azure AD, etc.) to use the
              endpoint below.
            </p>
          </div>
          {!showCreateForm && (
            <Button
              variant="secondary"
              className="flex-shrink-0"
              onClick={() => setShowCreateForm(true)}
            >
              Add token
            </Button>
          )}
        </div>

        {/* SCIM endpoint URL */}
        <div className="mt-4">
          <CopyableField label="SCIM Endpoint URL" value={scimEndpoint} />
        </div>

        {/* Create token form */}
        {showCreateForm && (
          <div className="mt-4 rounded-lg border border-blue-100 bg-blue-50 p-4">
            <p className="text-sm font-medium text-blue-900 mb-3">Create a new SCIM token</p>
            <form onSubmit={onCreateSubmit} className="flex items-start gap-3">
              <div className="flex-1">
                <FormField
                  control={form.control}
                  name="name"
                  label="Token name"
                  placeholder='e.g. "Okta SCIM Provisioner"'
                />
              </div>
              <div className="flex gap-2 mt-6">
                <Button
                  type="submit"
                  variant="primary"
                  loading={createMutation.isPending}
                  className="whitespace-nowrap"
                >
                  Create
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    setShowCreateForm(false);
                    form.reset();
                  }}
                >
                  Cancel
                </Button>
              </div>
            </form>
          </div>
        )}

        {/* Token list */}
        <div className="mt-4">
          {isLoading && (
            <div className="py-6 flex justify-center">
              <Loading />
            </div>
          )}
          {isError && (
            <div className="rounded-lg border border-red-100 bg-red-50 p-4 flex items-center gap-3">
              <ExclamationTriangleIcon className="h-5 w-5 text-red-500 flex-shrink-0" />
              <p className="text-sm text-red-700">Failed to load SCIM tokens. Refresh to retry.</p>
            </div>
          )}
          {!isLoading && !isError && tokens.length === 0 && (
            <p className="text-sm text-gray-400 py-4 text-center">
              No tokens yet. Create one above to start provisioning users via SCIM.
            </p>
          )}
          {!isLoading && !isError && tokens.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="py-2 pr-4 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                    <th className="py-2 pr-4 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
                    <th className="py-2 pr-4 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Last used</th>
                    <th className="py-2 pr-4 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                    <th className="py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {tokens.map((t) => (
                    <tr key={t.id} className="hover:bg-gray-50 transition-colors">
                      <td className="py-2.5 pr-4 font-medium text-gray-900">{t.name}</td>
                      <td className="py-2.5 pr-4 text-gray-500 whitespace-nowrap">
                        {new Date(t.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-2.5 pr-4 text-gray-500 whitespace-nowrap">
                        {t.last_used_at
                          ? new Date(t.last_used_at).toLocaleDateString()
                          : <span className="text-gray-300">Never</span>}
                      </td>
                      <td className="py-2.5 pr-4">
                        <span
                          className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                            t.is_active
                              ? 'bg-green-100 text-green-700'
                              : 'bg-gray-100 text-gray-500'
                          }`}
                        >
                          {t.is_active ? 'Active' : 'Revoked'}
                        </span>
                      </td>
                      <td className="py-2.5 text-right">
                        {t.is_active && (
                          <button
                            type="button"
                            onClick={() => setRevokeTarget({ id: t.id, name: t.name })}
                            className="text-xs text-red-500 hover:text-red-700 hover:underline transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-red-400 rounded cursor-pointer"
                          >
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Token reveal modal (shown once after creation) */}
      {revealToken && (
        <TokenRevealModal
          tokenValue={revealToken}
          onClose={() => setRevealToken(null)}
        />
      )}

      {/* Revoke confirmation dialog */}
      <ConfirmDialog
        isOpen={revokeTarget !== null}
        onClose={() => setRevokeTarget(null)}
        onConfirm={() => {
          if (revokeTarget) {
            revokeMutation.mutate(revokeTarget.id);
          }
          setRevokeTarget(null);
        }}
        title="Revoke SCIM token"
        message={`Revoking "${revokeTarget?.name}" will immediately stop any SCIM provisioning using this token. This cannot be undone.`}
        confirmLabel="Revoke token"
        cancelLabel="Keep active"
        variant="danger"
        loading={revokeMutation.isPending}
      />
    </>
  );
}

// ── Section: Security (top-level) ─────────────────────────────────────

function SecuritySection() {
  const { features, theme } = useTenantStore();

  return (
    <div data-tour="security-2fa-section" className="space-y-6">
      <PasswordPolicyCard />
      <TwoFactorSessionCard />
      {features.saml && (
        <SAMLSSOCard subdomain={theme.subdomain ?? ''} />
      )}
      <SCIMTokenCard subdomain={theme.subdomain ?? ''} />
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

// ── Section: Mode & Labels (FE-015 / TASK-020) ───────────────────────────────

/** All label keys alongside their human-readable form names for the settings UI. */
const MODE_LABEL_META: Array<{ key: ModeLabelKey; name: string; description: string }> = [
  { key: 'learner',        name: 'Learner (singular)',  description: 'e.g. "Teacher" or "Employee"' },
  { key: 'learner_plural', name: 'Learner (plural)',    description: 'e.g. "Teachers" or "Employees"' },
  { key: 'course',         name: 'Course (singular)',   description: 'e.g. "Course" or "Training Program"' },
  { key: 'course_plural',  name: 'Course (plural)',     description: 'e.g. "Courses" or "Training Programs"' },
  { key: 'module',         name: 'Module',              description: 'Section within a course' },
  { key: 'lesson',         name: 'Lesson',              description: 'Individual content item' },
  { key: 'assignment',     name: 'Assignment',          description: 'Graded task' },
  { key: 'badge',          name: 'Badge',               description: 'Gamification achievement' },
  { key: 'league',         name: 'League',              description: 'Competitive grouping' },
  { key: 'xp',             name: 'XP label',            description: 'Experience point currency label' },
  { key: 'streak',         name: 'Streak',              description: 'Consecutive-day activity label' },
  { key: 'dashboard',      name: 'Dashboard',           description: 'Main overview page title' },
];

function ModeSwitchSection() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { setModeLabels } = useTenantStore();

  const [currentMode, setCurrentMode] = useState<TenantMode>('education');
  const [overrides, setOverrides] = useState<Partial<ModeLabels>>({});
  const [isFetched, setIsFetched] = useState(false);

  // Load current mode settings
  const { isLoading } = useQuery({
    queryKey: ['tenantModeSettings'],
    queryFn: adminSettingsService.getModeSettings,
    retry: false,
  });

  // Populate local state once the query resolves
  useEffect(() => {
    adminSettingsService.getModeSettings()
      .then((data: TenantModeSettings) => {
        setCurrentMode(data.mode);
        setOverrides(data.mode_label_overrides ?? {});
        setIsFetched(true);
      })
      .catch(() => {
        setIsFetched(true);
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveMutation = useMutation({
    mutationFn: (payload: { mode: TenantMode; mode_label_overrides: Partial<ModeLabels> }) =>
      adminSettingsService.updateModeSettings(payload),
    onSuccess: (data: TenantModeSettings) => {
      const merged: ModeLabels = { ...EDUCATION_DEFAULTS, ...(data.mode_labels as Partial<ModeLabels>) };
      setModeLabels(data.mode, merged);
      queryClient.invalidateQueries({ queryKey: ['tenantModeSettings'] });
      toast.success('Mode settings saved', 'Label changes are now live across the platform.');
    },
    onError: () => {
      toast.error('Failed to save', 'Please try again.');
    },
  });

  // Effective preview labels: mode defaults + current overrides (not yet saved)
  const modeDefaults = currentMode === 'education' ? EDUCATION_DEFAULTS : CORPORATE_DEFAULTS;
  const previewLabels: ModeLabels = { ...modeDefaults, ...overrides } as ModeLabels;

  const handleModeChange = (newMode: TenantMode) => {
    setCurrentMode(newMode);
    // Clear overrides when switching modes so the user sees clean defaults
    setOverrides({});
  };

  const handleOverrideChange = (key: ModeLabelKey, value: string) => {
    setOverrides((prev) => {
      const next = { ...prev };
      const defaultForMode = (currentMode === 'education' ? EDUCATION_DEFAULTS : CORPORATE_DEFAULTS)[key];
      if (value === '' || value === defaultForMode) {
        // Remove override — let the default win
        delete next[key];
      } else {
        next[key] = value;
      }
      return next;
    });
  };

  const handleSave = () => {
    saveMutation.mutate({ mode: currentMode, mode_label_overrides: overrides });
  };

  const handleResetOverrides = () => {
    setOverrides({});
  };

  if (isLoading && !isFetched) {
    return (
      <div className="flex justify-center py-12">
        <Loading />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Mode selector */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-1">Platform Mode</h2>
        <p className="text-sm text-gray-500 mb-5">
          Switch between Education and Corporate mode to adapt the terminology used throughout
          the platform. Custom label overrides are applied on top of the mode defaults.
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Education option */}
          <button
            type="button"
            onClick={() => handleModeChange('education')}
            className={`relative rounded-xl border-2 p-4 text-left transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 cursor-pointer ${
              currentMode === 'education'
                ? 'border-indigo-500 bg-indigo-50'
                : 'border-gray-200 hover:border-gray-300'
            }`}
          >
            {currentMode === 'education' && (
              <span className="absolute top-3 right-3">
                <CheckCircleIcon className="h-5 w-5 text-indigo-600" />
              </span>
            )}
            <p className="font-semibold text-gray-900 text-sm">Education</p>
            <p className="text-xs text-gray-500 mt-1">
              Uses school terminology: Teachers, Courses, Badges, Leagues
            </p>
          </button>

          {/* Corporate option */}
          <button
            type="button"
            onClick={() => handleModeChange('corporate')}
            className={`relative rounded-xl border-2 p-4 text-left transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 cursor-pointer ${
              currentMode === 'corporate'
                ? 'border-indigo-500 bg-indigo-50'
                : 'border-gray-200 hover:border-gray-300'
            }`}
          >
            {currentMode === 'corporate' && (
              <span className="absolute top-3 right-3">
                <CheckCircleIcon className="h-5 w-5 text-indigo-600" />
              </span>
            )}
            <p className="font-semibold text-gray-900 text-sm">Corporate</p>
            <p className="text-xs text-gray-500 mt-1">
              Uses corporate terminology: Employees, Training Programs, Achievements, Tiers
            </p>
          </button>
        </div>
      </div>

      {/* Label overrides */}
      <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-1">
          <h2 className="text-lg font-semibold text-gray-900">Label Overrides</h2>
          {Object.keys(overrides).length > 0 && (
            <button
              type="button"
              onClick={handleResetOverrides}
              className="text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1 transition-colors cursor-pointer"
            >
              <ArrowPathIcon className="h-3.5 w-3.5" />
              Reset to mode defaults
            </button>
          )}
        </div>
        <p className="text-sm text-gray-500 mb-5">
          Customise individual labels. Leave a field empty or matching its default to remove
          the override. Changes are previewed in the &quot;Effective&quot; column.
        </p>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100">
                <th className="text-left pb-3 font-medium text-gray-600 w-36">Label</th>
                <th className="text-left pb-3 font-medium text-gray-600 w-36">Mode Default</th>
                <th className="text-left pb-3 font-medium text-gray-600">Custom Override</th>
                <th className="text-left pb-3 font-medium text-gray-600 w-36">Effective</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {MODE_LABEL_META.map(({ key, name, description }) => {
                const defaultVal = modeDefaults[key];
                const overrideVal = overrides[key] ?? '';
                const effective = previewLabels[key];
                const isOverridden = Boolean(overrides[key]);

                return (
                  <tr key={key} className="group">
                    <td className="py-3 pr-4 align-top">
                      <p className="font-medium text-gray-800">{name}</p>
                      <p className="text-[11px] text-gray-400 mt-0.5">{description}</p>
                    </td>
                    <td className="py-3 pr-4 align-middle">
                      <span className="text-gray-500">{defaultVal}</span>
                    </td>
                    <td className="py-3 pr-4 align-middle">
                      <input
                        type="text"
                        value={overrideVal}
                        onChange={(e) => handleOverrideChange(key, e.target.value)}
                        placeholder={defaultVal}
                        className="w-full rounded-lg border border-gray-200 px-3 py-1.5 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-colors"
                        aria-label={`Override for ${name}`}
                        data-testid={`override-${key}`}
                      />
                    </td>
                    <td className="py-3 align-middle">
                      <span
                        className={`font-medium ${isOverridden ? 'text-indigo-600' : 'text-gray-700'}`}
                        data-testid={`effective-${key}`}
                      >
                        {effective}
                      </span>
                      {isOverridden && (
                        <span className="ml-1.5 text-[10px] bg-indigo-100 text-indigo-700 rounded px-1 py-0.5 align-middle">
                          custom
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Save */}
      <div className="flex justify-end gap-3">
        <Button
          variant="primary"
          onClick={handleSave}
          disabled={saveMutation.isPending}
          className="min-w-[120px]"
        >
          {saveMutation.isPending ? 'Saving…' : 'Save Mode & Labels'}
        </Button>
      </div>
    </div>
  );
}

// ── Section: AI Provider ─────────────────────────────────────────────────────

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
      {activeTab === 'mode' && <ModeSwitchSection />}
      {activeTab === 'ai' && <AIProviderSection />}
    </div>
  );
};
