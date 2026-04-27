// src/services/masteryService.ts
//
// TASK-018 — Mastery Points frontend surface.
//
// Mastery Points (MP) is a second gamification currency that tracks
// demonstrated competence (quiz/assignment mastery, course completion bonus)
// rather than effort. The backend exposes three endpoints:
//
//   GET /gamification/mastery/                          — teacher MP summary
//   GET /gamification/mastery/history/                  — teacher MP ledger
//   GET /gamification/admin/mastery/leaderboard/        — admin leaderboard
//
// All types mirror the DRF serializers in
// `backend/apps/progress/gamification_serializers.py` — `amount` and totals
// are serialized as strings (DecimalField), callers must coerce to Number
// before doing arithmetic/formatting.

import api from '../config/api';

// ── Reason enum ───────────────────────────────────────────────────────────────

/**
 * MP transaction reasons — matches `MASTERY_POINT_REASON_CHOICES` in the
 * backend gamification models.
 */
export type MasteryReason =
  | 'quiz_mastery'
  | 'assignment_mastery'
  | 'course_mastery_bonus'
  | 'admin_adjust';

export const MASTERY_REASON_LABELS: Record<MasteryReason, string> = {
  quiz_mastery: 'Quiz mastery',
  assignment_mastery: 'Assignment mastery',
  course_mastery_bonus: 'Course bonus',
  admin_adjust: 'Admin adjust',
};

// ── Response types ────────────────────────────────────────────────────────────

/** One immutable row in the MP ledger. */
export interface MasteryTransaction {
  id: string;
  teacher: string;
  teacher_name: string;
  teacher_email: string;
  /** Decimal rendered as a string (e.g. "12.50"). */
  amount: string;
  reason: MasteryReason;
  description: string;
  reference_id: string | null;
  reference_type: string;
  skill_code: string;
  created_at: string;
}

/** Denormalized per-teacher MP totals. */
export interface MasterySummary {
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  total_mastery_points: string;
  mp_this_month: string;
  mp_this_week: string;
  last_mp_at: string | null;
}

/** One admin leaderboard entry. */
export interface MasteryLeaderboardEntry {
  rank: number;
  teacher_id: string;
  teacher_name: string;
  teacher_email: string;
  total_mastery_points: string;
  mp_this_week: string;
  mp_this_month: string;
}

export interface MasteryLeaderboardResponse {
  count: number;
  results: MasteryLeaderboardEntry[];
}

/** Standard DRF page payload for the teacher history endpoint. */
export interface MasteryHistoryPage {
  count: number;
  next: string | null;
  previous: string | null;
  results: MasteryTransaction[];
}

// ── Request param types ───────────────────────────────────────────────────────

export interface TeacherHistoryParams {
  page?: number;
  /**
   * Optional reason filter applied client-side in the UI but passed through
   * so the backend can adopt server-side filtering later without a FE change.
   */
  source?: MasteryReason | '';
}

export type MasteryLeaderboardPeriod = 'weekly' | 'monthly' | 'all_time';

export interface AdminLeaderboardParams {
  period?: MasteryLeaderboardPeriod;
  limit?: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Coerce a decimal string ("12.50") to a JS number. Returns 0 on NaN. */
export function mpToNumber(raw: string | number | null | undefined): number {
  if (raw == null) return 0;
  const n = typeof raw === 'number' ? raw : Number(raw);
  return Number.isFinite(n) ? n : 0;
}

// ── Service ───────────────────────────────────────────────────────────────────

export const masteryService = {
  /** Fetch the current teacher's MP summary. */
  async getTeacherSummary(): Promise<MasterySummary> {
    const res = await api.get<MasterySummary>('/gamification/mastery/');
    return res.data;
  },

  /** Fetch the current teacher's paginated MP ledger. */
  async getTeacherHistory(
    params: TeacherHistoryParams = {},
  ): Promise<MasteryHistoryPage> {
    const query: Record<string, string | number> = {};
    if (params.page && params.page > 0) query.page = params.page;
    if (params.source) query.reason = params.source;
    const res = await api.get<MasteryHistoryPage>(
      '/gamification/mastery/history/',
      { params: query },
    );
    return res.data;
  },

  /** Admin: ranked leaderboard across the tenant. */
  async getAdminLeaderboard(
    params: AdminLeaderboardParams = {},
  ): Promise<MasteryLeaderboardResponse> {
    const query: Record<string, string | number> = {};
    if (params.period) query.period = params.period;
    if (params.limit) query.limit = params.limit;
    const res = await api.get<MasteryLeaderboardResponse>(
      '/gamification/admin/mastery/leaderboard/',
      { params: query },
    );
    return res.data;
  },
};
