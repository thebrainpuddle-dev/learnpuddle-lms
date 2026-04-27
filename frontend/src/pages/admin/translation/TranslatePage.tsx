// src/pages/admin/translation/TranslatePage.tsx
// Admin route: /admin/courses/:courseId/translate
// Locale picker → submit → poll job → show per-content review cards.

import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { LanguageIcon, ChevronDownIcon, ChevronRightIcon } from '@heroicons/react/24/outline';
import { useToast } from '../../../components/common/Toast';
import { translationService } from '../../../services/translationService';
import { fetchCourse } from '../course-editor/api';
import type { Course, Content } from '../course-editor/types';
import { LocalePicker } from './components/LocalePicker';
import { TranslationReview } from './TranslationReview';

// ─── ContentReviewCard ────────────────────────────────────────────────────────
// Collapsible card wrapping a TranslationReview for one content item.

interface ContentReviewCardProps {
  content: Content;
  courseId: string;
  jobId: string;
  targetLanguages: string[];
  onRetry: () => void;
  defaultOpen?: boolean;
}

const ContentReviewCard: React.FC<ContentReviewCardProps> = ({
  content,
  courseId,
  jobId,
  targetLanguages,
  onRetry,
  defaultOpen = false,
}) => {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div
      data-testid={`content-review-card-${content.id}`}
      className="rounded-xl border border-gray-200 bg-white overflow-hidden"
    >
      <button
        type="button"
        data-testid={`content-review-toggle-${content.id}`}
        onClick={() => setOpen((prev) => !prev)}
        className="w-full flex items-center justify-between gap-3 px-5 py-4 text-left cursor-pointer hover:bg-gray-50 transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary-500"
      >
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-sm font-semibold text-gray-800 truncate">
            {content.title}
          </span>
          <span className="shrink-0 inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-500">
            {content.content_type}
          </span>
        </div>
        {open
          ? <ChevronDownIcon className="h-4 w-4 shrink-0 text-gray-400" />
          : <ChevronRightIcon className="h-4 w-4 shrink-0 text-gray-400" />
        }
      </button>

      {open && (
        <div className="border-t border-gray-100 px-5 py-5">
          <TranslationReview
            courseId={courseId}
            jobId={jobId}
            targetLanguages={targetLanguages}
            onRetry={onRetry}
            contentId={content.id}
          />
        </div>
      )}
    </div>
  );
};

// ─── TranslatePage ────────────────────────────────────────────────────────────

export const TranslatePage: React.FC = () => {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const toast = useToast();

  const [selectedLocales, setSelectedLocales] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [targetLanguages, setTargetLanguages] = useState<string[]>([]);
  const [course, setCourse] = useState<Course | null>(null);
  const [courseLoading, setCourseLoading] = useState(false);

  // Fetch course details whenever we have a jobId so we can enumerate contents.
  useEffect(() => {
    if (!jobId || !courseId) return;
    let cancelled = false;
    setCourseLoading(true);
    fetchCourse(courseId)
      .then((data) => {
        if (!cancelled) setCourse(data);
      })
      .catch(() => {
        // Non-fatal: fall back to contentId-less review if fetch fails.
      })
      .finally(() => {
        if (!cancelled) setCourseLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, courseId]);

  // Flatten all content items from all modules.
  const allContents: Content[] = course
    ? course.modules.flatMap((m) => m.contents)
    : [];

  const canSubmit = selectedLocales.length > 0 && !submitting;

  const handleSubmit = async () => {
    if (!courseId || !canSubmit) return;
    setSubmitting(true);
    try {
      const res = await translationService.createCourseJob(courseId, selectedLocales);
      setTargetLanguages(selectedLocales);
      setJobId(res.job_id);
      toast.success('Translation started', 'Your translation job has been queued.');
    } catch (err: any) {
      const status = Number(err?.response?.status ?? 0);
      if (status === 404) {
        toast.error('Course not found', 'This course does not exist or you lack access.');
        navigate(`/admin/courses`);
        return;
      }
      if (status === 503 || status === 429) {
        toast.error(
          'Rate limit reached',
          'Translation service is rate-limited. Please wait and try again.'
        );
        return;
      }
      toast.error(
        'Failed to start translation',
        err?.response?.data?.detail ?? 'Please try again.'
      );
    } finally {
      setSubmitting(false);
    }
  };

  const handleRetry = async () => {
    // Reset job state and allow re-submission.
    // Preserve targetLanguages so the user doesn't have to re-select locales
    // after a retry (TASK-064 L6).
    setJobId(null);
    setCourse(null);
  };

  // If job has been created, show the review/polling view(s)
  if (jobId && targetLanguages.length > 0) {
    // Still loading course details — show a brief spinner before revealing cards
    if (courseLoading) {
      return (
        <div className="max-w-4xl mx-auto flex items-center justify-center mt-24 gap-3 text-gray-500">
          <span className="h-6 w-6 animate-spin rounded-full border-2 border-primary-600 border-t-transparent" />
          Loading course contents…
        </div>
      );
    }

    // Multiple contents — render collapsible per-content cards
    if (allContents.length > 1) {
      return (
        <div className="max-w-4xl mx-auto space-y-4">
          <div>
            <h2 className="text-xl font-bold text-gray-900">Translation Review</h2>
            <p className="text-sm text-gray-500 mt-0.5">
              {allContents.length} content items — expand each card to review translations.
            </p>
          </div>
          {allContents.map((content, idx) => (
            <ContentReviewCard
              key={content.id}
              content={content}
              courseId={courseId!}
              jobId={jobId}
              targetLanguages={targetLanguages}
              onRetry={handleRetry}
              defaultOpen={idx === 0}
            />
          ))}
        </div>
      );
    }

    // Single content or no contents fetched — render a single TranslationReview
    return (
      <div className="max-w-4xl mx-auto space-y-6">
        <TranslationReview
          courseId={courseId!}
          jobId={jobId}
          targetLanguages={targetLanguages}
          onRetry={handleRetry}
          contentId={allContents[0]?.id}
        />
      </div>
    );
  }

  // Locale picker + submit form
  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-50">
          <LanguageIcon className="h-6 w-6 text-primary-600" />
        </div>
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Translate Course</h1>
          <p className="text-sm text-gray-500">
            Auto-translate this course's content into one or more languages.
          </p>
        </div>
      </div>

      {/* Form card */}
      <div className="rounded-xl border border-gray-200 bg-white p-6 space-y-5">
        <div>
          <h2 className="text-sm font-semibold text-gray-700 mb-1">
            Target Languages
          </h2>
          <LocalePicker
            selected={selectedLocales}
            onChange={setSelectedLocales}
            disabled={submitting}
          />
        </div>

        {selectedLocales.length === 0 && (
          <p
            data-testid="no-locale-warning"
            className="text-sm text-amber-600"
          >
            Select at least one language to enable translation.
          </p>
        )}

        <div className="flex items-center gap-3 pt-2">
          <button
            type="button"
            data-testid="translate-submit-btn"
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="cursor-pointer inline-flex items-center gap-2 rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 transition-colors"
          >
            {submitting ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Starting…
              </>
            ) : (
              <>
                <LanguageIcon className="h-4 w-4" />
                Start Translation
              </>
            )}
          </button>

          <button
            type="button"
            onClick={() => courseId && navigate(`/admin/courses/${courseId}/edit`)}
            className="cursor-pointer rounded-lg border border-gray-300 px-4 py-2.5 text-sm font-medium text-gray-700 hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-gray-400 transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>

      {/* Info box */}
      <div className="rounded-lg bg-blue-50 border border-blue-100 p-4">
        <h3 className="text-sm font-semibold text-blue-700 mb-1">How it works</h3>
        <ul className="text-sm text-blue-600 space-y-1 list-disc list-inside">
          <li>Translation is powered by AI and runs in the background.</li>
          <li>You'll see the progress here — the page updates automatically.</li>
          <li>Once complete, review translated fields and approve or edit them.</li>
          <li>English (source) is never modified.</li>
        </ul>
      </div>
    </div>
  );
};
