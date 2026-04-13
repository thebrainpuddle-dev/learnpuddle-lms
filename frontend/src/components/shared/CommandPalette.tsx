import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  MagnifyingGlassIcon,
  XMarkIcon,
  AcademicCapIcon,
  UserGroupIcon,
  UsersIcon,
  Squares2X2Icon,
  ChartBarIcon,
  BellIcon,
  CreditCardIcon,
  Cog6ToothIcon,
  ShieldCheckIcon,
  DocumentTextIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline';
import { LayoutDashboard } from 'lucide-react';
import api from '../../config/api';

// ─── Types ──────────────────────────────────────────────────────────────────

interface SearchResult {
  id: string;
  title: string;
  subtitle?: string;
  category: 'page' | 'course' | 'teacher' | 'group';
  icon: React.ElementType;
  href: string;
}

interface SearchResponse {
  query: string;
  courses: Array<{
    id: string;
    title: string;
    description?: string;
    is_published?: boolean;
  }>;
  content: Array<{
    id: string;
    title: string;
    course_id?: string;
    course_title?: string;
    module_title?: string;
    content_type?: string;
  }>;
}

// ─── Debounce hook ──────────────────────────────────────────────────────────

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

// ─── Page entries ───────────────────────────────────────────────────────────

const ADMIN_PAGES: SearchResult[] = [
  { id: 'page-dashboard', title: 'Dashboard', subtitle: 'Overview & stats', category: 'page', icon: LayoutDashboard as unknown as React.ElementType, href: '/admin/dashboard' },
  { id: 'page-courses', title: 'Courses', subtitle: 'Manage courses', category: 'page', icon: AcademicCapIcon, href: '/admin/courses' },
  { id: 'page-teachers', title: 'Teachers', subtitle: 'Manage teachers', category: 'page', icon: UsersIcon, href: '/admin/teachers' },
  { id: 'page-groups', title: 'Groups', subtitle: 'Manage groups', category: 'page', icon: UserGroupIcon, href: '/admin/groups' },
  { id: 'page-certifications', title: 'Certifications', subtitle: 'Certificates & approvals', category: 'page', icon: ShieldCheckIcon, href: '/admin/certifications' },
  { id: 'page-analytics', title: 'Analytics', subtitle: 'Reports & insights', category: 'page', icon: ChartBarIcon, href: '/admin/analytics' },
  { id: 'page-reminders', title: 'Reminders', subtitle: 'Automated & manual reminders', category: 'page', icon: BellIcon, href: '/admin/reminders' },
  { id: 'page-billing', title: 'Billing', subtitle: 'Plans & payments', category: 'page', icon: CreditCardIcon, href: '/admin/billing' },
  { id: 'page-settings', title: 'Settings', subtitle: 'School profile & branding', category: 'page', icon: Cog6ToothIcon, href: '/admin/settings' },
];

// ─── Search API ─────────────────────────────────────────────────────────────

async function fetchSearchResults(query: string): Promise<SearchResponse> {
  if (query.length < 2) {
    return { query, courses: [], content: [] };
  }
  const response = await api.get('/courses/search/', { params: { q: query } });
  return response.data;
}

// ─── Category config ────────────────────────────────────────────────────────

const CATEGORY_META: Record<string, { label: string; order: number }> = {
  page: { label: 'Pages', order: 0 },
  course: { label: 'Courses', order: 1 },
  teacher: { label: 'Teachers', order: 2 },
  group: { label: 'Groups', order: 3 },
};

// ─── Component ──────────────────────────────────────────────────────────────

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ isOpen, onClose }) => {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);

  const debouncedQuery = useDebounce(query, 300);

  // Fetch course/content search results
  const { data: apiResults, isLoading } = useQuery({
    queryKey: ['commandPaletteSearch', debouncedQuery],
    queryFn: () => fetchSearchResults(debouncedQuery),
    enabled: isOpen && debouncedQuery.length >= 2,
  });

  // Build combined results
  const allResults = useMemo(() => {
    const results: SearchResult[] = [];

    // Filter pages by query
    const q = query.toLowerCase().trim();
    const matchingPages = q
      ? ADMIN_PAGES.filter(
          (p) =>
            p.title.toLowerCase().includes(q) ||
            (p.subtitle && p.subtitle.toLowerCase().includes(q))
        )
      : ADMIN_PAGES;
    results.push(...matchingPages);

    // Add courses from API
    if (apiResults?.courses) {
      for (const course of apiResults.courses) {
        results.push({
          id: `course-${course.id}`,
          title: course.title,
          subtitle: course.description?.slice(0, 60) || undefined,
          category: 'course',
          icon: AcademicCapIcon,
          href: `/admin/courses/${course.id}/edit`,
        });
      }
    }

    // Add content from API mapped as courses
    if (apiResults?.content) {
      for (const item of apiResults.content) {
        results.push({
          id: `content-${item.id}`,
          title: item.title,
          subtitle: item.course_title
            ? `${item.course_title} / ${item.module_title || ''}`
            : undefined,
          category: 'course',
          icon: DocumentTextIcon,
          href: item.course_id ? `/admin/courses/${item.course_id}/edit` : '/admin/courses',
        });
      }
    }

    // TODO: Add teacher search results from API
    // TODO: Add group search results from API

    return results;
  }, [query, apiResults]);

  // Group by category
  const grouped = useMemo(() => {
    const groups = new Map<string, SearchResult[]>();
    for (const result of allResults) {
      const existing = groups.get(result.category) ?? [];
      existing.push(result);
      groups.set(result.category, existing);
    }
    return Array.from(groups.entries())
      .sort(([a], [b]) => (CATEGORY_META[a]?.order ?? 99) - (CATEGORY_META[b]?.order ?? 99));
  }, [allResults]);

  // Flat list for keyboard navigation
  const flatResults = useMemo(() => grouped.flatMap(([, items]) => items), [grouped]);

  // Focus input on open
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      // Small delay to ensure the modal is rendered
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [isOpen]);

  // Clamp selected index
  useEffect(() => {
    if (selectedIndex >= flatResults.length) {
      setSelectedIndex(Math.max(0, flatResults.length - 1));
    }
  }, [flatResults.length, selectedIndex]);

  // Scroll selected into view
  useEffect(() => {
    if (!listRef.current) return;
    const selectedEl = listRef.current.querySelector(`[data-index="${selectedIndex}"]`);
    selectedEl?.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex]);

  const handleSelect = useCallback(
    (result: SearchResult) => {
      onClose();
      navigate(result.href);
    },
    [navigate, onClose]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setSelectedIndex((prev) => Math.min(prev + 1, flatResults.length - 1));
          break;
        case 'ArrowUp':
          e.preventDefault();
          setSelectedIndex((prev) => Math.max(prev - 1, 0));
          break;
        case 'Enter':
          e.preventDefault();
          if (flatResults[selectedIndex]) {
            handleSelect(flatResults[selectedIndex]);
          }
          break;
        case 'Escape':
          e.preventDefault();
          onClose();
          break;
      }
    },
    [flatResults, selectedIndex, handleSelect, onClose]
  );

  if (!isOpen) return null;

  let flatIndex = -1;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
        aria-hidden
      />

      {/* Palette */}
      <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] px-4 pointer-events-none">
        <div
          className="w-full max-w-lg bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden pointer-events-auto"
          role="dialog"
          aria-label="Command palette"
        >
          {/* Search input */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100">
            <MagnifyingGlassIcon className="h-5 w-5 text-gray-400 flex-shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelectedIndex(0);
              }}
              onKeyDown={handleKeyDown}
              placeholder="Search pages, courses, teachers..."
              className="flex-1 text-sm text-gray-900 placeholder-gray-400 outline-none bg-transparent"
              autoComplete="off"
              spellCheck={false}
            />
            {query && (
              <button
                onClick={() => {
                  setQuery('');
                  setSelectedIndex(0);
                  inputRef.current?.focus();
                }}
                className="p-0.5 text-gray-400 hover:text-gray-600"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            )}
            <kbd className="hidden sm:inline-flex h-5 items-center gap-0.5 rounded border border-gray-200 bg-gray-50 px-1.5 text-[10px] font-medium text-gray-400">
              ESC
            </kbd>
          </div>

          {/* Results */}
          <div ref={listRef} className="max-h-80 overflow-y-auto py-1">
            {isLoading && debouncedQuery.length >= 2 ? (
              <div className="px-4 py-8 text-center text-gray-500">
                <div className="animate-spin h-5 w-5 border-2 border-primary-600 border-t-transparent rounded-full mx-auto mb-2" />
                <span className="text-sm">Searching...</span>
              </div>
            ) : flatResults.length === 0 ? (
              <div className="px-4 py-8 text-center text-gray-500">
                <MagnifyingGlassIcon className="h-6 w-6 mx-auto mb-2 text-gray-300" />
                <p className="text-sm font-medium">No results found</p>
                <p className="text-xs mt-1">Try a different search term.</p>
              </div>
            ) : (
              grouped.map(([category, items]) => (
                <div key={category}>
                  <div className="px-4 py-1.5 text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                    {CATEGORY_META[category]?.label ?? category}
                  </div>
                  {items.map((result) => {
                    flatIndex++;
                    const isSelected = flatIndex === selectedIndex;
                    const Icon = result.icon;
                    const idx = flatIndex;
                    return (
                      <button
                        key={result.id}
                        data-index={idx}
                        onClick={() => handleSelect(result)}
                        onMouseEnter={() => setSelectedIndex(idx)}
                        className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                          isSelected ? 'bg-primary-50' : 'hover:bg-gray-50'
                        }`}
                      >
                        <div
                          className={`flex-shrink-0 p-1.5 rounded-lg ${
                            isSelected ? 'bg-primary-100' : 'bg-gray-100'
                          }`}
                        >
                          <Icon
                            className={`h-4 w-4 ${
                              isSelected ? 'text-primary-600' : 'text-gray-500'
                            }`}
                          />
                        </div>
                        <div className="flex-1 min-w-0">
                          <span
                            className={`text-sm font-medium truncate block ${
                              isSelected ? 'text-primary-900' : 'text-gray-900'
                            }`}
                          >
                            {result.title}
                          </span>
                          {result.subtitle && (
                            <span className="text-xs text-gray-400 truncate block">
                              {result.subtitle}
                            </span>
                          )}
                        </div>
                        {isSelected && (
                          <ArrowRightIcon className="h-3.5 w-3.5 text-primary-400 flex-shrink-0" />
                        )}
                      </button>
                    );
                  })}
                </div>
              ))
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center gap-4 px-4 py-2 border-t border-gray-100 bg-gray-50/50 text-[10px] text-gray-400">
            <span>
              <kbd className="inline-flex items-center justify-center h-4 w-4 rounded border border-gray-200 bg-white text-[9px]">
                &uarr;
              </kbd>{' '}
              <kbd className="inline-flex items-center justify-center h-4 w-4 rounded border border-gray-200 bg-white text-[9px]">
                &darr;
              </kbd>{' '}
              to navigate
            </span>
            <span>
              <kbd className="inline-flex items-center justify-center h-4 min-w-[28px] rounded border border-gray-200 bg-white text-[9px] px-1">
                Enter
              </kbd>{' '}
              to select
            </span>
            <span>
              <kbd className="inline-flex items-center justify-center h-4 min-w-[20px] rounded border border-gray-200 bg-white text-[9px] px-1">
                Esc
              </kbd>{' '}
              to close
            </span>
          </div>
        </div>
      </div>
    </>
  );
};
