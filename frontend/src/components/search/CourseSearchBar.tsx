// src/components/search/CourseSearchBar.tsx
// Teacher-side inline search box with dropdown results for a specific course.

import React, {
  useState,
  useRef,
  useCallback,
  useEffect,
  useId,
} from 'react';
import { useNavigate } from 'react-router-dom';
import {
  MagnifyingGlassIcon,
  XMarkIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { searchService } from '../../services/searchService';
import type { SearchResult } from '../../services/searchService';
import { SearchResultList } from './SearchResultList';

const MAX_QUERY_LENGTH = 200;
const DEBOUNCE_MS = 300;
const TOP_K = 5;

interface CourseSearchBarProps {
  courseId: string;
  /** Optional placeholder text */
  placeholder?: string;
  className?: string;
}

type Status = 'idle' | 'loading' | 'success' | 'error';

function buildNavigationPath(result: SearchResult): string {
  const ctx = result.context;
  const courseId = ctx.course_id;
  const contentId = ctx.content_id;
  const moduleId = ctx.module_id;

  if ((result.source_type === 'content' || result.source_type === 'transcript') && courseId && contentId) {
    return `/teacher/courses/${courseId}/contents/${contentId}`;
  }
  if (result.source_type === 'module' && courseId && moduleId) {
    return `/teacher/courses/${courseId}?module=${moduleId}`;
  }
  if (result.source_type === 'course' && courseId) {
    return `/teacher/courses/${courseId}`;
  }
  // Fallback: go to course
  if (courseId) {
    return `/teacher/courses/${courseId}`;
  }
  return '/teacher/courses';
}

export const CourseSearchBar: React.FC<CourseSearchBarProps> = ({
  courseId,
  placeholder = 'Search this course…',
  className = '',
}) => {
  const navigate = useNavigate();
  const uid = useId();
  const listId = `${uid}-listbox`;
  const inputId = `${uid}-input`;
  const itemIdPrefix = `${uid}-item`;

  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [status, setStatus] = useState<Status>('idle');
  const [errorMessage, setErrorMessage] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState(-1);
  const [hasSearched, setHasSearched] = useState(false);
  const [retryDisabled, setRetryDisabled] = useState<boolean>(false);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const overLimit = query.length > MAX_QUERY_LENGTH;

  const runSearch = useCallback(
    async (q: string) => {
      if (!q.trim()) {
        setResults([]);
        setStatus('idle');
        setIsOpen(false);
        setHasSearched(false);
        return;
      }
      setStatus('loading');
      setHasSearched(true);
      try {
        const response = await searchService.search(q, {
          courseId,
          topK: TOP_K,
        });
        setResults(response.results);
        setStatus('success');
        setIsOpen(true);
        setFocusedIndex(-1);
      } catch (err: any) {
        const httpStatus = err?.response?.status;
        if (httpStatus === 503 || httpStatus === 500) {
          setStatus('error');
          setErrorMessage('Search service is temporarily unavailable.');
        } else {
          setStatus('error');
          setErrorMessage('Search failed. Please try again.');
        }
        setResults([]);
        setIsOpen(true);
      }
    },
    [courseId],
  );

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
    setIsOpen(false);
    setHasSearched(false);
    setFocusedIndex(-1);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    inputRef.current?.focus();
  };

  const handleResultClick = (result: SearchResult) => {
    const path = buildNavigationPath(result);
    setIsOpen(false);
    setQuery('');
    navigate(path);
  };

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen) return;

    if (e.key === 'Escape') {
      e.preventDefault();
      setIsOpen(false);
      setFocusedIndex(-1);
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setFocusedIndex((prev) =>
        prev < results.length - 1 ? prev + 1 : 0,
      );
      return;
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setFocusedIndex((prev) =>
        prev > 0 ? prev - 1 : results.length - 1,
      );
      return;
    }

    if (e.key === 'Enter' && focusedIndex >= 0 && results[focusedIndex]) {
      e.preventDefault();
      handleResultClick(results[focusedIndex]);
    }
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
        setFocusedIndex(-1);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  // Clean up debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const activeDescendant =
    focusedIndex >= 0 ? `${itemIdPrefix}-${focusedIndex}` : undefined;

  const showEmpty =
    status === 'success' && results.length === 0 && hasSearched;
  const showResults = status === 'success' && results.length > 0;
  const showDropdown = isOpen && query.trim() !== '';

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {/* Input row */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center">
            <MagnifyingGlassIcon
              className={`h-4 w-4 ${
                status === 'loading' ? 'animate-pulse text-primary-500' : 'text-slate-400'
              }`}
            />
          </span>
          <input
            ref={inputRef}
            id={inputId}
            type="search"
            role="combobox"
            aria-expanded={showDropdown}
            aria-controls={showDropdown ? listId : undefined}
            aria-activedescendant={activeDescendant}
            aria-label="Search this course"
            autoComplete="off"
            value={query}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onFocus={() => {
              if (results.length > 0 || status === 'error') {
                setIsOpen(true);
              }
            }}
            placeholder={placeholder}
            maxLength={MAX_QUERY_LENGTH + 1}
            className={`w-full rounded-lg border py-2 pl-9 pr-8 text-sm shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 ${
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
              className="absolute inset-y-0 right-2 flex items-center text-slate-400 hover:text-slate-600 cursor-pointer"
            >
              <XMarkIcon className="h-4 w-4" />
            </button>
          )}
        </div>

        {/* Character counter — only when approaching limit */}
        {query.length > MAX_QUERY_LENGTH * 0.7 && (
          <span
            className={`flex-shrink-0 text-xs font-medium tabular-nums ${
              overLimit ? 'text-red-500' : 'text-slate-400'
            }`}
            aria-live="polite"
          >
            {query.length}/{MAX_QUERY_LENGTH}
          </span>
        )}
      </div>

      {/* Dropdown panel */}
      {showDropdown && (
        <div
          role="presentation"
          className="absolute left-0 right-0 top-full z-50 mt-1 rounded-xl border border-slate-200 bg-white shadow-lg overflow-hidden"
        >
          {/* Loading skeleton */}
          {status === 'loading' && (
            <div className="space-y-0" aria-label="Loading search results">
              {Array.from({ length: 3 }).map((_, i) => (
                <div
                  key={i}
                  className="flex flex-col gap-2 px-4 py-3 border-b border-slate-100 last:border-0"
                >
                  <div className="h-3 w-3/4 animate-pulse rounded bg-slate-200" />
                  <div className="h-2.5 w-full animate-pulse rounded bg-slate-100" />
                  <div className="h-2 w-1/4 animate-pulse rounded bg-slate-100" />
                </div>
              ))}
            </div>
          )}

          {/* Error banner */}
          {status === 'error' && (
            <div className="flex items-center gap-3 px-4 py-3 bg-red-50 border-b border-red-100">
              <ExclamationTriangleIcon className="h-4 w-4 flex-shrink-0 text-red-500" />
              <p className="flex-1 text-sm text-red-700">{errorMessage}</p>
              <button
                type="button"
                data-testid="search-retry-btn"
                onClick={handleRetry}
                disabled={retryDisabled}
                className="flex-shrink-0 rounded-md bg-red-100 px-3 py-1 text-xs font-semibold text-red-700 hover:bg-red-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Retry
              </button>
            </div>
          )}

          {/* Empty state */}
          {showEmpty && (
            <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
              <MagnifyingGlassIcon className="h-8 w-8 text-slate-300 mb-2" />
              <p className="text-sm font-medium text-slate-500">No results found</p>
              <p className="mt-1 text-xs text-slate-400">
                Try different keywords or broaden your search.
              </p>
            </div>
          )}

          {/* Results */}
          {showResults && (
            <SearchResultList
              listId={listId}
              results={results}
              onResultClick={handleResultClick}
              focusedIndex={focusedIndex}
              itemIdPrefix={itemIdPrefix}
            />
          )}
        </div>
      )}
    </div>
  );
};

export default CourseSearchBar;
