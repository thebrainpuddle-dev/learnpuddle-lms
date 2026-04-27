// src/stores/translationStore.ts
// Zustand store for Translation feature — polling state + per-field review state
// (backed by TASK-064b server persistence as of this file's last revision).

import { create } from 'zustand';
import type {
  TranslationJob,
  TranslationJobStatus,
  ContentTranslationReview,
  TranslationFieldKey,
} from '../services/translationService';
import { translationService } from '../services/translationService';

// ─── Types ────────────────────────────────────────────────────────────────────

export type PollingState = 'idle' | 'polling' | 'stopped';

export interface JobPollingEntry {
  jobId: string;
  pollingState: PollingState;
  backoffMs: number;
  errorCount: number;
}

/**
 * Per-field review state — now mirrors server shape (TASK-064b).
 * The store is the authoritative client cache; populated from server responses.
 */
export type FieldReviewStatus = 'pending' | 'approved' | 'rejected';

export interface FieldReviewEntry {
  fieldKey: string; // e.g. "title", "description"
  status: FieldReviewStatus;
  editedText: string | null;
  reviewedAt: string | null;
  reviewedByEmail: string | null;
  publishedAt: string | null;
}

/** Keyed by "{contentId}:{lang}" */
export type ContentPublishState = 'idle' | 'publishing' | 'published';

interface TranslationState {
  // Active polling registry keyed by job id
  pollingRegistry: Record<string, JobPollingEntry>;

  // Cached full job data per job id
  jobCache: Record<string, TranslationJob>;

  // Per-field review state keyed by "{contentId}:{lang}:{fieldKey}"
  fieldReviews: Record<string, FieldReviewEntry>;

  // Publish state per content+lang keyed by "{contentId}:{lang}"
  publishState: Record<string, ContentPublishState>;

  // Optimistic-rollback snapshot keyed by "{contentId}:{lang}:{fieldKey}"
  _optimisticSnapshot: Record<string, FieldReviewEntry | undefined>;

  // Actions — synchronous
  startPolling: (jobId: string) => void;
  stopPolling: (jobId: string) => void;
  setPollingBackoff: (jobId: string, backoffMs: number, errorCount: number) => void;
  cacheJob: (job: TranslationJob) => void;
  /** Low-level setter — used by server-hydration and tests. */
  setFieldReview: (contentId: string, lang: string, fieldKey: string, entry: Partial<FieldReviewEntry>) => void;
  /** Hydrate multiple fields from a getContentTranslations response. */
  hydrateFromServer: (contentId: string, lang: string, rows: ContentTranslationReview[]) => void;
  /** Reset all review entries for a given jobId prefix (used on Retry). */
  resetFieldReviews: (jobId: string) => void;
  reset: () => void;

  // Actions — async (call backend, then update store)
  approveField: (
    contentId: string,
    field: TranslationFieldKey,
    lang: string,
    toastFn: { error: (title: string, msg?: string) => void }
  ) => Promise<void>;
  rejectField: (
    contentId: string,
    field: TranslationFieldKey,
    lang: string,
    toastFn: { error: (title: string, msg?: string) => void }
  ) => Promise<void>;
  editField: (
    contentId: string,
    field: TranslationFieldKey,
    lang: string,
    editedText: string,
    toastFn: { error: (title: string, msg?: string) => void }
  ) => Promise<void>;
  publishTranslation: (
    contentId: string,
    lang: string,
    toastFn: {
      success: (title: string, msg?: string) => void;
      error: (title: string, msg?: string) => void;
      info: (title: string, msg?: string) => void;
    }
  ) => Promise<{ rows_published: number; skipped: Record<string, string> } | null>;
}

// ─── Backoff constants ────────────────────────────────────────────────────────

export const POLL_INTERVAL_MS = 3000;
const BACKOFF_STEPS = [3000, 6000, 12000, 24000, 30000];

export function nextBackoffMs(currentMs: number): number {
  const idx = BACKOFF_STEPS.findIndex((s) => s >= currentMs);
  return BACKOFF_STEPS[Math.min(idx + 1, BACKOFF_STEPS.length - 1)];
}

export function isTerminalStatus(status: TranslationJobStatus): boolean {
  return status === 'success' || status === 'failed';
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function reviewKey(contentId: string, lang: string, fieldKey: string): string {
  return `${contentId}:${lang}:${fieldKey}`;
}

function serverRowToEntry(row: ContentTranslationReview): FieldReviewEntry {
  return {
    fieldKey: row.field,
    status: row.review_status,
    editedText: row.edited_text,
    reviewedAt: row.reviewed_at,
    reviewedByEmail: row.reviewed_by_email,
    publishedAt: row.published_at,
  };
}

function handleReviewApiError(
  err: any,
  toastFn: { error: (title: string, msg?: string) => void }
) {
  const status = Number(err?.response?.status ?? 0);
  if (status === 429) {
    const retryAfter = err?.response?.headers?.['retry-after'];
    const hint = retryAfter ? ` Retry after ${retryAfter}s.` : '';
    toastFn.error('Rate limit reached', `Too many review actions.${hint}`);
  } else if (status === 403) {
    toastFn.error('Permission denied', 'Only admins can review translations.');
  } else if (status === 404) {
    toastFn.error('Not found', 'Translation row not found or access denied.');
  } else {
    toastFn.error(
      'Action failed',
      err?.response?.data?.detail ?? 'Please try again.'
    );
  }
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useTranslationStore = create<TranslationState>((set, get) => ({
  pollingRegistry: {},
  jobCache: {},
  fieldReviews: {},
  publishState: {},
  _optimisticSnapshot: {},

  startPolling: (jobId) =>
    set((state) => ({
      pollingRegistry: {
        ...state.pollingRegistry,
        [jobId]: {
          jobId,
          pollingState: 'polling',
          backoffMs: POLL_INTERVAL_MS,
          errorCount: 0,
        },
      },
    })),

  stopPolling: (jobId) =>
    set((state) => {
      const entry = state.pollingRegistry[jobId];
      if (!entry) return state;
      return {
        pollingRegistry: {
          ...state.pollingRegistry,
          [jobId]: { ...entry, pollingState: 'stopped' },
        },
      };
    }),

  setPollingBackoff: (jobId, backoffMs, errorCount) =>
    set((state) => {
      const entry = state.pollingRegistry[jobId];
      if (!entry) return state;
      return {
        pollingRegistry: {
          ...state.pollingRegistry,
          [jobId]: { ...entry, backoffMs, errorCount },
        },
      };
    }),

  cacheJob: (job) =>
    set((state) => ({
      jobCache: { ...state.jobCache, [job.id]: job },
    })),

  setFieldReview: (contentId, lang, fieldKey, entry) =>
    set((state) => {
      const key = reviewKey(contentId, lang, fieldKey);
      const existing = state.fieldReviews[key] ?? {
        fieldKey,
        status: 'pending' as FieldReviewStatus,
        editedText: null,
        reviewedAt: null,
        reviewedByEmail: null,
        publishedAt: null,
      };
      return {
        fieldReviews: {
          ...state.fieldReviews,
          [key]: { ...existing, ...entry },
        },
      };
    }),

  hydrateFromServer: (contentId, lang, rows) =>
    set((state) => {
      const updated = { ...state.fieldReviews };
      rows.forEach((row) => {
        const key = reviewKey(contentId, lang, row.field);
        updated[key] = serverRowToEntry(row);
      });
      return { fieldReviews: updated };
    }),

  resetFieldReviews: (jobId) =>
    set((state) => {
      const updated = { ...state.fieldReviews };
      Object.keys(updated).forEach((k) => {
        if (k.startsWith(`${jobId}:`)) delete updated[k];
      });
      return { fieldReviews: updated };
    }),

  reset: () =>
    set({
      pollingRegistry: {},
      jobCache: {},
      fieldReviews: {},
      publishState: {},
      _optimisticSnapshot: {},
    }),

  // ── Async actions ────────────────────────────────────────────────────────────

  approveField: async (contentId, field, lang, toastFn) => {
    const key = reviewKey(contentId, lang, field);
    const snapshot = get().fieldReviews[key];
    // Optimistic update
    get().setFieldReview(contentId, lang, field, { status: 'approved' });
    try {
      const row = await translationService.approveField(contentId, field, lang);
      set((state) => ({
        fieldReviews: {
          ...state.fieldReviews,
          [key]: serverRowToEntry(row),
        },
      }));
    } catch (err: any) {
      // Roll back
      set((state) => ({
        fieldReviews: {
          ...state.fieldReviews,
          [key]: snapshot ?? {
            fieldKey: field,
            status: 'pending',
            editedText: null,
            reviewedAt: null,
            reviewedByEmail: null,
            publishedAt: null,
          },
        },
      }));
      handleReviewApiError(err, toastFn);
    }
  },

  rejectField: async (contentId, field, lang, toastFn) => {
    const key = reviewKey(contentId, lang, field);
    const snapshot = get().fieldReviews[key];
    // Optimistic update
    get().setFieldReview(contentId, lang, field, { status: 'rejected', editedText: null });
    try {
      const row = await translationService.rejectField(contentId, field, lang);
      set((state) => ({
        fieldReviews: {
          ...state.fieldReviews,
          [key]: serverRowToEntry(row),
        },
      }));
    } catch (err: any) {
      // Roll back
      set((state) => ({
        fieldReviews: {
          ...state.fieldReviews,
          [key]: snapshot ?? {
            fieldKey: field,
            status: 'pending',
            editedText: null,
            reviewedAt: null,
            reviewedByEmail: null,
            publishedAt: null,
          },
        },
      }));
      handleReviewApiError(err, toastFn);
    }
  },

  editField: async (contentId, field, lang, editedText, toastFn) => {
    const key = reviewKey(contentId, lang, field);
    const snapshot = get().fieldReviews[key];
    // Optimistic update
    get().setFieldReview(contentId, lang, field, { editedText, status: 'approved' });
    try {
      const row = await translationService.editField(contentId, field, lang, editedText);
      set((state) => ({
        fieldReviews: {
          ...state.fieldReviews,
          [key]: serverRowToEntry(row),
        },
      }));
    } catch (err: any) {
      // Roll back
      set((state) => ({
        fieldReviews: {
          ...state.fieldReviews,
          [key]: snapshot ?? {
            fieldKey: field,
            status: 'pending',
            editedText: null,
            reviewedAt: null,
            reviewedByEmail: null,
            publishedAt: null,
          },
        },
      }));
      handleReviewApiError(err, toastFn);
    }
  },

  publishTranslation: async (contentId, lang, toastFn) => {
    const pubKey = `${contentId}:${lang}`;
    set((state) => ({
      publishState: { ...state.publishState, [pubKey]: 'publishing' },
    }));
    try {
      const result = await translationService.publishTranslation(contentId, lang);
      set((state) => ({
        publishState: { ...state.publishState, [pubKey]: 'published' },
      }));
      const skippedCount = Object.keys(result.skipped ?? {}).length;
      if (skippedCount > 0) {
        const skippedList = Object.entries(result.skipped)
          .map(([f, reason]) => `${f}: ${reason}`)
          .join('; ');
        toastFn.info(
          `Published ${result.rows_published} field${result.rows_published !== 1 ? 's' : ''}`,
          `${skippedCount} skipped — ${skippedList}`
        );
      } else {
        toastFn.success(
          `Published ${result.rows_published} field${result.rows_published !== 1 ? 's' : ''}`,
          'All approved translations have been published.'
        );
      }
      return { rows_published: result.rows_published, skipped: result.skipped ?? {} };
    } catch (err: any) {
      set((state) => ({
        publishState: { ...state.publishState, [pubKey]: 'idle' },
      }));
      handleReviewApiError(err, toastFn);
      return null;
    }
  },
}));
