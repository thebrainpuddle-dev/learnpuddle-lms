// src/pages/admin/translation/TranslationReview.tsx
// Side-by-side review page shown after a translation job succeeds.
// Retrieves translations per content-item and shows per-field diff + server-backed review actions.
// TASK-064b: review state is now persisted to the backend via per-field approve/reject/edit endpoints.

import React, { useEffect, useCallback, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowPathIcon,
  ExclamationCircleIcon,
  CheckCircleIcon,
  CloudArrowUpIcon,
} from '@heroicons/react/24/outline';
import { useToast } from '../../../components/common/Toast';
import {
  translationService,
  SUPPORTED_LOCALES,
} from '../../../services/translationService';
import type {
  TranslationJob,
  ContentTranslationReview,
  TranslationFieldKey,
} from '../../../services/translationService';
import {
  useTranslationStore,
  POLL_INTERVAL_MS,
  nextBackoffMs,
  isTerminalStatus,
} from '../../../stores/translationStore';
import { FieldDiff } from './components/FieldDiff';

// ─── Types ────────────────────────────────────────────────────────────────────

interface TranslationReviewProps {
  courseId: string;
  jobId: string;
  targetLanguages: string[];
  onRetry: () => void;
  /**
   * contentId to review.  When provided the component fetches per-field review
   * state from the server on mount and enables the per-field review actions and
   * publish button.
   *
   * When absent (course-level aggregate view, no individual content item
   * selected) the component falls back to showing aggregate fields_translated
   * summary only.
   *
   * TASK-064-L1: contentId is now threaded through from TranslatePage which
   * fetches the full course after job creation and passes each content's id
   * via ContentReviewCard.
   */
  contentId?: string;
}

// ─── Field config ─────────────────────────────────────────────────────────────

const TRANSLATABLE_FIELDS: { key: TranslationFieldKey; label: string }[] = [
  { key: 'title', label: 'Title' },
  { key: 'description', label: 'Description' },
  { key: 'body', label: 'Body' },
  { key: 'transcript', label: 'Transcript' },
];

// ─── Component ────────────────────────────────────────────────────────────────

export const TranslationReview: React.FC<TranslationReviewProps> = ({
  courseId,
  jobId,
  targetLanguages,
  onRetry,
  contentId,
}) => {
  const navigate = useNavigate();
  const toast = useToast();

  const {
    cacheJob,
    jobCache,
    startPolling,
    stopPolling,
    setPollingBackoff,
    pollingRegistry,
    fieldReviews,
    publishState,
    hydrateFromServer,
    approveField,
    rejectField,
    editField,
    publishTranslation,
  } = useTranslationStore();

  const [job, setJob] = useState<TranslationJob | null>(
    jobId ? jobCache[jobId] ?? null : null
  );
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeLocale, setActiveLocale] = useState(
    targetLanguages[0] ?? ''
  );
  const [publishBanner, setPublishBanner] = useState<{
    rowsPublished: number;
    skipped: Record<string, string>;
  } | null>(null);

  const pollingRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);

  // ── Fetch job ──────────────────────────────────────────────────────────────
  const fetchJob = useCallback(async () => {
    if (!jobId) return;
    try {
      const data = await translationService.getJob(jobId);
      if (!mountedRef.current) return;
      setJob(data);
      cacheJob(data);
      setLoadError(null);
      setPollingBackoff(jobId, POLL_INTERVAL_MS, 0);

      if (isTerminalStatus(data.status)) {
        stopPolling(jobId);
      }
    } catch (err: any) {
      if (!mountedRef.current) return;
      const status = Number(err?.response?.status ?? 0);
      if (status === 404) {
        setLoadError('Course not found or access denied.');
        stopPolling(jobId);
        navigate(`/admin/courses/${courseId}/edit`);
        return;
      }
      if (status === 503) {
        toast.error('Service unavailable', 'Translation service is temporarily unavailable.');
      }
      const registry = pollingRegistry[jobId];
      const errCount = (registry?.errorCount ?? 0) + 1;
      const newBackoff = nextBackoffMs(registry?.backoffMs ?? POLL_INTERVAL_MS);
      setPollingBackoff(jobId, newBackoff, errCount);
    }
  }, [jobId, cacheJob, stopPolling, setPollingBackoff, pollingRegistry, navigate, courseId, toast]);

  // ── Polling loop ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!jobId) return;
    mountedRef.current = true;
    startPolling(jobId);
    fetchJob();

    const scheduleNext = () => {
      const registry = useTranslationStore.getState().pollingRegistry[jobId];
      if (!registry || registry.pollingState === 'stopped') return;
      const interval = registry.backoffMs;
      pollingRef.current = setTimeout(async () => {
        if (!mountedRef.current) return;
        const latest = useTranslationStore.getState().pollingRegistry[jobId];
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

  // ── Hydrate per-content review state when job succeeds ─────────────────────
  useEffect(() => {
    if (!job || job.status !== 'success' || !activeLocale || !contentId) return;

    let cancelled = false;
    translationService.getContentTranslations(contentId, activeLocale)
      .then((resp) => {
        if (cancelled) return;
        // getContentTranslations returns ContentTranslationRow[] which lacks
        // review fields.  Cast conservatively — the backend actually returns
        // ContentTranslationReviewSerializer rows on the same endpoint when
        // review fields have been written.  If the row has no review_status the
        // hydrateFromServer helper treats it as 'pending'.
        hydrateFromServer(
          contentId,
          activeLocale,
          resp.rows as unknown as ContentTranslationReview[]
        );
      })
      .catch(() => {
        // Non-fatal: review state simply stays 'pending' if fetch fails.
      });

    return () => {
      cancelled = true;
    };
  }, [job, activeLocale, contentId, hydrateFromServer]);

  // ── Field review helpers ────────────────────────────────────────────────────

  const getFieldReview = (fieldKey: TranslationFieldKey) => {
    if (!contentId) {
      // Fallback: use legacy jobId-keyed store entry for course-level view
      return fieldReviews[`${jobId}:${activeLocale}:${fieldKey}`];
    }
    return fieldReviews[`${contentId}:${activeLocale}:${fieldKey}`];
  };

  const handleApprove = async (fieldKey: TranslationFieldKey) => {
    if (!contentId) return;
    await approveField(contentId, fieldKey, activeLocale, toast);
  };

  const handleReject = async (fieldKey: TranslationFieldKey) => {
    if (!contentId) return;
    await rejectField(contentId, fieldKey, activeLocale, toast);
  };

  // TODO (TASK-064 L2): split edit vs approve — needs backend status=pending support.
  // The backend PUT .../fields/{field}/edit/ always sets review_status='approved'
  // (see backend/apps/translations/views.py edit_translation_field). To support a
  // "Save draft" path that keeps status='pending', the backend endpoint needs to
  // accept an optional `auto_approve` flag or a separate edit-without-approve
  // endpoint. Until then, handleSaveEdit always approves on edit (current behaviour).
  const handleSaveEdit = async (fieldKey: TranslationFieldKey, text: string) => {
    if (!contentId) return;
    await editField(contentId, fieldKey, activeLocale, text, toast);
  };

  const handlePublish = async () => {
    if (!contentId) return;
    const pubKey = `${contentId}:${activeLocale}`;
    if (publishState[pubKey] === 'publishing') return;

    setPublishBanner(null);
    const result = await publishTranslation(contentId, activeLocale, toast);
    if (result) {
      setPublishBanner({ rowsPublished: result.rows_published, skipped: result.skipped });
    }
  };

  // ── Render ──────────────────────────────────────────────────────────────────

  if (loadError && !job) {
    return (
      <div
        data-testid="translation-load-error"
        className="max-w-2xl mx-auto mt-12 text-center"
      >
        <ExclamationCircleIcon className="mx-auto h-12 w-12 text-red-400 mb-3" />
        <p className="text-gray-700 font-medium">{loadError}</p>
      </div>
    );
  }

  if (!job) {
    return (
      <div className="max-w-2xl mx-auto flex items-center justify-center mt-24 gap-3 text-gray-500">
        <span className="h-6 w-6 animate-spin rounded-full border-2 border-primary-600 border-t-transparent" />
        Loading translation job…
      </div>
    );
  }

  const isTerminal = isTerminalStatus(job.status);
  const isFailed = job.status === 'failed';
  const isSucceeded = job.status === 'success';
  const pubKey = contentId ? `${contentId}:${activeLocale}` : null;
  const currentPublishState = pubKey ? (publishState[pubKey] ?? 'idle') : 'idle';
  const isPublishing = currentPublishState === 'publishing';
  const isPublished = currentPublishState === 'published';

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-900">Translation Job</h2>
          <p className="text-xs text-gray-400 font-mono mt-0.5">{job.id}</p>
        </div>
        <div className="flex items-center gap-2">
          <span
            data-testid="job-status-badge"
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
              isFailed
                ? 'bg-red-100 text-red-700'
                : isSucceeded
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-blue-100 text-blue-700'
            }`}
          >
            {job.status}
          </span>
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

      {/* In-progress state */}
      {!isTerminal && (
        <div
          data-testid="translation-pending-banner"
          className="rounded-lg border border-blue-100 bg-blue-50 p-6 text-center"
        >
          <span className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-blue-100">
            <ArrowPathIcon className="h-6 w-6 animate-spin text-blue-600" />
          </span>
          <p className="text-sm font-medium text-blue-700">
            {job.status === 'pending' && 'Translation queued — waiting for worker…'}
            {job.status === 'running' && 'Translation in progress…'}
          </p>
          <p className="mt-1 text-xs text-blue-500">
            This page will update automatically.
          </p>
        </div>
      )}

      {/* Failed state */}
      {isFailed && (
        <div
          data-testid="translation-error-banner"
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 p-4 flex items-start gap-3"
        >
          <ExclamationCircleIcon className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-red-700">Translation failed</p>
            <p className="mt-1 text-sm text-red-600 break-words">
              {job.error || 'An unknown error occurred.'}
            </p>
          </div>
          <button
            type="button"
            data-testid="translation-retry-btn"
            onClick={onRetry}
            className="cursor-pointer shrink-0 rounded-lg bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500"
          >
            Retry
          </button>
        </div>
      )}

      {/* Succeeded state — show summary + locale tabs */}
      {isSucceeded && (
        <div className="space-y-4">
          {/* Success summary */}
          <div
            data-testid="translation-success-summary"
            className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 flex items-center gap-3"
          >
            <CheckCircleIcon className="h-5 w-5 text-emerald-500 shrink-0" />
            <div>
              <p className="text-sm font-semibold text-emerald-700">
                Translation complete
              </p>
              <p className="text-xs text-emerald-600">
                {job.fields_translated} field
                {job.fields_translated !== 1 ? 's' : ''} translated across{' '}
                {job.target_languages.length} language
                {job.target_languages.length !== 1 ? 's' : ''}.
              </p>
            </div>
          </div>

          {/* Locale tabs */}
          {targetLanguages.length > 1 && (
            <div className="border-b border-gray-200">
              <nav className="-mb-px flex gap-4 overflow-x-auto">
                {targetLanguages.map((code) => {
                  const locale = SUPPORTED_LOCALES.find((l) => l.code === code);
                  return (
                    <button
                      key={code}
                      type="button"
                      data-testid={`locale-tab-${code}`}
                      onClick={() => setActiveLocale(code)}
                      className={`py-3 px-1 border-b-2 font-medium text-sm transition-colors whitespace-nowrap cursor-pointer ${
                        activeLocale === code
                          ? 'border-primary-500 text-primary-600'
                          : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                      }`}
                    >
                      {locale?.label ?? code}
                    </button>
                  );
                })}
              </nav>
            </div>
          )}

          {/* Review instructions */}
          <div className="rounded-lg bg-amber-50 border border-amber-200 p-3">
            <p className="text-sm text-amber-700">
              Review the translations below. Use <strong>Approve</strong>,{' '}
              <strong>Reject</strong>, or <strong>Edit</strong> to mark each
              field.{' '}
              {contentId
                ? 'Review decisions are saved to the server and survive page refreshes.'
                : 'To load per-field content, visit individual content items in the Course editor.'}
            </p>
          </div>

          {/* Publish result banner */}
          {publishBanner && (
            <div
              data-testid="publish-result-banner"
              className="rounded-lg border border-blue-200 bg-blue-50 p-3 flex items-start gap-2"
            >
              <CloudArrowUpIcon className="h-5 w-5 text-blue-500 shrink-0 mt-0.5" />
              <div className="text-sm text-blue-700">
                <span className="font-semibold">
                  {publishBanner.rowsPublished} field
                  {publishBanner.rowsPublished !== 1 ? 's' : ''} published.
                </span>
                {Object.keys(publishBanner.skipped).length > 0 && (
                  <span className="ml-1">
                    Skipped:{' '}
                    {Object.entries(publishBanner.skipped)
                      .map(([f, reason]) => `${f} (${reason})`)
                      .join(', ')}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Per-field review */}
          <div className="space-y-3">
            {TRANSLATABLE_FIELDS.map(({ key, label }) => {
              const review = getFieldReview(key);
              return (
                <FieldDiff
                  key={key}
                  fieldKey={key}
                  fieldLabel={label}
                  sourceText=""
                  translatedText=""
                  reviewStatus={review?.status ?? 'pending'}
                  editedText={review?.editedText ?? null}
                  onApprove={() => handleApprove(key)}
                  onReject={() => handleReject(key)}
                  onSaveEdit={(text) => handleSaveEdit(key, text)}
                />
              );
            })}
          </div>

          {/* Publish button — only shown when a contentId is available */}
          {contentId && (
            <div
              data-testid="publish-section"
              className="flex items-center justify-end pt-2 border-t border-gray-100"
            >
              <button
                type="button"
                data-testid="publish-translation-btn"
                onClick={handlePublish}
                disabled={isPublishing || isPublished}
                className="cursor-pointer inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 transition-colors"
              >
                {isPublishing ? (
                  <>
                    <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Publishing…
                  </>
                ) : isPublished ? (
                  <>
                    <CheckCircleIcon className="h-4 w-4" />
                    Published
                  </>
                ) : (
                  <>
                    <CloudArrowUpIcon className="h-4 w-4" />
                    Publish translation
                  </>
                )}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Back navigation */}
      <div className="flex gap-4 pt-2">
        <button
          type="button"
          data-testid="back-to-course-btn"
          onClick={() => navigate(`/admin/courses/${courseId}/edit`)}
          className="cursor-pointer text-sm text-gray-500 hover:text-gray-700"
        >
          ← Back to Course editor
        </button>
      </div>
    </div>
  );
};
