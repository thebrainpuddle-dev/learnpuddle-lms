// src/pages/admin/ai-course-generator/AIGeneratorJobsList.tsx
// Paginated jobs table with status/created_by filters and per-row delete.

import React, { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  TrashIcon,
  EyeIcon,
  PlusIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { useToast } from '../../../components/common/Toast';
import {
  aiCourseGeneratorService,
} from '../../../services/aiCourseGeneratorService';
import type { JobListItem, JobStatus } from '../../../services/aiCourseGeneratorService';
import { JobStatusBadge } from './components/JobStatusBadge';

// ─── Delete confirmation modal ────────────────────────────────────────────────

interface DeleteModalProps {
  job: JobListItem;
  onConfirm: () => void;
  onCancel: () => void;
  loading: boolean;
}

const DeleteModal: React.FC<DeleteModalProps> = ({
  job,
  onConfirm,
  onCancel,
  loading,
}) => (
  <div
    role="dialog"
    aria-modal="true"
    aria-labelledby="delete-modal-title"
    data-testid="delete-modal"
    className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
  >
    <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
      <div className="flex items-start gap-3 mb-4">
        <ExclamationTriangleIcon className="h-6 w-6 text-amber-500 shrink-0 mt-0.5" />
        <div>
          <h2
            id="delete-modal-title"
            className="text-lg font-semibold text-gray-900"
          >
            Delete this job?
          </h2>
          <p className="mt-1 text-sm text-gray-600">
            The job record and extracted text will be permanently removed.
          </p>
          {job.draft_course_id && (
            <div className="mt-3 rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-700">
              <strong>Note:</strong> The draft course this job created will
              NOT be deleted. Go to Courses to remove it separately.
            </div>
          )}
        </div>
      </div>
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
          data-testid="confirm-delete-btn"
          className="cursor-pointer inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-red-500"
        >
          {loading ? (
            <>
              <span className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
              Deleting…
            </>
          ) : (
            <>
              <TrashIcon className="h-4 w-4" />
              Delete
            </>
          )}
        </button>
      </div>
    </div>
  </div>
);

// ─── Status filter options ────────────────────────────────────────────────────

const STATUS_OPTIONS: { value: JobStatus | ''; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'pending', label: 'Pending' },
  { value: 'extracting', label: 'Extracting' },
  { value: 'llm_outlining', label: 'Generating Outline' },
  { value: 'materialising', label: 'Materialising' },
  { value: 'succeeded', label: 'Succeeded' },
  { value: 'failed', label: 'Failed' },
];

const PAGE_SIZE = 20;

// ─── Component ────────────────────────────────────────────────────────────────

export const AIGeneratorJobsList: React.FC = () => {
  const navigate = useNavigate();
  const toast = useToast();

  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<JobStatus | ''>('');
  const [createdByFilter, setCreatedByFilter] = useState('');
  const [page, setPage] = useState(1);
  const [jobToDelete, setJobToDelete] = useState<JobListItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await aiCourseGeneratorService.listJobs({
        status: statusFilter || undefined,
        created_by: createdByFilter.trim() || undefined,
      });
      setJobs(data);
      setPage(1);
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? 'Failed to load jobs.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter, createdByFilter]);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  const handleDelete = async () => {
    if (!jobToDelete) return;
    setDeleting(true);
    try {
      await aiCourseGeneratorService.deleteJob(jobToDelete.id);
      toast.success('Job deleted', 'The generation job has been removed.');
      setJobToDelete(null);
      await loadJobs();
    } catch (err: any) {
      toast.error('Delete failed', err?.response?.data?.detail ?? 'Please try again.');
    } finally {
      setDeleting(false);
    }
  };

  // Pagination
  const totalPages = Math.max(1, Math.ceil(jobs.length / PAGE_SIZE));
  const paginatedJobs = jobs.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return iso;
    }
  };

  return (
    <>
      <div className="space-y-5">
        {/* Page header */}
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-900">AI Course Generation Jobs</h1>
          <button
            type="button"
            onClick={() => navigate('/admin/ai-course-generator/new')}
            className="cursor-pointer inline-flex items-center gap-2 rounded-lg bg-primary-600 px-4 py-2 text-sm font-medium text-white hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <PlusIcon className="h-4 w-4" />
            New job
          </button>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Status
            </label>
            <select
              data-testid="status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as JobStatus | '')}
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">
              Created by (email)
            </label>
            <input
              type="text"
              data-testid="created-by-filter"
              value={createdByFilter}
              onChange={(e) => setCreatedByFilter(e.target.value)}
              placeholder="Filter by email"
              className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
            />
          </div>
        </div>

        {/* Table / states */}
        {loading ? (
          <div className="flex items-center justify-center py-16 gap-3 text-gray-400">
            <span className="h-5 w-5 animate-spin rounded-full border-2 border-primary-600 border-t-transparent" />
            Loading jobs…
          </div>
        ) : error ? (
          <div role="alert" className="rounded-lg bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            {error}
          </div>
        ) : jobs.length === 0 ? (
          <div className="rounded-lg border-2 border-dashed border-gray-200 p-12 text-center">
            <p className="text-gray-500 font-medium mb-2">No jobs yet</p>
            <button
              type="button"
              onClick={() => navigate('/admin/ai-course-generator/new')}
              className="cursor-pointer text-sm text-primary-600 hover:underline"
            >
              Generate your first course outline
            </button>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-gray-200 bg-white shadow-sm">
            <table className="min-w-full divide-y divide-gray-200 text-sm">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
                    ID
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
                    Source
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
                    Status
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
                    Created by
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
                    Created at
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-gray-400">
                    Draft course
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-gray-400">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {paginatedJobs.map((job) => (
                  <tr
                    key={job.id}
                    data-testid={`job-row-${job.id}`}
                    className="hover:bg-gray-50 transition-colors"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-gray-400 max-w-[120px] truncate">
                      {job.id}
                    </td>
                    <td className="px-4 py-3 capitalize text-gray-700">
                      {job.source_type}
                    </td>
                    <td className="px-4 py-3">
                      <JobStatusBadge status={job.status} />
                    </td>
                    <td className="px-4 py-3 text-gray-700 truncate max-w-[160px]">
                      {job.created_by_email ?? '—'}
                    </td>
                    <td className="px-4 py-3 text-gray-500 whitespace-nowrap">
                      {formatDate(job.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      {job.draft_course_id ? (
                        <button
                          type="button"
                          onClick={() =>
                            navigate(`/admin/courses/${job.draft_course_id}/edit`)
                          }
                          className="cursor-pointer text-xs text-primary-600 hover:underline"
                        >
                          Open editor
                        </button>
                      ) : (
                        <span className="text-gray-400">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          type="button"
                          onClick={() =>
                            navigate(
                              `/admin/ai-course-generator/jobs/${job.id}`
                            )
                          }
                          title="View job"
                          className="cursor-pointer rounded p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50"
                        >
                          <EyeIcon className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setJobToDelete(job)}
                          data-testid={`delete-btn-${job.id}`}
                          title="Delete job"
                          className="cursor-pointer rounded p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50"
                        >
                          <TrashIcon className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between text-sm text-gray-500">
            <span>
              Showing {(page - 1) * PAGE_SIZE + 1}–
              {Math.min(page * PAGE_SIZE, jobs.length)} of {jobs.length}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
                className="cursor-pointer rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-40 disabled:cursor-default"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={page === totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="cursor-pointer rounded-lg border border-gray-300 px-3 py-1.5 text-sm hover:bg-gray-50 disabled:opacity-40 disabled:cursor-default"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {jobToDelete && (
        <DeleteModal
          job={jobToDelete}
          onConfirm={handleDelete}
          onCancel={() => setJobToDelete(null)}
          loading={deleting}
        />
      )}
    </>
  );
};
