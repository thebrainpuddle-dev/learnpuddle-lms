// src/services/reportBuilderService.ts
//
// API service for the Custom Report Builder (TASK-053 backend / TASK-056 frontend).
//
// All endpoints are mounted under /v1/admin/reports/.
// One exported helper per endpoint; types mirror the backend serializer shapes
// (apps/reports_builder/serializers.py and query_engine.py).

import api from '../config/api';

// ─── Primitive types ─────────────────────────────────────────────────────────

/** Data sources — matches DATA_SOURCE_CHOICES on ReportDefinition. */
export type ReportDataSource =
  | 'courses'
  | 'teacher_progress'
  | 'assignments'
  | 'quiz_attempts'
  | 'gamification'
  | 'certifications';

/** Supported filter operators — see SUPPORTED_OPS in query_engine.py. */
export type ReportFilterOp =
  | 'eq'
  | 'ne'
  | 'gt'
  | 'gte'
  | 'lt'
  | 'lte'
  | 'in'
  | 'contains'
  | 'between';

/** Supported aggregate functions — see AGGREGATE_FN_MAP in query_engine.py. */
export type ReportAggregateFn = 'count' | 'distinct_count' | 'sum' | 'avg';

/** Run statuses on ReportRun. */
export type ReportRunStatus = 'pending' | 'running' | 'success' | 'error';

/** Schedule cadences. */
export type ReportScheduleCadence = 'daily' | 'weekly' | 'monthly';

/** Schedule last_run_status. */
export type ReportScheduleLastRunStatus =
  | 'ok'
  | 'error'
  | 'never_run'
  | 'delivery_failed';

// ─── JSON DSL entries ────────────────────────────────────────────────────────

export interface FilterEntry {
  field: string;
  op: ReportFilterOp;
  // JSONField — arbitrary scalar / array. Type loosely here.
  value: unknown;
}

export interface GroupByEntry {
  field: string;
}

export interface AggregateEntry {
  fn: ReportAggregateFn;
  field: string;
  alias?: string;
}

// ─── Definition shapes ───────────────────────────────────────────────────────

export interface ReportDefinitionListItem {
  id: string;
  name: string;
  description: string;
  data_source: ReportDataSource;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface ReportDefinition extends ReportDefinitionListItem {
  filters_json: FilterEntry[];
  // Backend accepts both string[] and {field: string}[]. We normalise to GroupByEntry[]
  // on the UI side but keep the raw union here to stay faithful to the wire format.
  group_by_json: Array<string | GroupByEntry>;
  aggregates_json: AggregateEntry[];
  is_soft_deleted: boolean;
}

export interface ReportDefinitionWritePayload {
  name: string;
  description?: string;
  data_source: ReportDataSource;
  filters_json: FilterEntry[];
  group_by_json: GroupByEntry[] | string[];
  aggregates_json: AggregateEntry[];
}

// ─── Run / export shapes ─────────────────────────────────────────────────────

export interface ReportRunResult {
  run_id: string;
  row_count: number;
  rows: Array<Record<string, unknown>>;
}

export interface ReportRunRecord {
  id: string;
  definition: string | null;
  run_by: string | null;
  params_snapshot_json: Record<string, unknown>;
  started_at: string;
  finished_at: string | null;
  row_count: number;
  artifact_path: string;
  artifact_sha256: string;
  status: ReportRunStatus;
  error: string;
}

export interface ExportEnqueueResponse {
  run_id: string;
}

export interface DownloadSignedUrlResponse {
  download_url: string;
  expires_in: number;
}

// ─── Schedule shapes ─────────────────────────────────────────────────────────

export interface ReportSchedule {
  id: string;
  cadence: ReportScheduleCadence;
  run_at_hour: number;
  run_at_day_of_week: number | null;
  run_at_day_of_month: number | null;
  recipients_json: string[];
  enabled: boolean;
  last_run_at: string | null;
  last_run_status: ReportScheduleLastRunStatus;
  created_at: string;
  updated_at: string;
}

export interface ReportScheduleWritePayload {
  cadence: ReportScheduleCadence;
  run_at_hour: number;
  run_at_day_of_week?: number | null;
  run_at_day_of_month?: number | null;
  recipients_json: string[];
  enabled?: boolean;
}

// ─── Data-source schema ──────────────────────────────────────────────────────

export interface DataSourceSchema {
  name: ReportDataSource;
  label: string;
  fields: string[];
  operators: ReportFilterOp[];
  aggregates: ReportAggregateFn[];
}

export interface SchemaResponse {
  data_sources: DataSourceSchema[];
}

// ─── Service ─────────────────────────────────────────────────────────────────

const BASE = '/v1/admin/reports';

export const reportBuilderService = {
  /** GET /schema/ — data source whitelists for the builder. */
  getSchema: async (): Promise<SchemaResponse> => {
    const res = await api.get<SchemaResponse>(`${BASE}/schema/`);
    return res.data;
  },

  /** GET /definitions/ — list all definitions for current tenant. */
  listDefinitions: async (): Promise<ReportDefinitionListItem[]> => {
    const res = await api.get<ReportDefinitionListItem[]>(`${BASE}/definitions/`);
    return res.data;
  },

  /** GET /definitions/{id}/ — fetch one definition. */
  getDefinition: async (id: string): Promise<ReportDefinition> => {
    const res = await api.get<ReportDefinition>(`${BASE}/definitions/${id}/`);
    return res.data;
  },

  /** POST /definitions/ — create a new definition. */
  createDefinition: async (
    payload: ReportDefinitionWritePayload,
  ): Promise<ReportDefinition> => {
    const res = await api.post<ReportDefinition>(`${BASE}/definitions/`, payload);
    return res.data;
  },

  /** PATCH /definitions/{id}/ — partial update. */
  updateDefinition: async (
    id: string,
    patch: Partial<ReportDefinitionWritePayload>,
  ): Promise<ReportDefinition> => {
    const res = await api.patch<ReportDefinition>(
      `${BASE}/definitions/${id}/`,
      patch,
    );
    return res.data;
  },

  /** DELETE /definitions/{id}/ — soft delete. */
  deleteDefinition: async (id: string): Promise<void> => {
    await api.delete(`${BASE}/definitions/${id}/`);
  },

  /**
   * POST /definitions/{id}/run/ — execute synchronously.
   * Surfaces `ROW_CAP_EXCEEDED` as a 400 error body; 503 on cache outage.
   */
  runDefinition: async (id: string): Promise<ReportRunResult> => {
    const res = await api.post<ReportRunResult>(
      `${BASE}/definitions/${id}/run/`,
    );
    return res.data;
  },

  /** POST /definitions/{id}/export/ — enqueue async CSV build. */
  exportDefinition: async (id: string): Promise<ExportEnqueueResponse> => {
    const res = await api.post<ExportEnqueueResponse>(
      `${BASE}/definitions/${id}/export/`,
    );
    return res.data;
  },

  /** GET /runs/ — list run history, optionally filtered by definition_id. */
  listRuns: async (definitionId?: string): Promise<ReportRunRecord[]> => {
    const res = await api.get<ReportRunRecord[]>(`${BASE}/runs/`, {
      params: definitionId ? { definition_id: definitionId } : {},
    });
    return res.data;
  },

  /** GET /runs/{id}/download/ — signed URL for a successful run's CSV artifact. */
  getDownloadUrl: async (runId: string): Promise<DownloadSignedUrlResponse> => {
    const res = await api.get<DownloadSignedUrlResponse>(
      `${BASE}/runs/${runId}/download/`,
    );
    return res.data;
  },

  /** GET /definitions/{id}/schedules/ — list schedules. */
  listSchedules: async (definitionId: string): Promise<ReportSchedule[]> => {
    const res = await api.get<ReportSchedule[]>(
      `${BASE}/definitions/${definitionId}/schedules/`,
    );
    return res.data;
  },

  /** POST /definitions/{id}/schedules/ — create a schedule. */
  createSchedule: async (
    definitionId: string,
    payload: ReportScheduleWritePayload,
  ): Promise<ReportSchedule> => {
    const res = await api.post<ReportSchedule>(
      `${BASE}/definitions/${definitionId}/schedules/`,
      payload,
    );
    return res.data;
  },

  /** PATCH /definitions/{id}/schedules/{sid}/ — update a schedule. */
  updateSchedule: async (
    definitionId: string,
    scheduleId: string,
    patch: Partial<ReportScheduleWritePayload>,
  ): Promise<ReportSchedule> => {
    const res = await api.patch<ReportSchedule>(
      `${BASE}/definitions/${definitionId}/schedules/${scheduleId}/`,
      patch,
    );
    return res.data;
  },

  /** DELETE /definitions/{id}/schedules/{sid}/. */
  deleteSchedule: async (
    definitionId: string,
    scheduleId: string,
  ): Promise<void> => {
    await api.delete(
      `${BASE}/definitions/${definitionId}/schedules/${scheduleId}/`,
    );
  },
};

// ─── Helpers exported for UI consumption ────────────────────────────────────

/** Normalise the loose group_by_json wire format into a list of entries. */
export function normaliseGroupBy(
  raw: Array<string | GroupByEntry> | undefined | null,
): GroupByEntry[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((item) => {
      if (typeof item === 'string') return { field: item };
      if (item && typeof item === 'object' && typeof item.field === 'string') {
        return { field: item.field };
      }
      return null;
    })
    .filter((x): x is GroupByEntry => x !== null);
}

/** Flatten a list of GroupByEntry back to plain string[] for the wire format. */
export function serialiseGroupBy(entries: GroupByEntry[]): string[] {
  return entries.map((e) => e.field);
}
