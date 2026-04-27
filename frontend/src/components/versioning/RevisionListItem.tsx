// src/components/versioning/RevisionListItem.tsx
//
// Compact row for a single revision in the history panel list.
// Shows revision number, who made it, summary, timestamp, and action buttons.

import React from 'react';
import {
  ClockIcon,
  UserCircleIcon,
  EyeIcon,
  ArrowUturnLeftIcon,
} from '@heroicons/react/24/outline';
import type { ContentRevisionListItem } from '../../services/versioningService';

interface RevisionListItemProps {
  revision: ContentRevisionListItem;
  isSelected: boolean;
  onSelect: (revision: ContentRevisionListItem) => void;
  onRestoreClick: (revision: ContentRevisionListItem) => void;
}

function formatDate(isoString: string): string {
  try {
    return new Intl.DateTimeFormat('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    }).format(new Date(isoString));
  } catch {
    return isoString;
  }
}

function formatSummary(summary: string): string {
  if (!summary) return 'Updated';
  if (summary === 'create') return 'Created';
  if (summary === 'update') return 'Updated';
  const restoreMatch = summary.match(/^restore-from-v(\d+)$/);
  if (restoreMatch) {
    return `Restored from v${restoreMatch[1]}`;
  }
  return summary.charAt(0).toUpperCase() + summary.slice(1);
}

export const RevisionListItem: React.FC<RevisionListItemProps> = ({
  revision,
  isSelected,
  onSelect,
  onRestoreClick,
}) => {
  const isRestoreRevision = revision.change_summary?.startsWith('restore-from-v');

  return (
    <div
      className={`group flex items-start gap-3 p-3 rounded-lg cursor-pointer transition-colors border ${
        isSelected
          ? 'bg-blue-50 border-blue-200'
          : 'bg-white border-transparent hover:bg-gray-50 hover:border-gray-200'
      }`}
      onClick={() => onSelect(revision)}
      role="button"
      tabIndex={0}
      aria-pressed={isSelected}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(revision);
        }
      }}
    >
      {/* Version badge */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${
          isRestoreRevision
            ? 'bg-amber-100 text-amber-700'
            : 'bg-blue-100 text-blue-700'
        }`}
      >
        v{revision.revision_number}
      </div>

      {/* Details */}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 truncate">
          {formatSummary(revision.change_summary)}
        </p>

        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-gray-500">
          {revision.changed_by_name && (
            <span className="flex items-center gap-1">
              <UserCircleIcon className="h-3.5 w-3.5" />
              {revision.changed_by_name}
            </span>
          )}
          <span className="flex items-center gap-1">
            <ClockIcon className="h-3.5 w-3.5" />
            {formatDate(revision.created_at)}
          </span>
        </div>
      </div>

      {/* Action buttons — visible on hover or when selected */}
      <div
        className={`flex-shrink-0 flex items-center gap-1 transition-opacity ${
          isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          type="button"
          title="View snapshot"
          onClick={() => onSelect(revision)}
          className="p-1.5 rounded-md text-gray-400 hover:text-blue-600 hover:bg-blue-50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
          aria-label={`View revision ${revision.revision_number}`}
        >
          <EyeIcon className="h-4 w-4" />
        </button>
        <button
          type="button"
          title="Restore this revision"
          onClick={() => onRestoreClick(revision)}
          className="p-1.5 rounded-md text-gray-400 hover:text-amber-600 hover:bg-amber-50 transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-400"
          aria-label={`Restore revision ${revision.revision_number}`}
        >
          <ArrowUturnLeftIcon className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};
