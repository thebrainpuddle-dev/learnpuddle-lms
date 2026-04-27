// src/pages/admin/ReportBuilderListPage.tsx
//
// List of saved ReportDefinitions. Each row has: name, data source, last run,
// quick actions (Run, Edit, Schedule, Delete).

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  PlusIcon,
  PlayIcon,
  PencilSquareIcon,
  TrashIcon,
  DocumentChartBarIcon,
} from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';
import { ConfirmDialog } from '../../components/common/ConfirmDialog';
import { useToast } from '../../components/common/Toast';
import { EmptyState } from '../../components/common';
import { Button } from '../../components/common/Button';
import { Badge } from '../../components/ui/badge';
import {
  reportBuilderService,
  type ReportDefinitionListItem,
} from '../../services/reportBuilderService';

const DATA_SOURCE_LABELS: Record<string, string> = {
  courses: 'Courses',
  teacher_progress: 'Teacher Progress',
  assignments: 'Assignments',
  quiz_attempts: 'Quiz Attempts',
  gamification: 'XP / Gamification',
  certifications: 'Certifications',
};

export const ReportBuilderListPage: React.FC = () => {
  usePageTitle('Report Builder');
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();

  const [confirmDelete, setConfirmDelete] =
    useState<ReportDefinitionListItem | null>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['reportBuilder', 'definitions'],
    queryFn: () => reportBuilderService.listDefinitions(),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => reportBuilderService.deleteDefinition(id),
    onSuccess: () => {
      toast.success('Report deleted', 'The definition was removed.');
      queryClient.invalidateQueries({
        queryKey: ['reportBuilder', 'definitions'],
      });
    },
    onError: () => {
      toast.error('Delete failed', 'Could not delete this report. Try again.');
    },
  });

  const runMutation = useMutation({
    mutationFn: (id: string) => reportBuilderService.runDefinition(id),
    onSuccess: (_data, id) => {
      toast.success('Report executed', 'Opening detail page with results…');
      navigate(`/admin/reports/builder/${id}`);
    },
    onError: (err: unknown) => {
      const status = (err as { response?: { status?: number } })?.response
        ?.status;
      const body =
        (err as { response?: { data?: { error?: string } } })?.response?.data
          ?.error ?? '';
      if (status === 503) {
        toast.error(
          'Service unavailable',
          'Report runs are temporarily unavailable. Try again in a minute.',
        );
      } else if (status === 429) {
        toast.error(
          'Rate limit exceeded',
          'Max 20 report runs per hour per school.',
        );
      } else if (body === 'ROW_CAP_EXCEEDED') {
        toast.error(
          'Too many rows',
          'The result exceeds 50,000 rows. Add filters to narrow it down.',
        );
      } else {
        toast.error('Run failed', 'Something went wrong. See the report detail page for details.');
      }
    },
  });

  const definitions = data ?? [];

  return (
    <div className="space-y-6 p-4 sm:p-6" data-testid="report-builder-list-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Report Builder</h1>
          <p className="mt-1 text-sm text-gray-500">
            Compose custom reports over courses, progress, assignments, quizzes,
            certifications and gamification data.
          </p>
        </div>
        <Button
          leftIcon={<PlusIcon className="h-4 w-4" />}
          onClick={() => navigate('/admin/reports/builder/new')}
          data-testid="new-report-btn"
        >
          New report
        </Button>
      </div>

      {isLoading ? (
        <div
          className="rounded-lg border border-gray-200 p-8 text-center text-sm text-gray-500"
          data-testid="list-loading"
        >
          Loading definitions…
        </div>
      ) : isError ? (
        <EmptyState
          title="Failed to load reports"
          description="We couldn't fetch your reports. Please refresh."
          icon={<DocumentChartBarIcon className="h-12 w-12 text-gray-300" />}
        />
      ) : definitions.length === 0 ? (
        <EmptyState
          title="No reports yet"
          description="Click “New report” to compose your first custom report."
          icon={<DocumentChartBarIcon className="h-12 w-12 text-gray-300" />}
        />
      ) : (
        <div
          className="overflow-x-auto rounded-lg border border-gray-200"
          data-testid="definition-table"
        >
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-medium text-gray-700">
                  Name
                </th>
                <th scope="col" className="px-3 py-2 text-left font-medium text-gray-700">
                  Data source
                </th>
                <th scope="col" className="px-3 py-2 text-left font-medium text-gray-700">
                  Last updated
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium text-gray-700">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 bg-white">
              {definitions.map((def) => (
                <tr key={def.id} data-testid={`definition-row-${def.id}`}>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() =>
                        navigate(`/admin/reports/builder/${def.id}`)
                      }
                      className="font-medium text-primary-700 hover:underline"
                      data-testid={`definition-name-${def.id}`}
                    >
                      {def.name}
                    </button>
                    {def.description && (
                      <p className="mt-0.5 max-w-md truncate text-xs text-gray-500">
                        {def.description}
                      </p>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <Badge variant="secondary">
                      {DATA_SOURCE_LABELS[def.data_source] ?? def.data_source}
                    </Badge>
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-600 whitespace-nowrap">
                    {new Date(def.updated_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex justify-end gap-1">
                      <button
                        type="button"
                        onClick={() => runMutation.mutate(def.id)}
                        disabled={runMutation.isPending}
                        data-testid={`run-${def.id}`}
                        aria-label={`Run ${def.name}`}
                        className="rounded-md p-1.5 text-emerald-600 hover:bg-emerald-50 disabled:opacity-50"
                      >
                        <PlayIcon className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          navigate(`/admin/reports/builder/${def.id}/edit`)
                        }
                        data-testid={`edit-${def.id}`}
                        aria-label={`Edit ${def.name}`}
                        className="rounded-md p-1.5 text-gray-600 hover:bg-gray-100"
                      >
                        <PencilSquareIcon className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmDelete(def)}
                        data-testid={`delete-${def.id}`}
                        aria-label={`Delete ${def.name}`}
                        className="rounded-md p-1.5 text-red-500 hover:bg-red-50"
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

      <ConfirmDialog
        isOpen={confirmDelete !== null}
        onClose={() => setConfirmDelete(null)}
        onConfirm={() => {
          if (confirmDelete) deleteMutation.mutate(confirmDelete.id);
          setConfirmDelete(null);
        }}
        title={`Delete "${confirmDelete?.name ?? ''}"?`}
        message="This report will be removed. Scheduled deliveries will stop."
        confirmLabel="Delete"
        cancelLabel="Cancel"
        variant="danger"
        loading={deleteMutation.isPending}
      />
    </div>
  );
};
