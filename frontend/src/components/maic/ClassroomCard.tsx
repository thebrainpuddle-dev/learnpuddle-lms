// src/components/maic/ClassroomCard.tsx
//
// Card component for the classroom library grid. Shows title, description,
// status badge, scene count, estimated duration, and created date.

import React from 'react';
import { Clock, Layers, Calendar } from 'lucide-react';
import type { MAICClassroomMeta } from '../../types/maic';
import { cn } from '../../lib/utils';

interface ClassroomCardProps {
  classroom: MAICClassroomMeta;
  onClick: () => void;
}

const statusConfig: Record<MAICClassroomMeta['status'], { label: string; classes: string }> = {
  DRAFT: { label: 'Draft', classes: 'bg-gray-100 text-gray-600' },
  GENERATING: { label: 'Generating', classes: 'bg-yellow-100 text-yellow-700 animate-pulse' },
  READY: { label: 'Ready', classes: 'bg-green-100 text-green-700' },
  FAILED: { label: 'Failed', classes: 'bg-red-100 text-red-700' },
  ARCHIVED: { label: 'Archived', classes: 'bg-gray-100 text-gray-500' },
};

function formatDate(dateStr: string): string {
  try {
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    }).format(new Date(dateStr));
  } catch {
    return dateStr;
  }
}

export const ClassroomCard = React.memo<ClassroomCardProps>(function ClassroomCard({
  classroom,
  onClick,
}) {
  const status = statusConfig[classroom.status] || statusConfig.DRAFT;

  return (
    <button
      type="button"
      onClick={onClick}
      data-testid="classroom-card"
      className={cn(
        'group w-full text-left rounded-xl border border-gray-200 bg-white p-5',
        'shadow-sm hover:shadow-md hover:border-gray-300',
        'transition-all duration-200',
        'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
      )}
      aria-label={`Open classroom: ${classroom.title}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <h3 className="text-base font-semibold text-gray-900 line-clamp-2 group-hover:text-primary-600 transition-colors">
          {classroom.title}
        </h3>
        <span
          className={cn(
            'shrink-0 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
            status.classes,
          )}
        >
          {status.label}
        </span>
      </div>

      {/* Description */}
      {classroom.description && (
        <p className="text-sm text-gray-500 line-clamp-2 mb-3">
          {classroom.description}
        </p>
      )}

      {/* Meta row */}
      <div className="flex items-center gap-4 text-xs text-gray-400">
        <span className="inline-flex items-center gap-1">
          <Layers className="h-3.5 w-3.5" aria-hidden="true" />
          {classroom.scene_count} scene{classroom.scene_count !== 1 ? 's' : ''}
        </span>

        {classroom.estimated_minutes > 0 && (
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3.5 w-3.5" aria-hidden="true" />
            {classroom.estimated_minutes} min
          </span>
        )}

        <span className="inline-flex items-center gap-1 ml-auto">
          <Calendar className="h-3.5 w-3.5" aria-hidden="true" />
          {formatDate(classroom.created_at)}
        </span>
      </div>

      {/* Error message if failed */}
      {classroom.status === 'FAILED' && classroom.error_message && (
        <p className="mt-2 text-xs text-red-500 line-clamp-1">
          {classroom.error_message}
        </p>
      )}
    </button>
  );
});
