// src/pages/admin/ai-course-generator/AIGeneratorJobDetail.tsx
// Polling view + outline review + materialise button.

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import { useToast } from '../../../components/common/Toast';
import {
  aiCourseGeneratorService,
  TERMINAL_STATES,
} from '../../../services/aiCourseGeneratorService';
import type { Job, Outline } from '../../../services/aiCourseGeneratorService';
import { validateOutline } from '../../../services/aiCourseGeneratorService';
import {
  useAiGeneratorStore,
  POLL_INTERVAL_MS,
  nextBackoffMs,
} from '../../../stores/aiGeneratorStore';
import { JobStatusBadge } from './components/JobStatusBadge';
import { OutlineEditor } from './components/OutlineEditor';

// ─── Materialise confirmation modal ──────────────────────────────────────────

interface ConfirmModalProps {
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
}

const ConfirmMaterialiseModal: React.FC<ConfirmModalProps> = ({
  onConfirm,
  onCancel,
  loading,
}) => (
  <div
    role="dialog"
    aria-modal="true"
    aria-labelledby="materialise-modal-title"
    className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
  >
    <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
      <h2
        id="materialise-modal-title"
        className="text-lg font-semibold text-gray-900 mb-2"
      >
        Create draft course?
      </h2>
      <p className="text-sm text-gray-600 mb-6">
        This creates a <strong>DRAFT</strong> course — nothing is published yet.
        You'll be redirected to the Course editor where you can review and
        publish.
      </p>
      <div className="flex gap-3 justify-end">
        <button
          type="button"
          onClick={onCancel}
          disabled={loading}
          className="cursor-pointer rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={loading}
          data-testid="confirm-materialise-btn"
          className="cursor-pointer inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          {loading ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              Creating…
            </>
          ) : (
            'Yes, create draft'
          )}
        </button>
      </div>
    </div>
  </div>
);

// ─── Progress stepper ─────────────────────────────────────────────────────────

const STEPS = [
  { key: 'pending', label: 'Queued' },
  { key: 'extracting', label: 'Extracting' },
  { key: 'llm_outlining', label: 'Generating outline' },
  { key: 'succeeded', label: 'Ready' },
];

const STEP_KEYS = STEPS.map((s) => s.key);

interface ProgressStepperProps {
  status: string;
  failed: boolean;
}

const ProgressStepper: React.FC<ProgressStepperProps> = ({ status, failed }) => {
  const currentIdx = STEP_KEYS.indexOf(status === 'failed' ? 'pending' : status);

  return (
    <ol className="flex items-center gap-0 mb-6">
      {STEPS.map((step, idx) => {
        const done = currentIdx > idx || status === 'succeeded';
        const active = idx === currentIdx && !failed;
        return (
          <li key={step.key} className="flex flex-1 items-center">
            <div className="flex flex-col items-center flex-1">
              <div
                className={`h-8 w-8 rounded-full flex items-center justify-center text-sm font-semibold transition-colors ${
                  failed && idx === 0
                    ? 'bg-red-100 text-red-600'
                    : done
                    ? 'bg-primary-600 text-white'
                    : active
                    ? 'border-2 border-primary-600 text-primary-600 bg-white'
                    : 'border-2 border-gray-200 text-gray-400 bg-white'
                }`}
              >
                {done && !active ? (
                  <CheckCircleIcon className="h-5 w-5" />
                ) : (
                  idx + 1
                )}
              </div>
              <span className="mt-1 text-xs text-gray-500 text-center leading-tight">
                {step.label}
              </span>
            </div>
            {idx < STEPS.length - 1 && (
              <div
                className={`flex-1 h-0.5 mx-1 ${
                  done ? 'bg-primary-600' : 'bg-gray-200'
                }`}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
};

// ─── Main component ───────────────────────────────────────────────────────────

export const AIGeneratorJobDetail: React.FC = () => {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const toast = useToast();

  const {
    cacheJob,
    jobCache,
    setOutlineEdit,
    outlineEdits,
    startPolling,
    stopPolling,
    setPollingBackoff,
    pollingRegistry,
  } = useAiGeneratorStore();

  const [job, setJob] = useState<Job | null>(jobId ? jobCache[jobId] ?? null : null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [outlineErrors, setOutlineErrors] = useState<Record<string, string>>({});
  const [showModal, setShowModal] = useState(false);
  const [materialising, setMaterialising] = useState(false);

  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  // ── Fetch job once ──────────────────────────────────────────────────────────
  const fetchJob = useCallback(async () => {
    if (!jobId) return;
    try {
      const data = await aiCourseGeneratorService.getJob(jobId);
      if (!mountedRef.current) return;
      setJob(data);
      cacheJob(data);
      setLoadError(null);

      // Reset backoff on success
      setPollingBackoff(jobId, POLL_INTERVAL_MS, 0);

      // Initialise local outline edit from server if not yet edited
      if (data.outline_json && !outlineEdits[jobId]) {
        setOutlineEdit(jobId, data.outline_json);
      }

      // Stop polling when terminal
      if (TERMINAL_STATES.includes(data.status)) {
        stopPolling(jobId);
      }
    } catch (err) {
      if (!mountedRef.current) return;
      // Backoff on network error
      const registry = pollingRegistry[jobId];
      const errCount = (registry?.errorCount ?? 0) + 1;
      const newBackoff = nextBackoffMs(registry?.backoffMs ?? POLL_INTERVAL_MS);
      setPollingBackoff(jobId, newBackoff, errCount);
    }
  }, [jobId, cacheJob, outlineEdits, setOutlineEdit, stopPolling, setPollingBackoff, pollingRegistry]);

  // ── Polling loop ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!jobId) return;
    mountedRef.current = true;
    startPolling(jobId);

    // Initial load
    fetchJob();

    const scheduleNext = () => {
      const registry = useAiGeneratorStore.getState().pollingRegistry[jobId];
      if (!registry || registry.pollingState === 'stopped') return;

      const interval = registry.backoffMs;
      // Read store via getState() inside the timer callback; avoid stale closure on outline/job changes
      pollingRef.current = setTimeout(async () => {
        if (!mountedRef.current) return;
        const latest = useAiGeneratorStore.getState().pollingRegistry[jobId];
        if (!latest || latest.pollingState === 'stopped') return;

        await fetchJob();
        scheduleNext();
      }, interval);
    };

    scheduleNext();

    return () => {
      mountedRef.current = false;
      stopPolling(jobId);
      if (pollingRef.current) {
        clearTimeout(pollingRef.current);
      }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  // ── Materialise ─────────────────────────────────────────────────────────────
  const handleMaterialise = async () => {
    if (!jobId) return;
    setMaterialising(true);
    try {
      const editedOutline = outlineEdits[jobId] ?? job?.outline_json ?? undefined;
      const res = await aiCourseGeneratorService.materialiseJob(
        jobId,
        editedOutline
      );
      if (res.idempotent) {
        toast.info(
          'Draft already created',
          'Redirecting to Course editor…'
        );
      } else {
        toast.success('Draft course created', 'Redirecting to Course editor…');
      }
      navigate(`/admin/courses/${res.draft_course_id}/edit`);
    } catch (err: any) {
      toast.error(
        'Failed to create draft',
        err?.response?.data?.detail ?? 'Please try again.'
      );
    } finally {
      setMaterialising(false);
      setShowModal(false);
    }
  };

  // ── Retry (re-enqueue new job with same source) ──────────────────────────────
  const handleRetry = async () => {
    if (!job) return;
    const formData = new FormData();
    formData.append('source_type', job.source_type);
    const meta = job.source_metadata as any;
    if (meta?.url) {
      formData.append('url', meta.url);
    } else if (meta?.filename) {
      // Cannot re-upload the binary from metadata; guide admin
      toast.warning(
        'Re-upload required',
        'Please go back and re-submit the file.'
      );
      navigate('/admin/ai-course-generator/new');
      return;
    }
    if (meta?.title_hint) formData.append('title_hint', meta.title_hint);
    if (meta?.target_module_count)
      formData.append('target_module_count', String(meta.target_module_count));

    try {
      const res = await aiCourseGeneratorService.createJob(formData);
      toast.success('Retrying generation', 'A new job has been enqueued.');
      navigate(`/admin/ai-course-generator/jobs/${res.job_id}`);
    } catch (err: any) {
      toast.error('Failed to retry', err?.response?.data?.detail ?? 'Please try again.');
    }
  };

  // ── Outline change handler ──────────────────────────────────────────────────
  const handleOutlineChange = useCallback(
    (outline: Outline, errors: Record<string, string>) => {
      if (jobId) setOutlineEdit(jobId, outline);
      setOutlineErrors(errors);
    },
    [jobId, setOutlineEdit]
  );

  const hasOutlineErrors = Object.keys(outlineErrors).length > 0;
  const editedOutline = jobId ? outlineEdits[jobId] : null;
  const displayOutline = editedOutline ?? job?.outline_json ?? null;

  // ── Render ──────────────────────────────────────────────────────────────────

  if (loadError && !job) {
    return (
      <div className="max-w-2xl mx-auto mt-12 text-center">
        <ExclamationCircleIcon className="mx-auto h-12 w-12 text-red-400 mb-3" />
        <p className="text-gray-700 font-medium">{loadError}</p>
        <button
          type="button"
          onClick={() => navigate('/admin/ai-course-generator')}
          className="cursor-pointer mt-4 text-sm text-primary-600 hover:underline"
        >
          Back to jobs list
        </button>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="max-w-2xl mx-auto flex items-center justify-center mt-24 gap-3 text-gray-500">
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-primary-600 border-t-transparent" />
        Loading job…
      </div>
    );
  }

  const isTerminal = TERMINAL_STATES.includes(job.status);
  const isFailed = job.status === 'failed';
  const isSucceeded = job.status === 'succeeded';

  return (
    <>
      <div className="max-w-3xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Generation Job</h1>
            <p className="text-xs text-gray-400 font-mono mt-0.5">{job.id}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <JobStatusBadge status={job.status} />
            {!isTerminal && (
              <span
                data-testid="polling-indicator"
                className="flex items-center gap-1 text-xs text-gray-400"
              >
                <ArrowPathIcon className="h-3.5 w-3.5 animate-spin" />
                Polling…
              </span>
            )}
          </div>
        </div>

        {/* Stepper */}
        <ProgressStepper status={job.status} failed={isFailed} />

        {/* Reconnecting hint — shown when polling has hit ≥2 consecutive errors */}
        {!isTerminal && jobId && (pollingRegistry[jobId]?.errorCount ?? 0) >= 2 && (
          <span className="text-xs text-muted-foreground" data-testid="reconnecting-hint">Reconnecting…</span>
        )}

        {/* Job metadata */}
        <div className="rounded-lg border border-gray-200 bg-white p-4">
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
            <div>
              <dt className="text-xs text-gray-400 uppercase tracking-wide">Source</dt>
              <dd className="mt-1 font-medium text-gray-900 capitalize">
                {job.source_type}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-400 uppercase tracking-wide">Created by</dt>
              <dd className="mt-1 font-medium text-gray-900 truncate">
                {job.created_by_email ?? '—'}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-gray-400 uppercase tracking-wide">Provider</dt>
              <dd className="mt-1 font-medium text-gray-900">{job.provider ?? '—'}</dd>
            </div>
            <div>
              <dt className="text-xs text-gray-400 uppercase tracking-wide">Tokens</dt>
              <dd className="mt-1 font-medium text-gray-900">
                {job.tokens_prompt != null
                  ? `${job.tokens_prompt}+${job.tokens_completion}`
                  : '—'}
              </dd>
            </div>
          </dl>
        </div>

        {/* Failed state */}
        {isFailed && (
          <div
            data-testid="error-banner"
            role="alert"
            className="rounded-lg border border-red-200 bg-red-50 p-4 flex items-start gap-3"
          >
            <ExclamationCircleIcon className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
            <div className="flex-1 min-w-0">
              <p className="text-sm font-semibold text-red-700">Generation failed</p>
              <p className="mt-1 text-sm text-red-600 break-words">
                {job.error ?? 'An unknown error occurred.'}
              </p>
            </div>
            <button
              type="button"
              data-testid="retry-btn"
              onClick={handleRetry}
              className="cursor-pointer shrink-0 rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500"
            >
              Try again
            </button>
          </div>
        )}

        {/* Outline editor (succeeded state) */}
        {isSucceeded && displayOutline && (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">
                Review &amp; Edit Outline
              </h2>
              {job.draft_course_id ? (
                <span className="text-xs text-gray-400">
                  Already materialised
                </span>
              ) : null}
            </div>

            <OutlineEditor
              key={job.id} // reset editor if job changes
              initialOutline={displayOutline}
              onChange={handleOutlineChange}
            />

            {hasOutlineErrors && (
              <p
                data-testid="outline-validation-summary"
                role="alert"
                className="text-sm text-red-600"
              >
                Please fix the errors above before creating the draft course.
              </p>
            )}

            <div className="flex justify-end pt-2">
              <button
                type="button"
                disabled={hasOutlineErrors || materialising}
                data-testid="materialise-btn"
                onClick={() => setShowModal(true)}
                className="cursor-pointer inline-flex items-center gap-2 rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 transition-colors"
              >
                Create draft course
              </button>
            </div>
          </div>
        )}

        {/* Pending / in-progress state */}
        {!isTerminal && (
          <div className="rounded-lg border border-blue-100 bg-blue-50 p-6 text-center">
            <span className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-blue-100">
              <ArrowPathIcon className="h-6 w-6 animate-spin text-blue-600" />
            </span>
            <p className="text-sm font-medium text-blue-700">
              {job.status === 'pending' && 'Waiting in queue…'}
              {job.status === 'extracting' && 'Extracting content from source…'}
              {job.status === 'llm_outlining' && 'Generating course outline with AI…'}
              {job.status === 'materialising' && 'Creating course structure…'}
            </p>
            <p className="mt-1 text-xs text-blue-500">
              This page will update automatically.
            </p>
          </div>
        )}

        <div className="flex gap-4">
          <button
            type="button"
            onClick={() => navigate('/admin/ai-course-generator')}
            className="cursor-pointer text-sm text-gray-500 hover:text-gray-700"
          >
            ← All jobs
          </button>
          <button
            type="button"
            onClick={() => navigate('/admin/ai-course-generator/new')}
            className="cursor-pointer text-sm text-gray-500 hover:text-gray-700"
          >
            + New job
          </button>
        </div>
      </div>

      {showModal && (
        <ConfirmMaterialiseModal
          onConfirm={handleMaterialise}
          onCancel={() => setShowModal(false)}
          loading={materialising}
        />
      )}
    </>
  );
};
