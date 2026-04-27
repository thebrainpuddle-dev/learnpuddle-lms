// src/pages/admin/ReportBuilderDetailPage.tsx
//
// Detail view for a single ReportDefinition with four tabs:
//   Overview | Preview | History | Schedules
//
// The Preview tab runs the report synchronously on demand and shows the
// result as a paginated table. CSV export enqueues an async build and polls
// the run list for success, then asks the backend for a signed URL and
// opens it in a new tab.

import React, { useEffect, useMemo, useState, useCallback, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeftIcon,
  ArrowDownTrayIcon,
  PencilSquareIcon,
  PlayIcon,
  PlusIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  TabsPanels,
} from '../../components/ui/tabs';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/common/Button';
import { useToast } from '../../components/common/Toast';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  reportBuilderService,
  type ReportRunResult,
  type ReportSchedule,
  type ReportScheduleWritePayload,
  normaliseGroupBy,
} from '../../services/reportBuilderService';
import { PreviewTable } from '../../components/reportBuilder/PreviewTable';
import { RunHistoryTable } from '../../components/reportBuilder/RunHistoryTable';
import { ScheduleForm } from '../../components/reportBuilder/ScheduleForm';

const DATA_SOURCE_LABELS: Record<string, string> = {
  courses: 'Courses',
  teacher_progress: 'Teacher Progress',
  assignments: 'Assignments',
  quiz_attempts: 'Quiz Attempts',
  gamification: 'XP / Gamification',
  certifications: 'Certifications',
};

const EXPORT_POLL_MS = 2500;
const EXPORT_POLL_MAX = 30;

export const ReportBuilderDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  usePageTitle('Report detail');

  const [previewResult, setPreviewResult] = useState<ReportRunResult | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [scheduleFormOpen, setScheduleFormOpen] = useState(false);
  const [editingSchedule, setEditingSchedule] = useState<ReportSchedule | null>(
    null,
  );
  const [scheduleSubmitError, setScheduleSubmitError] = useState<string | null>(
    null,
  );
  const [scheduleSubmitErrorCode, setScheduleSubmitErrorCode] = useState<string | null>(
    null,
  );
  const [confirmDeleteSchedule, setConfirmDeleteSchedule] =
    useState<ReportSchedule | null>(null);
  const [downloadingRunId, setDownloadingRunId] = useState<string | null>(null);

  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Definition ──────────────────────────────────────────────────────────
  const definitionQuery = useQuery({
    queryKey: ['reportBuilder', 'definition', id],
    queryFn: () => reportBuilderService.getDefinition(id!),
    enabled: Boolean(id),
  });

  // ── Runs ────────────────────────────────────────────────────────────────
  const runsQuery = useQuery({
    queryKey: ['reportBuilder', 'runs', id],
    queryFn: () => reportBuilderService.listRuns(id!),
    enabled: Boolean(id),
  });

  // ── Schedules ───────────────────────────────────────────────────────────
  const schedulesQuery = useQuery({
    queryKey: ['reportBuilder', 'schedules', id],
    queryFn: () => reportBuilderService.listSchedules(id!),
    enabled: Boolean(id),
  });

  // ── Preview (run) mutation ──────────────────────────────────────────────
  const runMutation = useMutation({
    mutationFn: () => reportBuilderService.runDefinition(id!),
    onMutate: () => {
      setPreviewError(null);
    },
    onSuccess: (data) => {
      setPreviewResult(data);
      queryClient.invalidateQueries({
        queryKey: ['reportBuilder', 'runs', id],
      });
    },
    onError: (err: unknown) => {
      const response = (err as { response?: { status?: number; data?: { error?: string } } })
        ?.response;
      const errorCode = response?.data?.error ?? '';
      if (response?.status === 503) {
        toast.error(
          'Service unavailable',
          'Report runs are temporarily unavailable. Try again in a minute.',
        );
      } else if (response?.status === 429) {
        toast.error(
          'Rate limit exceeded',
          'Max 20 report runs per hour per school.',
        );
      } else if (errorCode === 'ROW_CAP_EXCEEDED') {
        setPreviewError(
          'ROW_CAP_EXCEEDED — the result exceeds 50,000 rows. Add filters to narrow it down.',
        );
      } else {
        setPreviewError(errorCode || 'Run failed. Check filters and try again.');
      }
    },
  });

  // ── Export (async CSV build) ────────────────────────────────────────────
  const [exportRunId, setExportRunId] = useState<string | null>(null);
  const [exportPollCount, setExportPollCount] = useState(0);

  const clearPollTimer = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    return clearPollTimer;
  }, [clearPollTimer]);

  const pollExport = useCallback(
    async (runId: string, attempt = 0) => {
      if (attempt >= EXPORT_POLL_MAX) {
        toast.error(
          'Export taking too long',
          'The CSV build did not complete in time. Check the History tab.',
        );
        setExportRunId(null);
        return;
      }
      try {
        const runs = await reportBuilderService.listRuns(id!);
        queryClient.setQueryData(['reportBuilder', 'runs', id], runs);
        const match = runs.find((r) => r.id === runId);
        if (!match) {
          pollTimerRef.current = setTimeout(
            () => pollExport(runId, attempt + 1),
            EXPORT_POLL_MS,
          );
          setExportPollCount(attempt + 1);
          return;
        }
        if (match.status === 'success') {
          setExportRunId(null);
          toast.success('Export ready', 'Your CSV is ready to download.');
          // Inline download so we avoid a stale-closure reference to handleDownload.
          setDownloadingRunId(runId);
          try {
            const { download_url } = await reportBuilderService.getDownloadUrl(runId);
            window.open(download_url, '_blank', 'noopener,noreferrer');
          } catch {
            toast.error(
              'Download failed',
              'Could not fetch a signed URL. Try again later.',
            );
          } finally {
            setDownloadingRunId(null);
          }
          return;
        }
        if (match.status === 'error') {
          setExportRunId(null);
          toast.error(
            'Export failed',
            'Something went wrong building the CSV. See History for details.',
          );
          return;
        }
        // pending / running — keep polling
        pollTimerRef.current = setTimeout(
          () => pollExport(runId, attempt + 1),
          EXPORT_POLL_MS,
        );
        setExportPollCount(attempt + 1);
      } catch {
        pollTimerRef.current = setTimeout(
          () => pollExport(runId, attempt + 1),
          EXPORT_POLL_MS,
        );
        setExportPollCount(attempt + 1);
      }
    },
    [id, queryClient, toast],
  );

  const exportMutation = useMutation({
    mutationFn: () => reportBuilderService.exportDefinition(id!),
    onSuccess: (data) => {
      setExportRunId(data.run_id);
      setExportPollCount(0);
      toast.info('Export started', 'Preparing CSV — this may take a moment.');
      queryClient.invalidateQueries({
        queryKey: ['reportBuilder', 'runs', id],
      });
      pollExport(data.run_id, 0);
    },
    onError: (err: unknown) => {
      const status = (err as { response?: { status?: number } })?.response
        ?.status;
      if (status === 503) {
        toast.error(
          'Service unavailable',
          'CSV exports are temporarily unavailable. Try again in a minute.',
        );
      } else if (status === 429) {
        toast.error(
          'Rate limit exceeded',
          'Max 20 report runs per hour per school.',
        );
      } else {
        toast.error('Export failed', 'Could not start CSV build. Try again.');
      }
    },
  });

  // ── Download handler (for run history + export completion) ──────────────
  const handleDownload = useCallback(
    async (runId: string) => {
      setDownloadingRunId(runId);
      try {
        const { download_url } = await reportBuilderService.getDownloadUrl(runId);
        window.open(download_url, '_blank', 'noopener,noreferrer');
      } catch {
        toast.error(
          'Download failed',
          'Could not fetch a signed URL. Try again later.',
        );
      } finally {
        setDownloadingRunId(null);
      }
    },
    [toast],
  );

  // ── Schedule mutations ──────────────────────────────────────────────────
  const createScheduleMutation = useMutation({
    mutationFn: (payload: ReportScheduleWritePayload) =>
      reportBuilderService.createSchedule(id!, payload),
    onSuccess: () => {
      toast.success('Schedule created');
      queryClient.invalidateQueries({
        queryKey: ['reportBuilder', 'schedules', id],
      });
      setScheduleFormOpen(false);
      setScheduleSubmitError(null);
      setScheduleSubmitErrorCode(null);
    },
    onError: (err: unknown) => {
      const body =
        (err as { response?: { data?: unknown } })?.response?.data ?? {};
      const { message, code } = flattenScheduleError(body);
      setScheduleSubmitError(message);
      setScheduleSubmitErrorCode(code);
    },
  });

  const updateScheduleMutation = useMutation({
    mutationFn: ({
      scheduleId,
      patch,
    }: {
      scheduleId: string;
      patch: Partial<ReportScheduleWritePayload>;
    }) => reportBuilderService.updateSchedule(id!, scheduleId, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ['reportBuilder', 'schedules', id],
      });
      setScheduleFormOpen(false);
      setEditingSchedule(null);
      setScheduleSubmitError(null);
      setScheduleSubmitErrorCode(null);
    },
    onError: (err: unknown) => {
      const body =
        (err as { response?: { data?: unknown } })?.response?.data ?? {};
      const { message, code } = flattenScheduleError(body);
      setScheduleSubmitError(message);
      setScheduleSubmitErrorCode(code);
    },
  });

  const deleteScheduleMutation = useMutation({
    mutationFn: (scheduleId: string) =>
      reportBuilderService.deleteSchedule(id!, scheduleId),
    onSuccess: () => {
      toast.success('Schedule deleted');
      queryClient.invalidateQueries({
        queryKey: ['reportBuilder', 'schedules', id],
      });
    },
    onError: () => {
      toast.error('Delete failed', 'Could not remove this schedule.');
    },
  });

  const definition = definitionQuery.data;
  const runs = runsQuery.data ?? [];
  const schedules = schedulesQuery.data ?? [];

  const groupByFields = useMemo(
    () => normaliseGroupBy(definition?.group_by_json),
    [definition?.group_by_json],
  );

  if (!id) return null;

  if (definitionQuery.isLoading) {
    return (
      <div className="p-6 text-sm text-gray-500" data-testid="detail-loading">
        Loading report…
      </div>
    );
  }

  if (definitionQuery.isError || !definition) {
    return (
      <div className="p-6 text-sm text-red-600" data-testid="detail-error">
        Report not found or you don&apos;t have access.
      </div>
    );
  }

  return (
    <div
      className="space-y-6 p-4 sm:p-6"
      data-testid="report-builder-detail-page"
    >
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => navigate('/admin/reports/builder')}
            className="rounded-md p-1.5 text-gray-500 hover:bg-gray-100"
            aria-label="Back to list"
          >
            <ArrowLeftIcon className="h-4 w-4" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {definition.name}
            </h1>
            <p className="mt-0.5 text-xs text-gray-500">
              <Badge variant="secondary">
                {DATA_SOURCE_LABELS[definition.data_source] ?? definition.data_source}
              </Badge>{' '}
              · updated {new Date(definition.updated_at).toLocaleString()}
            </p>
          </div>
        </div>

        <div className="flex gap-2">
          <Button
            variant="outline"
            leftIcon={<PencilSquareIcon className="h-4 w-4" />}
            onClick={() => navigate(`/admin/reports/builder/${id}/edit`)}
            data-testid="detail-edit"
          >
            Edit
          </Button>
          <Button
            leftIcon={<PlayIcon className="h-4 w-4" />}
            onClick={() => runMutation.mutate()}
            loading={runMutation.isPending}
            data-testid="detail-run"
          >
            Run now
          </Button>
          <Button
            variant="secondary"
            leftIcon={<ArrowDownTrayIcon className="h-4 w-4" />}
            onClick={() => exportMutation.mutate()}
            loading={exportMutation.isPending || exportRunId !== null}
            data-testid="detail-export"
          >
            Export CSV
          </Button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs>
        <TabsList>
          <TabsTrigger data-testid="tab-overview">Overview</TabsTrigger>
          <TabsTrigger data-testid="tab-preview">Preview</TabsTrigger>
          <TabsTrigger data-testid="tab-history">History</TabsTrigger>
          <TabsTrigger data-testid="tab-schedules">Schedules</TabsTrigger>
        </TabsList>

        <TabsPanels>
          {/* Overview */}
          <TabsContent>
            <div className="space-y-4 rounded-lg border border-gray-200 bg-white p-4" data-testid="overview-panel">
              {definition.description && (
                <p className="text-sm text-gray-700">{definition.description}</p>
              )}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Filters
                </h3>
                {definition.filters_json.length === 0 ? (
                  <p className="text-sm text-gray-400">None</p>
                ) : (
                  <ul className="mt-1 list-inside list-disc text-sm text-gray-700">
                    {definition.filters_json.map((f, i) => (
                      <li key={i}>
                        <code className="text-xs">
                          {f.field} {f.op} {JSON.stringify(f.value)}
                        </code>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Group by
                </h3>
                {groupByFields.length === 0 ? (
                  <p className="text-sm text-gray-400">None</p>
                ) : (
                  <p className="text-sm text-gray-700">
                    {groupByFields.map((g) => g.field).join(', ')}
                  </p>
                )}
              </div>

              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Aggregates
                </h3>
                {definition.aggregates_json.length === 0 ? (
                  <p className="text-sm text-gray-400">None</p>
                ) : (
                  <ul className="mt-1 list-inside list-disc text-sm text-gray-700">
                    {definition.aggregates_json.map((a, i) => (
                      <li key={i}>
                        <code className="text-xs">
                          {a.fn}({a.field}){a.alias ? ` as ${a.alias}` : ''}
                        </code>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </TabsContent>

          {/* Preview */}
          <TabsContent>
            <div className="space-y-3" data-testid="preview-panel">
              {previewResult === null && !previewError && !runMutation.isPending && (
                <p className="text-sm text-gray-500">
                  Click <strong>Run now</strong> to preview results.
                </p>
              )}
              {runMutation.isPending && (
                <p className="text-sm text-gray-500" data-testid="preview-loading">
                  Running report…
                </p>
              )}
              {(previewResult || previewError) && (
                <PreviewTable
                  rows={previewResult?.rows ?? []}
                  rowCount={previewResult?.row_count}
                  errorMessage={previewError}
                />
              )}
            </div>
          </TabsContent>

          {/* History */}
          <TabsContent>
            <div data-testid="history-panel">
              <RunHistoryTable
                runs={runs}
                isLoading={runsQuery.isLoading}
                onDownload={handleDownload}
                downloadingRunId={downloadingRunId}
              />
              {exportRunId && (
                <p
                  className="mt-2 text-xs text-gray-500"
                  data-testid="export-polling-status"
                >
                  Polling export status… (attempt {exportPollCount + 1})
                </p>
              )}
            </div>
          </TabsContent>

          {/* Schedules */}
          <TabsContent>
            <div className="space-y-3" data-testid="schedules-panel">
              <div className="flex justify-end">
                <Button
                  size="sm"
                  leftIcon={<PlusIcon className="h-4 w-4" />}
                  onClick={() => {
                    setEditingSchedule(null);
                    setScheduleSubmitError(null);
                    setScheduleSubmitErrorCode(null);
                    setScheduleFormOpen(true);
                  }}
                  data-testid="new-schedule-btn"
                >
                  New schedule
                </Button>
              </div>

              {schedules.length === 0 ? (
                <div
                  className="rounded-lg border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500"
                  data-testid="schedules-empty"
                >
                  No schedules yet.
                </div>
              ) : (
                <ul className="space-y-2">
                  {schedules.map((sch) => (
                    <li
                      key={sch.id}
                      className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-3"
                      data-testid={`schedule-${sch.id}`}
                    >
                      <div>
                        <p className="text-sm font-medium text-gray-800">
                          {sch.cadence}{' '}
                          {sch.cadence === 'weekly' &&
                            sch.run_at_day_of_week !== null &&
                            `(dow ${sch.run_at_day_of_week})`}
                          {sch.cadence === 'monthly' &&
                            sch.run_at_day_of_month !== null &&
                            `(dom ${sch.run_at_day_of_month})`}{' '}
                          at {sch.run_at_hour}:00 UTC
                        </p>
                        <p className="text-xs text-gray-500">
                          {sch.recipients_json.length} recipient
                          {sch.recipients_json.length === 1 ? '' : 's'} · last
                          status: {sch.last_run_status}
                          {sch.last_run_at
                            ? ` · ${new Date(sch.last_run_at).toLocaleString()}`
                            : ''}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <label className="inline-flex items-center gap-1 text-xs text-gray-600">
                          <input
                            type="checkbox"
                            checked={sch.enabled}
                            onChange={(e) =>
                              updateScheduleMutation.mutate({
                                scheduleId: sch.id,
                                patch: { enabled: e.target.checked },
                              })
                            }
                            data-testid={`schedule-toggle-${sch.id}`}
                            className="h-3.5 w-3.5 rounded border-gray-300 text-primary-600"
                          />
                          Enabled
                        </label>
                        <button
                          type="button"
                          onClick={() => {
                            setEditingSchedule(sch);
                            setScheduleSubmitError(null);
                            setScheduleSubmitErrorCode(null);
                            setScheduleFormOpen(true);
                          }}
                          data-testid={`edit-schedule-${sch.id}`}
                          aria-label="Edit schedule"
                          className="rounded-md p-1.5 text-gray-600 hover:bg-gray-100"
                        >
                          <PencilSquareIcon className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setConfirmDeleteSchedule(sch)}
                          data-testid={`delete-schedule-${sch.id}`}
                          aria-label="Delete schedule"
                          className="rounded-md p-1.5 text-red-500 hover:bg-red-50"
                        >
                          <TrashIcon className="h-4 w-4" />
                        </button>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </TabsContent>
        </TabsPanels>
      </Tabs>

      {/* Schedule dialog */}
      <ScheduleForm
        open={scheduleFormOpen}
        onClose={() => {
          setScheduleFormOpen(false);
          setEditingSchedule(null);
          setScheduleSubmitError(null);
          setScheduleSubmitErrorCode(null);
        }}
        initial={editingSchedule}
        submitError={scheduleSubmitError}
        submitErrorCode={scheduleSubmitErrorCode}
        isSubmitting={
          createScheduleMutation.isPending || updateScheduleMutation.isPending
        }
        onSubmit={async (payload) => {
          setScheduleSubmitError(null);
          setScheduleSubmitErrorCode(null);
          if (editingSchedule) {
            await updateScheduleMutation
              .mutateAsync({
                scheduleId: editingSchedule.id,
                patch: payload,
              })
              .catch(() => undefined);
          } else {
            await createScheduleMutation.mutateAsync(payload).catch(() => undefined);
          }
        }}
      />

      {/* Delete schedule confirm */}
      <ConfirmDialog
        isOpen={confirmDeleteSchedule !== null}
        onClose={() => setConfirmDeleteSchedule(null)}
        onConfirm={() => {
          if (confirmDeleteSchedule)
            deleteScheduleMutation.mutate(confirmDeleteSchedule.id);
          setConfirmDeleteSchedule(null);
        }}
        title="Delete schedule?"
        message="Scheduled deliveries will stop immediately."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        loading={deleteScheduleMutation.isPending}
      />
    </div>
  );
};

// ───────────────────────────────────────────────────────────────────────────
// Helpers
// ───────────────────────────────────────────────────────────────────────────

/**
 * Strip the field-name prefix and known error-code prefix from a DRF
 * field error string so the user sees plain English.
 *
 * Examples:
 *   "recipients_json: EXTERNAL_RECIPIENT_NOT_ALLOWED: a@x.com, b@x.com"
 *     → { message: "External recipients not allowed: a@x.com, b@x.com",
 *         code: "EXTERNAL_RECIPIENT_NOT_ALLOWED" }
 *
 *   "name: This field is required."
 *     → { message: "This field is required.", code: null }
 */
function parseFieldError(raw: string): { message: string; code: string | null } {
  // Strip leading "field_name: " prefix (first colon-space-delimited token).
  const withoutField = raw.replace(/^\w+:\s*/, '');
  // Match a SCREAMING_SNAKE_CASE error code at the start.
  const codeMatch = withoutField.match(/^([A-Z][A-Z0-9_]+):\s*(.*)/s);
  if (codeMatch) {
    const code = codeMatch[1];
    const rest = codeMatch[2].trim();
    if (code === 'EXTERNAL_RECIPIENT_NOT_ALLOWED') {
      return { message: `External recipients not allowed: ${rest}`, code };
    }
    // Other codes: just strip the code prefix.
    return { message: rest || withoutField, code };
  }
  return { message: withoutField || raw, code: null };
}

/** Flatten a DRF field-error dict into a user-facing { message, code } pair. */
function flattenScheduleError(body: unknown): { message: string; code: string | null } {
  if (!body || typeof body !== 'object') return { message: 'Validation failed.', code: null };
  const obj = body as Record<string, unknown>;
  if (typeof obj.detail === 'string') return { message: obj.detail, code: null };
  if (typeof obj.error === 'string') return { message: obj.error, code: null };
  // Field-level errors (e.g. recipients_json: [...])
  const out: string[] = [];
  let firstCode: string | null = null;
  for (const [_key, value] of Object.entries(obj)) {
    if (Array.isArray(value)) {
      for (const v of value) {
        const parsed = parseFieldError(String(v));
        if (parsed.code && !firstCode) firstCode = parsed.code;
        out.push(parsed.message);
      }
    } else if (typeof value === 'string') {
      const parsed = parseFieldError(value);
      if (parsed.code && !firstCode) firstCode = parsed.code;
      out.push(parsed.message);
    }
  }
  return out.length > 0
    ? { message: out.join('\n'), code: firstCode }
    : { message: 'Validation failed.', code: null };
}
