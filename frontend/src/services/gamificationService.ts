import api from '../config/api';

// ── Admin types ──────────────────────────────────────────────────────

export interface GamificationConfig {
  id: string;
  xp_per_content_completion: number;
  xp_per_course_completion: number;
  xp_per_assignment_submission: number;
  xp_per_quiz_submission: number;
  xp_per_streak_day: number;
  streak_freeze_max: number;
  leaderboard_enabled: boolean;
  leaderboard_anonymize: boolean;
  opt_out_allowed: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface BadgeDefinition {
  id: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  category: 'milestone' | 'streak' | 'completion' | 'skill' | 'special';
  criteria_type: 'xp_threshold' | 'courses_completed' | 'streak_days' | 'content_completed' | 'manual';
  criteria_value: number;
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface BadgeCreateData {
  name: string;
  description?: string;
  icon?: string;
  color?: string;
  category: string;
  criteria_type: string;
  criteria_value: number;
  is_active?: boolean;
  sort_order?: number;
}

export interface XPTransaction {
  id: string;
  teacher: string;
  teacher_name: string;
  teacher_email: string;
  xp_amount: number;
  reason: string;
  description: string;
  reference_id: string | null;
  reference_type: string;
  created_at: string;
}

export interface XPAdjustData {
  teacher_id: string;
  xp_amount: number;
  reason?: string;
}

// ── Leaderboard types ────────────────────────────────────────────────

export interface LeaderboardEntry {
  rank: number;
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  total_xp: number;
  xp_period: number;
  level: number;
  level_name: string;
  badge_count: number;
  current_streak: number;
}

export interface LeaderboardResponse {
  period: string;
  entries: LeaderboardEntry[];
  snapshot_date: string;
}

// ── Teacher types ────────────────────────────────────────────────────

export interface TeacherXPSummary {
  total_xp: number;
  level: number;
  level_name: string;
  xp_this_month: number;
  xp_this_week: number;
  current_streak: number;
  longest_streak: number;
  last_xp_at: string | null;
  opted_out: boolean;
  badges: TeacherBadge[];
  next_level_xp: number | null;
  xp_to_next_level: number;
}

export interface TeacherBadge {
  id: string;
  badge: BadgeDefinition;
  awarded_at: string;
  awarded_reason: string;
}

// ── API service ──────────────────────────────────────────────────────

export const gamificationService = {
  // ── Admin: Config ──────────────────────────────────────────────────
  admin: {
    async getConfig(): Promise<GamificationConfig> {
      const res = await api.get('/gamification/admin/config/');
      return res.data;
    },
    async updateConfig(data: Partial<GamificationConfig>): Promise<GamificationConfig> {
      const res = await api.patch('/gamification/admin/config/update/', data);
      return res.data;
    },

    // ── Admin: Badges ────────────────────────────────────────────────
    async listBadges(): Promise<BadgeDefinition[]> {
      const res = await api.get('/gamification/admin/badges/');
      return res.data.results ?? res.data;
    },
    async createBadge(data: BadgeCreateData): Promise<BadgeDefinition> {
      const res = await api.post('/gamification/admin/badges/create/', data);
      return res.data;
    },
    async updateBadge(id: string, data: Partial<BadgeCreateData>): Promise<BadgeDefinition> {
      const res = await api.patch(`/gamification/admin/badges/${id}/update/`, data);
      return res.data;
    },
    async deleteBadge(id: string): Promise<void> {
      await api.delete(`/gamification/admin/badges/${id}/delete/`);
    },

    // ── Admin: Leaderboard ───────────────────────────────────────────
    async getLeaderboard(period?: string): Promise<LeaderboardResponse> {
      const res = await api.get('/gamification/admin/leaderboard/', { params: { period: period ?? 'all_time' } });
      return res.data;
    },

    // ── Admin: XP History ────────────────────────────────────────────
    async getXPHistory(params?: { teacher_id?: string; reason?: string }): Promise<XPTransaction[]> {
      const res = await api.get('/gamification/admin/xp-history/', { params });
      return res.data.results ?? res.data;
    },

    // ── Admin: XP Adjust ─────────────────────────────────────────────
    async adjustXP(data: XPAdjustData): Promise<XPTransaction> {
      const res = await api.post('/gamification/admin/xp-adjust/', data);
      return res.data;
    },
  },

  // ── Teacher endpoints ──────────────────────────────────────────────
  async getSummary(): Promise<TeacherXPSummary> {
    const res = await api.get('/gamification/summary/');
    return res.data;
  },

  async getLeaderboard(period?: string): Promise<LeaderboardResponse> {
    const res = await api.get('/gamification/leaderboard/', { params: { period: period ?? 'weekly' } });
    return res.data;
  },

  async getBadgeDefinitions(): Promise<BadgeDefinition[]> {
    const res = await api.get('/gamification/badge-definitions/');
    return res.data.results ?? res.data;
  },

  async getMyBadges(): Promise<TeacherBadge[]> {
    const res = await api.get('/gamification/badges/');
    return res.data.results ?? res.data;
  },

  async getXPHistory(): Promise<XPTransaction[]> {
    const res = await api.get('/gamification/xp-history/');
    return res.data.results ?? res.data;
  },

  async optOut(): Promise<void> {
    await api.post('/gamification/opt-out/');
  },

  async optIn(): Promise<void> {
    await api.post('/gamification/opt-in/');
  },

  async useStreakFreeze(): Promise<{ success: boolean; freezes_remaining: number }> {
    const res = await api.post('/gamification/streak-freeze/');
    return res.data;
  },
};
