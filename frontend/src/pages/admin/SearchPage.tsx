// src/pages/admin/SearchPage.tsx
// Admin-side tenant-wide semantic search page — results grouped by course.

import React, {
  useState,
  useRef,
  useCallback,
  useId,
} from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MagnifyingGlassIcon,
  XMarkIcon,
  ExclamationTriangleIcon,
  BookOpenIcon,
} from '@heroicons/react/24/outline';
import { searchService } from '../../services/searchService';
import type { SearchResult } from '../../services/searchService';
import { SearchResultItem } from '../../components/search/SearchResultItem';
import { usePageTitle } from '../../hooks/usePageTitle';

const MAX_QUERY_LENGTH = 200;
const DEBOUNCE_MS = 300;
const TOP_K = 20;

type Status = 'idle' | 'loading' | 'success' | 'error';

/** Group results by course_id, preserving order of first appearance. */
function groupByCourse(results: SearchResult[]): Array<{
  courseId: string;
  courseTitle: string;
  items: SearchResult[];
}> {
  const map = new Map<string, { courseId: string; courseTitle: string; items: SearchResult[] }>();

  for (const r of results) {
    const courseId = r.context.course_id ?? 'unknown';
    const courseTitle = r.context.course_title ?? 'Unknown Course';
    if (!map.has(courseId)) {
      map.set(courseId, { courseId, courseTitle, items: [] });
    }
    map.get(courseId)!.items.push(r);
  }

  return Array.from(map.values());
}

function buildAdminNavigationPath(result: SearchResult): string {
  const ctx = result.context;
  const courseId = ctx.course_id;

  if (courseId) {
    // All admin-side hits navigate to the course editor.
    // Content/module hits include an anchor so the admin can jump to that item.
    if (
      (result.source_type === 'content' || result.source_type === 'transcript') &&
      ctx.content_id
    ) {
      return `/admin/courses/${courseId}/edit#content-${ctx.content_id}`;
    }
    if (result.source_type === 'module' && ctx.module_id) {
      return `/admin/courses/${courseId}/edit#module-${ctx.module_id}`;
    }
    return `/admin/courses/${courseId}/edit`;
  }
  return '/admin/courses';
}

export const SearchPage: React.FC = () => {
  usePageTitle('Search');
  const navigate = useNavigate();
  const uid = useId();

  const [query, setQuery] = useState('');
  const [committedQuery, setCommittedQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [status, setStatus] = useState<Status>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [retryDisabled, setRetryDisabled] = useState<boolean>(false);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const overLimit = query.length > MAX_QUERY_LENGTH;

  const runSearch = useCallback(async (q: string) => {
    const trimmed = q.trim();
    if (!trimmed) {
      setResults([]);
      setStatus('idle');
      setCommittedQuery('');
      return;
    }
    setStatus('loading');
    setCommittedQuery(trimmed);
    try {
      const response = await searchService.search(trimmed, { topK: TOP_K });
      setResults(response.results);
      setStatus('success');
      setFocusedIndex(-1);
    } catch (err: any) {
      const httpStatus = err?.response?.status;
      if (httpStatus === 503 || httpStatus === 500) {
        setErrorMessage('Search service is temporarily unavailable.');
      } else {
        setErrorMessage('Search failed. Please try again.');
      }
      setResults([]);
      setStatus('error');
    }
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setQuery(value);
    if (value.length > MAX_QUERY_LENGTH) return;

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      runSearch(value);
    }, DEBOUNCE_MS);
  };

  const handleRetry = () => {
    setRetryDisabled(true);
    setTimeout(() => setRetryDisabled(false), 5000);
    runSearch(query);
  };

  const handleClear = () => {
    setQuery('');
    setResults([]);
    setStatus('idle');
    setCommittedQuery('');
    setFocusedIndex(-1);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    inputRef.current?.focus();
  };

  const flatResults = results;

  const handleResultClick = (result: SearchResult) => {
    const path = buildAdminNavigationPath(result);
    navigate(path);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocusedIndex((prev) =>
        prev < flatResults.length - 1 ? prev + 1 : 0,
      );
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocusedIndex((prev) =>
        prev > 0 ? prev - 1 : flatResults.length - 1,
      );
      return;
    }
    if (e.key === 'Enter' && focusedIndex >= 0 && flatResults[focusedIndex]) {
      e.preventDefault();
      handleResultClick(flatResults[focusedIndex]);
    }
  };

  const grouped = groupByCourse(results);
  const showEmpty = status === 'success' && results.length === 0 && committedQuery;

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Search Content</h1>
        <p className="mt-1 text-sm text-slate-500">
          Find course content, modules, and transcripts across your school.
        </p>
      </div>

      {/* Search input */}
      <div className="relative">
        <div className="flex items-center gap-3">
          <div className="relative flex-1">
            <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
              <MagnifyingGlassIcon
                className={`h-5 w-5 ${
                  status === 'loading' ? 'animate-pulse text-primary-500' : 'text-slate-400'
                }`}
              />
            </span>
            <input
              ref={inputRef}
              id={`${uid}-input`}
              type="search"
              role="searchbox"
              aria-label="Search tenant content"
              autoComplete="off"
              value={query}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Search across all courses…"
              maxLength={MAX_QUERY_LENGTH + 1}
              className={`w-full rounded-xl border py-3 pl-10 pr-10 text-base shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 ${
                overLimit
                  ? 'border-red-400 bg-red-50 focus:ring-red-400'
                  : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
            />
            {query && (
              <button
                type="button"
                aria-label="Clear search"
                onClick={handleClear}
                className="absolute inset-y-0 right-3 flex items-center text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            )}
          </div>

          {/* Character counter */}
          {query.length > MAX_QUERY_LENGTH * 0.7 && (
            <span
              className={`flex-shrink-0 text-sm font-medium tabular-nums ${
                overLimit ? 'text-red-500' : 'text-slate-400'
              }`}
              aria-live="polite"
            >
              {query.length}/{MAX_QUERY_LENGTH}
            </span>
          )}
        </div>

        {overLimit && (
          <p className="mt-1 text-xs text-red-500" role="alert">
            Query is too long. Maximum {MAX_QUERY_LENGTH} characters.
          </p>
        )}
      </div>

      {/* Error banner */}
      {status === 'error' && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3"
        >
          <ExclamationTriangleIcon className="h-5 w-5 flex-shrink-0 text-red-500" />
          <p className="flex-1 text-sm text-red-700">{errorMessage}</p>
          <button
            type="button"
            data-testid="search-retry-btn"
            onClick={handleRetry}
            disabled={retryDisabled}
            className="flex-shrink-0 rounded-lg bg-red-100 px-3 py-1.5 text-sm font-semibold text-red-700 hover:bg-red-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading skeleton */}
      {status === 'loading' && (
        <div className="space-y-4" aria-label="Loading search results">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
              <div className="h-4 w-1/3 animate-pulse rounded bg-slate-200" />
              <div className="space-y-2">
                <div className="h-3 w-3/4 animate-pulse rounded bg-slate-100" />
                <div className="h-3 w-full animate-pulse rounded bg-slate-100" />
                <div className="h-3 w-1/4 animate-pulse rounded bg-slate-100" />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {showEmpty && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-slate-200 bg-white py-12 px-4 text-center">
          <MagnifyingGlassIcon className="h-12 w-12 text-slate-300 mb-3" />
          <p className="text-base font-semibold text-slate-600">No results found</p>
          <p className="mt-1 text-sm text-slate-400">
            No content matched &ldquo;{committedQuery}&rdquo;. Try different keywords.
          </p>
        </div>
      )}

      {/* Results grouped by course */}
      {status === 'success' && grouped.length > 0 && (
        <div className="space-y-5" aria-label="Search results">
          {grouped.map((group) => {
            const groupStartIndex = results.indexOf(group.items[0]);
            return (
              <div
                key={group.courseId}
                className="rounded-xl border border-slate-200 bg-white overflow-hidden"
              >
                {/* Course header */}
                <div className="flex items-center gap-2 px-4 py-3 bg-slate-50 border-b border-slate-200">
                  <BookOpenIcon className="h-4 w-4 text-slate-400 flex-shrink-0" />
                  <h2 className="text-sm font-semibold text-slate-700 truncate">
                    {group.courseTitle}
                  </h2>
                  {/* TODO: dept-scoped admin permissions — when non-SCHOOL_ADMIN roles get
                      course-edit access, gate this button on the resolved permission instead
                      of unconditionally navigating to the edit route. */}
                  <button
                    type="button"
                    title="Edit course"
                    data-testid="search-result-open-btn"
                    onClick={() => navigate(`/admin/courses/${group.courseId}/edit`)}
                    className="ml-auto flex-shrink-0 rounded-md px-2 py-1 text-xs text-primary-600 hover:bg-primary-50 cursor-pointer"
                  >
                    Open
                  </button>
                </div>

                {/* Result items */}
                <ul role="list" className="divide-y divide-slate-100">
                  {group.items.map((result, localIdx) => {
                    const globalIdx = groupStartIndex + localIdx;
                    return (
                      <li key={`${result.source_type}-${result.source_id}-${result.chunk_index}`}>
                        <SearchResultItem
                          id={`${uid}-item-${globalIdx}`}
                          result={result}
                          onClick={handleResultClick}
                          isFocused={globalIdx === focusedIndex}
                        />
                      </li>
                    );
                  })}
                </ul>
              </div>
            );
          })}
        </div>
      )}

      {/* Idle state */}
      {status === 'idle' && !query && (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-slate-200 bg-white py-12 px-4 text-center">
          <MagnifyingGlassIcon className="h-10 w-10 text-slate-300 mb-3" />
          <p className="text-sm text-slate-400">
            Type to search across all course content.
          </p>
        </div>
      )}
    </div>
  );
};

export default SearchPage;
