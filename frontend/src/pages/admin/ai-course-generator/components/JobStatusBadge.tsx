// src/pages/admin/ai-course-generator/components/JobStatusBadge.tsx

import React from 'react';
import type { JobStatus } from '../../../../services/aiCourseGeneratorService';

interface JobStatusBadgeProps {
  status: JobStatus;
}

const STATUS_CONFIG: Record<
  JobStatus,
  { label: string; className: string }
> = {
  pending: {
    label: 'Pending',
    className: 'bg-gray-100 text-gray-700',
  },
  extracting: {
    label: 'Extracting',
    className: 'bg-blue-100 text-blue-700',
  },
  llm_outlining: {
    label: 'Generating Outline',
    className: 'bg-indigo-100 text-indigo-700',
  },
  materialising: {
    label: 'Creating Course',
    className: 'bg-amber-100 text-amber-700',
  },
  succeeded: {
    label: 'Succeeded',
    className: 'bg-emerald-100 text-emerald-700',
  },
  failed: {
    label: 'Failed',
    className: 'bg-red-100 text-red-700',
  },
};

export const JobStatusBadge: React.FC<JobStatusBadgeProps> = ({ status }) => {
  const config = STATUS_CONFIG[status] ?? {
    label: status,
    className: 'bg-gray-100 text-gray-700',
  };

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${config.className}`}
    >
      {config.label}
    </span>
  );
};
