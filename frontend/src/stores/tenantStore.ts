import { create } from 'zustand';

import type { TenantTheme } from '../config/theme';
import { DEFAULT_THEME } from '../config/theme';

export interface TenantFeatures {
  video_upload: boolean;
  auto_quiz: boolean;
  transcripts: boolean;
  reminders: boolean;
  custom_branding: boolean;
  reports_export: boolean;
  groups: boolean;
  certificates: boolean;
}

export interface TenantLimits {
  max_teachers: number;
  max_courses: number;
  max_storage_mb: number;
  max_video_duration_minutes: number;
}

export interface TenantUsage {
  teachers: { used: number; limit: number };
  courses: { used: number; limit: number };
  storage_mb: { used: number; limit: number };
}

const DEFAULT_FEATURES: TenantFeatures = {
  video_upload: false,
  auto_quiz: false,
  transcripts: false,
  reminders: true,
  custom_branding: false,
  reports_export: false,
  groups: true,
  certificates: false,
};

interface TenantState {
  theme: TenantTheme;
  plan: string;
  features: TenantFeatures;
  limits: TenantLimits | null;
  usage: TenantUsage | null;
  setTheme: (theme: TenantTheme) => void;
  setConfig: (config: { plan?: string; features?: TenantFeatures; limits?: TenantLimits; usage?: TenantUsage }) => void;
  hasFeature: (feature: keyof TenantFeatures) => boolean;
}

export const useTenantStore = create<TenantState>((set, get) => ({
  theme: DEFAULT_THEME,
  plan: 'FREE',
  features: DEFAULT_FEATURES,
  limits: null,
  usage: null,
  setTheme: (theme) => set({ theme }),
  setConfig: (config) => set({
    plan: config.plan ?? get().plan,
    features: config.features ?? get().features,
    limits: config.limits ?? get().limits,
    usage: config.usage ?? get().usage,
  }),
  hasFeature: (feature) => get().features[feature] ?? false,
}));
