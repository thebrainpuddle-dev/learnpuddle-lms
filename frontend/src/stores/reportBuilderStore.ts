// src/stores/reportBuilderStore.ts
//
// Minimal Zustand store for the Custom Report Builder.
// Holds the cached data-source schema (field / op / aggregate whitelists) so
// that Filter / GroupBy / Aggregate editors across the page tree don't each
// refetch on mount.
//
// Per-definition list / detail data is intentionally NOT cached here — it
// lives in React Query, which already handles staleness / invalidation for us.

import { create } from 'zustand';

import {
  reportBuilderService,
  type DataSourceSchema,
} from '../services/reportBuilderService';

interface ReportBuilderState {
  schema: DataSourceSchema[] | null;
  schemaLoading: boolean;
  schemaError: string | null;

  /** Fetch the schema once; subsequent callers get the cached copy. */
  ensureSchema: () => Promise<DataSourceSchema[]>;

  /** Force a refresh (used by tests + the "try again" button). */
  refreshSchema: () => Promise<DataSourceSchema[]>;

  /** Reset — used by tests. */
  reset: () => void;
}

const initialState = {
  schema: null,
  schemaLoading: false,
  schemaError: null,
};

export const useReportBuilderStore = create<ReportBuilderState>((set, get) => ({
  ...initialState,

  ensureSchema: async () => {
    const cached = get().schema;
    if (cached) return cached;
    return get().refreshSchema();
  },

  refreshSchema: async () => {
    set({ schemaLoading: true, schemaError: null });
    try {
      const res = await reportBuilderService.getSchema();
      const schema = res.data_sources;
      set({ schema, schemaLoading: false });
      return schema;
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { error?: string } } })?.response?.data
          ?.error ??
        (err as { message?: string })?.message ??
        'Failed to load report builder schema';
      set({ schemaError: message, schemaLoading: false });
      throw err;
    }
  },

  reset: () => set(initialState),
}));
