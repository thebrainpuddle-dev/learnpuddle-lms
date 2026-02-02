// src/pages/admin/SettingsPage.tsx

import React, { useState, useRef, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Input, Loading, useToast } from '../../components/common';
import { useTenantStore } from '../../stores/tenantStore';
import { applyTheme } from '../../config/theme';
import api from '../../config/api';
import {
  PhotoIcon,
  CheckCircleIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';

interface TenantSettings {
  id: string;
  name: string;
  subdomain: string;
  logo: string | null;
  logo_url: string | null;
  primary_color: string;
  secondary_color: string;
  font_family: string;
  is_active: boolean;
  is_trial: boolean;
  trial_end_date: string | null;
}

const fetchTenantSettings = async (): Promise<TenantSettings> => {
  const response = await api.get('/tenants/settings/');
  return response.data;
};

const updateTenantSettings = async (data: FormData): Promise<TenantSettings> => {
  const response = await api.patch('/tenants/settings/', data, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

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

export const SettingsPage: React.FC = () => {
  const toast = useToast();
  const queryClient = useQueryClient();
  const { setTheme } = useTenantStore();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [formData, setFormData] = useState({
    name: '',
    primary_color: '#1F4788',
    secondary_color: '',
    font_family: 'Inter',
  });
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState('');

  const { data: settings, isLoading, error } = useQuery({
    queryKey: ['tenantSettings'],
    queryFn: fetchTenantSettings,
  });

  // Populate form when settings data loads
  useEffect(() => {
    if (settings) {
      setFormData({
        name: settings.name,
        primary_color: settings.primary_color || '#1F4788',
        secondary_color: settings.secondary_color || '',
        font_family: settings.font_family || 'Inter',
      });
      if (settings.logo_url) {
        setLogoPreview(settings.logo_url);
      }
    }
  }, [settings]);

  const mutation = useMutation({
    mutationFn: updateTenantSettings,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['tenantSettings'] });
      queryClient.invalidateQueries({ queryKey: ['tenantTheme'] });
      
      // Update the theme store and apply immediately
      const newTheme = {
        name: data.name,
        subdomain: data.subdomain,
        logo: data.logo_url || undefined,
        primaryColor: data.primary_color,
        secondaryColor: data.secondary_color || data.primary_color,
        fontFamily: data.font_family || 'Inter',
      };
      setTheme(newTheme);
      applyTheme(newTheme);
      
      toast.success('Settings saved', 'Your branding has been updated.');
      setSuccessMessage('Settings saved successfully!');
      setTimeout(() => setSuccessMessage(''), 3000);
    },
    onError: () => {
      toast.error('Failed to save settings', 'Please try again.');
    },
  });

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({ ...prev, [name]: value }));
  };

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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    
    const data = new FormData();
    data.append('name', formData.name);
    data.append('primary_color', formData.primary_color);
    data.append('secondary_color', formData.secondary_color);
    data.append('font_family', formData.font_family);
    
    if (logoFile) {
      data.append('logo', logoFile);
    }
    
    mutation.mutate(data);
  };

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
          <p className="text-red-700">Failed to load settings. Please try again.</p>
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
          Manage your school's branding and appearance
        </p>
      </div>

      {/* Success Message */}
      {successMessage && (
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="flex items-center">
            <CheckCircleIcon className="h-5 w-5 text-green-500 mr-2" />
            <p className="text-green-700">{successMessage}</p>
          </div>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* General Settings */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">General</h2>
          
          <div className="space-y-4">
            <Input
              label="School Name"
              name="name"
              value={formData.name}
              onChange={handleInputChange}
              placeholder="Enter school name"
            />
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Subdomain
              </label>
              <div className="flex items-center">
                <span className="inline-flex items-center px-3 rounded-l-md border border-r-0 border-gray-300 bg-gray-50 text-gray-500 text-sm h-10">
                  https://
                </span>
                <input
                  type="text"
                  value={settings?.subdomain || ''}
                  disabled
                  className="flex-1 min-w-0 block w-full px-3 py-2 rounded-none border border-gray-300 bg-gray-100 text-gray-500 text-sm cursor-not-allowed"
                />
                <span className="inline-flex items-center px-3 rounded-r-md border border-l-0 border-gray-300 bg-gray-50 text-gray-500 text-sm h-10">
                  .lms.com
                </span>
              </div>
              <p className="mt-1 text-xs text-gray-500">Contact support to change your subdomain</p>
            </div>
          </div>
        </div>

        {/* Branding Settings */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Branding</h2>
          
          <div className="space-y-6">
            {/* Logo Upload */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                School Logo
              </label>
              <div className="flex items-center space-x-4">
                <div
                  className="w-24 h-24 border-2 border-dashed border-gray-300 rounded-lg flex items-center justify-center overflow-hidden bg-gray-50 cursor-pointer hover:border-primary-500 transition-colors"
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
                  <p className="mt-1 text-xs text-gray-500">PNG, JPG up to 2MB</p>
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
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Primary Color
                </label>
                <div className="flex items-center space-x-2">
                  <input
                    type="color"
                    name="primary_color"
                    value={formData.primary_color}
                    onChange={handleInputChange}
                    className="h-10 w-14 rounded border border-gray-300 cursor-pointer"
                  />
                  <input
                    type="text"
                    name="primary_color"
                    value={formData.primary_color}
                    onChange={handleInputChange}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-primary-500 focus:border-primary-500"
                    placeholder="#1F4788"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Secondary Color
                </label>
                <div className="flex items-center space-x-2">
                  <input
                    type="color"
                    name="secondary_color"
                    value={formData.secondary_color || formData.primary_color}
                    onChange={handleInputChange}
                    className="h-10 w-14 rounded border border-gray-300 cursor-pointer"
                  />
                  <input
                    type="text"
                    name="secondary_color"
                    value={formData.secondary_color}
                    onChange={handleInputChange}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-primary-500 focus:border-primary-500"
                    placeholder="#2E5C8A"
                  />
                </div>
              </div>
            </div>

            {/* Font Family */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Font Family
              </label>
              <select
                name="font_family"
                value={formData.font_family}
                onChange={handleInputChange}
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-primary-500 focus:border-primary-500"
              >
                {FONT_OPTIONS.map((font) => (
                  <option key={font} value={font} style={{ fontFamily: font }}>
                    {font}
                  </option>
                ))}
              </select>
            </div>

            {/* Preview */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Preview
              </label>
              <div
                className="p-4 rounded-lg border border-gray-200"
                style={{ fontFamily: formData.font_family }}
              >
                <div className="flex items-center mb-3">
                  {logoPreview && (
                    <img src={logoPreview} alt="Logo" className="h-8 w-auto mr-2" />
                  )}
                  <span
                    className="text-lg font-bold"
                    style={{ color: formData.primary_color }}
                  >
                    {formData.name || 'School Name'}
                  </span>
                </div>
                <div className="flex space-x-2">
                  <button
                    type="button"
                    className="px-4 py-2 rounded-lg text-white text-sm font-medium"
                    style={{ backgroundColor: formData.primary_color }}
                  >
                    Primary Button
                  </button>
                  <button
                    type="button"
                    className="px-4 py-2 rounded-lg text-white text-sm font-medium"
                    style={{ backgroundColor: formData.secondary_color || formData.primary_color }}
                  >
                    Secondary Button
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Account Info (read-only) */}
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Account</h2>
          
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Status
              </label>
              <span
                className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                  settings?.is_active
                    ? 'bg-green-100 text-green-800'
                    : 'bg-red-100 text-red-800'
                }`}
              >
                {settings?.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Plan
              </label>
              <span
                className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                  settings?.is_trial
                    ? 'bg-yellow-100 text-yellow-800'
                    : 'bg-blue-100 text-blue-800'
                }`}
              >
                {settings?.is_trial ? 'Trial' : 'Premium'}
              </span>
              {settings?.is_trial && settings?.trial_end_date && (
                <p className="mt-1 text-xs text-gray-500">
                  Trial ends: {new Date(settings.trial_end_date).toLocaleDateString()}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Submit */}
        <div className="flex justify-end">
          <Button
            type="submit"
            variant="primary"
            loading={mutation.isPending}
          >
            Save Changes
          </Button>
        </div>
      </form>
    </div>
  );
};
