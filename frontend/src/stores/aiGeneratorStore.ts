// src/stores/aiGeneratorStore.ts
// Zustand store for AI Course Generator — per-job polling state + local outline edits.

import { create } from 'zustand';
import type { Job, Outline, JobStatus } from '../services/aiCourseGeneratorService';

// ─── Types ────────────────────────────────────────────────────────────────────

export type PollingState = 'idle' | 'polling' | 'stopped';

export interface JobPollingEntry {
  jobId: string;
  pollingState: PollingState;
  backoffMs: number; // current interval
  errorCount: number;
}

interface AiGeneratorState {
  // Active polling registry keyed by job id
  pollingRegistry: Record<string, JobPollingEntry>;

  // Locally-edited outline per job (survives polling refetches)
  outlineEdits: Record<string, Outline>;

  // Cached full job data per job id
  jobCache: Record<string, Job>;

  // Actions
  startPolling: (jobId: string) => void;
  stopPolling: (jobId: string) => void;
  setPollingBackoff: (jobId: string, backoffMs: number, errorCount: number) => void;
  cacheJob: (job: Job) => void;
  setOutlineEdit: (jobId: string, outline: Outline) => void;
  clearOutlineEdit: (jobId: string) => void;
  reset: () => void;
}

// ─── Backoff constants ────────────────────────────────────────────────────────

export const POLL_INTERVAL_MS = 3000; // 3 s normal cadence
const BACKOFF_STEPS = [3000, 6000, 12000, 24000, 30000];

export function nextBackoffMs(currentMs: number): number {
  const idx = BACKOFF_STEPS.findIndex((s) => s >= currentMs);
  return BACKOFF_STEPS[Math.min(idx + 1, BACKOFF_STEPS.length - 1)];
}

// ─── Store ────────────────────────────────────────────────────────────────────

export const useAiGeneratorStore = create<AiGeneratorState>((set) => ({
  pollingRegistry: {},
  outlineEdits: {},
  jobCache: {},

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

  setOutlineEdit: (jobId, outline) =>
    set((state) => ({
      outlineEdits: { ...state.outlineEdits, [jobId]: outline },
    })),

  clearOutlineEdit: (jobId) =>
    set((state) => {
      const { [jobId]: _, ...rest } = state.outlineEdits;
      return { outlineEdits: rest };
    }),

  reset: () =>
    set({ pollingRegistry: {}, outlineEdits: {}, jobCache: {} }),
}));

// ─── Selector helpers ─────────────────────────────────────────────────────────

export function isTerminalStatus(status: JobStatus): boolean {
  return status === 'succeeded' || status === 'failed';
}
