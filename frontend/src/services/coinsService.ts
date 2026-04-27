// src/services/coinsService.ts
//
// TASK-019 — Puddle Coins frontend surface.
//
// Puddle Coins are the soft currency earned by XP-bearing actions (content
// completion, quiz submission, streak maintenance, …) and spent in the Shop
// on consumables — currently only the "Streak Freeze Token".
//
// Backend endpoints mirrored here (see
// `backend/apps/progress/gamification_urls.py` and `coin_views.py`):
//
//   GET  /gamification/coins/                       — current balance + lifetime totals
//   GET  /gamification/coins/history/               — paginated coin ledger (25/page)
//   POST /gamification/coins/purchase/streak-freeze/ — debit coins, mint a freeze token
//
// Notes on response shapes:
// - `CoinBalance` mirrors `TeacherCoinBalanceSerializer`. The balance endpoint
//   does NOT currently include `price_streak_freeze` (see `coin_views.py`),
//   so the field is typed as optional. If/when the BE adds it, no FE changes
//   are required.
// - The 400 response on insufficient funds DOES include `{balance, price}`;
//   the service exposes a narrow helper (`parseInsufficientCoinsError`) that
//   extracts it so the page can surface a specific error toast.
//
// Types are mirrored exactly — no `any`.

import axios from 'axios';
import api from '../config/api';

// ── Coin ledger ───────────────────────────────────────────────────────────────

/** Reason values for a CoinTransaction row (matches backend CHOICES). */
export type CoinReason =
  | 'content_completion'
  | 'quiz_submission'
  | 'assignment_submission'
  | 'course_completion'
  | 'streak_day'
  | 'streak_milestone'
  | 'admin_adjust'
  | 'purchase_streak_freeze'
  | 'refund';

/** Human labels used by the wallet history table. */
export const COIN_REASON_LABELS: Record<string, string> = {
  content_completion: 'Content completion',
  quiz_submission: 'Quiz submission',
  assignment_submission: 'Assignment submission',
  course_completion: 'Course completion',
  streak_day: 'Streak day',
  streak_milestone: 'Streak milestone',
  admin_adjust: 'Admin adjust',
  purchase_streak_freeze: 'Streak-freeze purchase',
  refund: 'Refund',
};

/** One immutable row in the coin ledger (earn = positive, spend = negative). */
export interface CoinTransaction {
  id: string;
  teacher: string;
  amount: number;
  reason: string;
  description: string;
  reference_id: string | null;
  reference_type: string;
  created_at: string;
}

/** Teacher coin balance row — mirrors `TeacherCoinBalanceSerializer`. */
export interface CoinBalance {
  teacher_id: string;
  balance: number;
  lifetime_earned: number;
  lifetime_spent: number;
  last_txn_at: string | null;
  updated_at: string;
  /**
   * Optional price hint for the Streak-Freeze Token. Not currently returned
   * by `GET /coins/`; present only if the backend adds it (or the UI caches
   * it from a previous InsufficientCoinsError response).
   */
  price_streak_freeze?: number;
}

/** Standard DRF page payload for the coin history endpoint. */
export interface CoinHistoryResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: CoinTransaction[];
}

/** Minted-token descriptor the purchase endpoint echoes back. */
export interface PurchasedToken {
  id: string | null;
  source: string | null;
  expires_at: string | null;
}

/** Success payload for `POST /coins/purchase/streak-freeze/`. */
export interface PurchaseResponse {
  balance: CoinBalance;
  transaction: CoinTransaction;
  token: PurchasedToken;
}

/** Error payload surfaced by `InsufficientCoinsError` (HTTP 400). */
export interface InsufficientCoinsPayload {
  balance: number;
  price: number;
  error?: string;
}

// ── Request params ────────────────────────────────────────────────────────────

export interface CoinHistoryParams {
  page?: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Narrow an Axios error thrown by the purchase endpoint into the typed
 * `{balance, price}` body so callers can render a specific toast.
 * Returns `null` if the error isn't a 400 with those fields.
 */
export function parseInsufficientCoinsError(
  err: unknown,
): InsufficientCoinsPayload | null {
  if (!axios.isAxiosError(err)) return null;
  if (err.response?.status !== 400) return null;
  const data = err.response.data as Partial<InsufficientCoinsPayload> | undefined;
  if (
    data &&
    typeof data.balance === 'number' &&
    typeof data.price === 'number'
  ) {
    return { balance: data.balance, price: data.price, error: data.error };
  }
  return null;
}

// ── Service ───────────────────────────────────────────────────────────────────

export const coinsService = {
  /** Fetch the current teacher's coin balance + lifetime totals. */
  async getBalance(): Promise<CoinBalance> {
    const res = await api.get<CoinBalance>('/gamification/coins/');
    return res.data;
  },

  /** Fetch the current teacher's paginated coin ledger. */
  async getHistory(params: CoinHistoryParams = {}): Promise<CoinHistoryResponse> {
    const query: Record<string, number> = {};
    if (params.page && params.page > 0) query.page = params.page;
    const res = await api.get<CoinHistoryResponse>(
      '/gamification/coins/history/',
      { params: query },
    );
    return res.data;
  },

  /**
   * Spend coins to buy exactly one Streak-Freeze Token.
   * Throws the underlying Axios error on 400 so callers can use
   * `parseInsufficientCoinsError` to surface a specific toast.
   */
  async purchaseStreakFreeze(): Promise<PurchaseResponse> {
    const res = await api.post<PurchaseResponse>(
      '/gamification/coins/purchase/streak-freeze/',
    );
    return res.data;
  },
};
