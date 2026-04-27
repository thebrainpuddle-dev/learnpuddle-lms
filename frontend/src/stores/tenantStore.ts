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
  teacher_authoring: boolean;
  ai_studio: boolean;
  maic: boolean;
  /** SAML 2.0 SSO (per TASK-045). Distinct from OAuth-style `sso`. */
  saml: boolean;
  /** OAuth-style SSO (Google, Microsoft, Okta). */
  sso: boolean;
  /** TOTP-based 2FA for teachers. */
  '2fa': boolean;
  /** Student portal access. */
  students: boolean;
}

// ── Mode Labels (TASK-020: Education vs Corporate mode switching) ─────────────

/** All label keys exposed by the backend MODE_LABEL_DEFAULTS map. */
export type ModeLabelKey =
  | 'learner'
  | 'learner_plural'
  | 'course'
  | 'course_plural'
  | 'module'
  | 'lesson'
  | 'assignment'
  | 'badge'
  | 'league'
  | 'xp'
  | 'streak'
  | 'dashboard';

export type TenantMode = 'education' | 'corporate';

/** Merged label map returned by `Tenant.get_mode_labels()` on the backend. */
export type ModeLabels = Record<ModeLabelKey, string>;

/** Fallback education defaults — mirrors backend `MODE_LABEL_DEFAULTS['education']`. */
export const EDUCATION_DEFAULTS: ModeLabels = {
  learner: 'Teacher',
  learner_plural: 'Teachers',
  course: 'Course',
  course_plural: 'Courses',
  module: 'Module',
  lesson: 'Lesson',
  assignment: 'Assignment',
  badge: 'Badge',
  league: 'League',
  xp: 'XP',
  streak: 'Streak',
  dashboard: 'Dashboard',
};

/** Fallback corporate defaults — mirrors backend `MODE_LABEL_DEFAULTS['corporate']`. */
export const CORPORATE_DEFAULTS: ModeLabels = {
  learner: 'Employee',
  learner_plural: 'Employees',
  course: 'Training Program',
  course_plural: 'Training Programs',
  module: 'Module',
  lesson: 'Task',
  assignment: 'Task',
  badge: 'Achievement',
  league: 'Tier',
  xp: 'Points',
  streak: 'Streak',
  dashboard: 'Workspace',
};

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
  teacher_authoring: false,
  ai_studio: false,
  maic: false,
  saml: false,
  sso: false,
  '2fa': false,
  students: false,
};

interface TenantState {
  theme: TenantTheme;
  plan: string;
  features: TenantFeatures;
  limits: TenantLimits | null;
  usage: TenantUsage | null;
  /** Active tenant mode (education | corporate). Defaults to 'education'. */
  mode: TenantMode;
  /**
   * Merged mode-labels dict from the backend (`Tenant.get_mode_labels()`).
   * Falls back to `EDUCATION_DEFAULTS` until populated after auth.
   */
  modeLabels: ModeLabels;
  setTheme: (theme: TenantTheme) => void;
  setConfig: (config: {
    plan?: string;
    features?: TenantFeatures;
    limits?: TenantLimits;
    usage?: TenantUsage;
  }) => void;
  /** Update mode + labels after loading from `/tenants/me/` or `/tenants/settings/`. */
  setModeLabels: (mode: TenantMode, labels: ModeLabels) => void;
  hasFeature: (feature: keyof TenantFeatures) => boolean;
  reset: () => void;
}

export const useTenantStore = create<TenantState>((set, get) => ({
  theme: DEFAULT_THEME,
  plan: 'FREE',
  features: DEFAULT_FEATURES,
  limits: null,
  usage: null,
  mode: 'education',
  modeLabels: EDUCATION_DEFAULTS,
  setTheme: (theme) => set({ theme }),
  setConfig: (config) => set({
    plan: config.plan ?? get().plan,
    features: config.features ?? get().features,
    limits: config.limits ?? get().limits,
    usage: config.usage ?? get().usage,
  }),
  setModeLabels: (mode, labels) => set({ mode, modeLabels: labels }),
  hasFeature: (feature) => get().features[feature] ?? false,
  reset: () => set({
    theme: DEFAULT_THEME,
    plan: 'FREE',
    features: DEFAULT_FEATURES,
    limits: null,
    usage: null,
    mode: 'education',
    modeLabels: EDUCATION_DEFAULTS,
  }),
}));
