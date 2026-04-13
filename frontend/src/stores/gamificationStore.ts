import { create } from 'zustand';

import {
  gamificationService,
  type GamificationConfig,
  type BadgeDefinition,
  type BadgeCreateData,
  type LeaderboardResponse,
  type XPTransaction,
  type XPAdjustData,
  type TeacherXPSummary,
  type TeacherBadge,
} from '../services/gamificationService';

interface GamificationState {
  // Admin state
  config: GamificationConfig | null;
  badges: BadgeDefinition[];
  leaderboard: LeaderboardResponse | null;
  xpHistory: XPTransaction[];

  // Teacher state
  summary: TeacherXPSummary | null;
  myBadges: TeacherBadge[];
  badgeDefinitions: BadgeDefinition[];
  teacherLeaderboard: LeaderboardResponse | null;
  teacherXPHistory: XPTransaction[];

  // UI state
  loading: boolean;
  error: string | null;

  // Admin actions
  fetchConfig: () => Promise<void>;
  updateConfig: (data: Partial<GamificationConfig>) => Promise<void>;
  fetchBadges: () => Promise<void>;
  createBadge: (data: BadgeCreateData) => Promise<void>;
  updateBadge: (id: string, data: Partial<BadgeCreateData>) => Promise<void>;
  deleteBadge: (id: string) => Promise<void>;
  fetchLeaderboard: (period?: string) => Promise<void>;
  fetchXPHistory: (params?: { teacher_id?: string; reason?: string }) => Promise<void>;
  adjustXP: (data: XPAdjustData) => Promise<void>;

  // Teacher actions
  fetchSummary: () => Promise<void>;
  fetchTeacherLeaderboard: (period?: string) => Promise<void>;
  fetchMyBadges: () => Promise<void>;
  fetchBadgeDefinitions: () => Promise<void>;
  fetchTeacherXPHistory: () => Promise<void>;
  toggleOptOut: () => Promise<void>;
  useStreakFreeze: () => Promise<void>;

  // Reset
  reset: () => void;
}

const initialState = {
  config: null,
  badges: [],
  leaderboard: null,
  xpHistory: [],
  summary: null,
  myBadges: [],
  badgeDefinitions: [],
  teacherLeaderboard: null,
  teacherXPHistory: [],
  loading: false,
  error: null,
};

export const useGamificationStore = create<GamificationState>((set, get) => ({
  ...initialState,

  // ── Admin actions ────────────────────────────────────────────────────

  fetchConfig: async () => {
    set({ loading: true, error: null });
    try {
      const config = await gamificationService.admin.getConfig();
      set({ config, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to fetch config', loading: false });
    }
  },

  updateConfig: async (data) => {
    set({ loading: true, error: null });
    try {
      const config = await gamificationService.admin.updateConfig(data);
      set({ config, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to update config', loading: false });
    }
  },

  fetchBadges: async () => {
    set({ loading: true, error: null });
    try {
      const badges = await gamificationService.admin.listBadges();
      set({ badges, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to fetch badges', loading: false });
    }
  },

  createBadge: async (data) => {
    set({ loading: true, error: null });
    try {
      const badge = await gamificationService.admin.createBadge(data);
      set({ badges: [...get().badges, badge], loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to create badge', loading: false });
    }
  },

  updateBadge: async (id, data) => {
    set({ loading: true, error: null });
    try {
      const updated = await gamificationService.admin.updateBadge(id, data);
      set({
        badges: get().badges.map((b) => (b.id === id ? updated : b)),
        loading: false,
      });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to update badge', loading: false });
    }
  },

  deleteBadge: async (id) => {
    set({ loading: true, error: null });
    try {
      await gamificationService.admin.deleteBadge(id);
      set({
        badges: get().badges.filter((b) => b.id !== id),
        loading: false,
      });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to delete badge', loading: false });
    }
  },

  fetchLeaderboard: async (period) => {
    set({ loading: true, error: null });
    try {
      const leaderboard = await gamificationService.admin.getLeaderboard(period);
      set({ leaderboard, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to fetch leaderboard', loading: false });
    }
  },

  fetchXPHistory: async (params) => {
    set({ loading: true, error: null });
    try {
      const xpHistory = await gamificationService.admin.getXPHistory(params);
      set({ xpHistory, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to fetch XP history', loading: false });
    }
  },

  adjustXP: async (data) => {
    set({ loading: true, error: null });
    try {
      const transaction = await gamificationService.admin.adjustXP(data);
      set({ xpHistory: [transaction, ...get().xpHistory], loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to adjust XP', loading: false });
    }
  },

  // ── Teacher actions ──────────────────────────────────────────────────

  fetchSummary: async () => {
    set({ loading: true, error: null });
    try {
      const summary = await gamificationService.getSummary();
      set({ summary, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to fetch summary', loading: false });
    }
  },

  fetchTeacherLeaderboard: async (period) => {
    set({ loading: true, error: null });
    try {
      const teacherLeaderboard = await gamificationService.getLeaderboard(period);
      set({ teacherLeaderboard, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to fetch leaderboard', loading: false });
    }
  },

  fetchMyBadges: async () => {
    set({ loading: true, error: null });
    try {
      const myBadges = await gamificationService.getMyBadges();
      set({ myBadges, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to fetch badges', loading: false });
    }
  },

  fetchBadgeDefinitions: async () => {
    set({ loading: true, error: null });
    try {
      const badgeDefinitions = await gamificationService.getBadgeDefinitions();
      set({ badgeDefinitions, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to fetch badge definitions', loading: false });
    }
  },

  fetchTeacherXPHistory: async () => {
    set({ loading: true, error: null });
    try {
      const teacherXPHistory = await gamificationService.getXPHistory();
      set({ teacherXPHistory, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to fetch XP history', loading: false });
    }
  },

  toggleOptOut: async () => {
    set({ loading: true, error: null });
    try {
      const currentlyOptedOut = get().summary?.opted_out ?? false;
      if (currentlyOptedOut) {
        await gamificationService.optIn();
      } else {
        await gamificationService.optOut();
      }
      // Re-fetch summary to get updated opt-out state
      const summary = await gamificationService.getSummary();
      set({ summary, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to toggle opt-out', loading: false });
    }
  },

  useStreakFreeze: async () => {
    set({ loading: true, error: null });
    try {
      await gamificationService.useStreakFreeze();
      // Re-fetch summary to get updated streak info
      const summary = await gamificationService.getSummary();
      set({ summary, loading: false });
    } catch (err: any) {
      set({ error: err?.response?.data?.detail ?? err.message ?? 'Failed to use streak freeze', loading: false });
    }
  },

  // ── Reset ────────────────────────────────────────────────────────────

  reset: () => set(initialState),
}));
