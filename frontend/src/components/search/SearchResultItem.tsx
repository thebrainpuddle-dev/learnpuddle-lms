// src/components/search/SearchResultItem.tsx
// Single result row: title + source_type badge + score percentage + snippet.

import React from 'react';
import {
  DocumentTextIcon,
  BookOpenIcon,
  VideoCameraIcon,
  FolderOpenIcon,
} from '@heroicons/react/24/outline';
import type { SearchResult, SearchSourceType } from '../../services/searchService';

interface SearchResultItemProps {
  result: SearchResult;
  onClick: (result: SearchResult) => void;
  isFocused?: boolean;
  id?: string;
}

const SOURCE_TYPE_LABELS: Record<SearchSourceType, string> = {
  content: 'Content',
  transcript: 'Transcript',
  module: 'Module',
  course: 'Course',
};

const SOURCE_TYPE_COLORS: Record<SearchSourceType, string> = {
  content: 'bg-blue-100 text-blue-700',
  transcript: 'bg-purple-100 text-purple-700',
  module: 'bg-amber-100 text-amber-700',
  course: 'bg-emerald-100 text-emerald-700',
};

function SourceTypeIcon({ type }: { type: SearchSourceType }) {
  const cls = 'h-3.5 w-3.5 inline-block mr-1';
  if (type === 'transcript') {
    return <VideoCameraIcon className={cls} />;
  }
  if (type === 'module') {
    return <FolderOpenIcon className={cls} />;
  }
  if (type === 'course') {
    return <BookOpenIcon className={cls} />;
  }
  return <DocumentTextIcon className={cls} />;
}

/** Format 0..1 score as an integer percentage string, e.g. 0.812 → "81%". Guards against NaN/Infinity. */
export function formatScore(score: number): string {
  return `${Math.round(Number.isFinite(score) ? score * 100 : 0)}%`;
}

export const SearchResultItem: React.FC<SearchResultItemProps> = ({
  result,
  onClick,
  isFocused = false,
  id,
}) => {
  const label = SOURCE_TYPE_LABELS[result.source_type] ?? result.source_type;
  const badgeColor =
    SOURCE_TYPE_COLORS[result.source_type] ?? 'bg-gray-100 text-gray-600';

  const title =
    result.context.course_title ??
    (result.source_type === 'course' ? 'Course' : result.source_id);

  // Display the snippet or fall back to source type label
  const snippet = result.snippet
    ? result.snippet.slice(0, 120)
    : null;

  return (
    <button
      id={id}
      type="button"
      role="option"
      aria-selected={isFocused}
      onClick={() => onClick(result)}
      className={`w-full text-left px-4 py-3 flex flex-col gap-1 cursor-pointer transition-colors focus:outline-none ${
        isFocused
          ? 'bg-primary-50 ring-2 ring-inset ring-primary-300'
          : 'hover:bg-slate-50'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-slate-900 truncate">
          {title}
        </span>
        <span
          className={`inline-flex items-center flex-shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium ${badgeColor}`}
        >
          <SourceTypeIcon type={result.source_type} />
          {label}
        </span>
      </div>

      {snippet && (
        <p className="text-xs text-slate-500 line-clamp-2">{snippet}</p>
      )}

      <span className="text-[11px] font-semibold text-slate-400">
        {formatScore(result.score)} match
      </span>
    </button>
  );
};

export default SearchResultItem;
