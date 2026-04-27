// src/pages/admin/ai-course-generator/AIGeneratorHome.tsx
// Upload/source page — admin picks source, fills options, submits to enqueue a job.

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SparklesIcon } from '@heroicons/react/24/outline';
import { useToast } from '../../../components/common/Toast';
import {
  aiCourseGeneratorService,
  MAX_FILE_BYTES,
  validateUrlHost,
} from '../../../services/aiCourseGeneratorService';
import type { SourceType } from '../../../services/aiCourseGeneratorService';
import { SourcePicker, FILE_SOURCE_TYPES } from './components/SourcePicker';

// ─── Error mapper ─────────────────────────────────────────────────────────────

export function mapApiError(err: any): string {
  const status = err?.response?.status;
  const code = err?.response?.data?.error as string | undefined;
  const detail = err?.response?.data?.detail as string | undefined;

  if (status === 413 || code === 'FILE_TOO_LARGE') {
    return 'File exceeds 20 MB. Please use a smaller file.';
  }
  if (code === 'INVALID_URL_HOST') {
    return 'Only YouTube and Vimeo URLs are supported.';
  }
  if (code === 'COST_LIMIT_EXCEEDED') {
    return 'This source is too large. Please try a shorter document.';
  }
  if (status === 429 || status === 503 || code === 'RATE_LIMIT_EXCEEDED' || code === 'SERVICE_UNAVAILABLE') {
    return "You've hit the hourly generation limit. Try again in an hour.";
  }
  return detail ?? 'Something went wrong. Please try again.';
}

// ─── Component ────────────────────────────────────────────────────────────────

export const AIGeneratorHome: React.FC = () => {
  const navigate = useNavigate();
  const toast = useToast();

  const [sourceType, setSourceType] = useState<SourceType>('pdf');
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState('');
  const [titleHint, setTitleHint] = useState('');
  const [targetModuleCount, setTargetModuleCount] = useState(5);
  const [submitting, setSubmitting] = useState(false);

  // Inline errors
  const [fileError, setFileError] = useState<string | null>(null);
  const [urlError, setUrlError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const isFileType = FILE_SOURCE_TYPES.includes(sourceType);

  // Validate on file change
  const handleFileChange = (f: File | null) => {
    setFile(f);
    if (f && f.size > MAX_FILE_BYTES) {
      setFileError('File exceeds 20 MB limit.');
    } else {
      setFileError(null);
    }
  };

  // Validate on URL change
  const handleUrlChange = (value: string) => {
    setUrl(value);
    if (value) {
      const err = validateUrlHost(value);
      setUrlError(err);
    } else {
      setUrlError(null);
    }
  };

  const canSubmit = (): boolean => {
    if (isFileType) {
      return !!file && !fileError;
    }
    return !!url && !urlError;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    // Re-validate before submit
    if (isFileType) {
      if (!file) {
        setFileError('Please choose a file.');
        return;
      }
      if (file.size > MAX_FILE_BYTES) {
        setFileError('File exceeds 20 MB limit.');
        return;
      }
    } else {
      if (!url.trim()) {
        setUrlError('Please enter a URL.');
        return;
      }
      const err = validateUrlHost(url);
      if (err) {
        setUrlError(err);
        return;
      }
    }

    const formData = new FormData();
    formData.append('source_type', sourceType);
    if (isFileType && file) {
      formData.append('file', file);
    } else {
      formData.append('url', url.trim());
    }
    if (titleHint.trim()) {
      formData.append('title_hint', titleHint.trim());
    }
    formData.append('target_module_count', String(targetModuleCount));

    setSubmitting(true);
    try {
      const result = await aiCourseGeneratorService.createJob(formData);
      toast.success('Generation started', 'Your course outline will be ready shortly.');
      navigate(`/admin/ai-course-generator/jobs/${result.job_id}`);
    } catch (err: any) {
      setFormError(mapApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <div className="flex items-center gap-3 mb-1">
          <SparklesIcon className="h-6 w-6 text-primary-600" />
          <h1 className="text-2xl font-bold text-gray-900">AI Course Generator</h1>
        </div>
        <p className="text-gray-500 text-sm">
          Upload a document or paste a video URL to automatically generate a course outline.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        noValidate
        className="space-y-5 rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
      >
        {/* Source picker */}
        <SourcePicker
          sourceType={sourceType}
          onSourceTypeChange={setSourceType}
          file={file}
          onFileChange={handleFileChange}
          url={url}
          onUrlChange={handleUrlChange}
          fileError={fileError}
          urlError={urlError}
        />

        {/* Title hint */}
        <div>
          <label
            htmlFor="title-hint"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            Course title hint{' '}
            <span className="text-gray-400 font-normal">(optional)</span>
          </label>
          <input
            id="title-hint"
            type="text"
            value={titleHint}
            onChange={(e) => setTitleHint(e.target.value)}
            placeholder="e.g. Introduction to Python"
            maxLength={120}
            className="block w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>

        {/* Target module count */}
        <div>
          <label
            htmlFor="module-count"
            className="block text-sm font-medium text-gray-700 mb-1"
          >
            Target number of modules{' '}
            <span className="text-gray-400 font-normal">(3–12)</span>
          </label>
          <input
            id="module-count"
            type="number"
            min={3}
            max={12}
            value={targetModuleCount}
            onChange={(e) =>
              setTargetModuleCount(
                Math.max(3, Math.min(12, Number(e.target.value)))
              )
            }
            className="block w-32 rounded-lg border border-gray-300 px-3 py-2.5 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
        </div>

        {/* Global error */}
        {formError && (
          <div
            role="alert"
            data-testid="form-error"
            className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700"
          >
            {formError}
          </div>
        )}

        {/* Submit */}
        <div className="flex items-center justify-between pt-2">
          <button
            type="button"
            onClick={() => navigate('/admin/ai-course-generator')}
            className="cursor-pointer text-sm text-gray-500 hover:text-gray-700"
          >
            View past jobs
          </button>
          <button
            type="submit"
            disabled={submitting || !canSubmit()}
            data-testid="submit-btn"
            className="cursor-pointer inline-flex items-center gap-2 rounded-lg bg-primary-600 px-5 py-2.5 text-sm font-medium text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 transition-colors"
          >
            {submitting ? (
              <>
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                Submitting…
              </>
            ) : (
              <>
                <SparklesIcon className="h-4 w-4" />
                Generate outline
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
