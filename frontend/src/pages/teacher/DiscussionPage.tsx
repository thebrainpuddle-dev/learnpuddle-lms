// src/pages/teacher/DiscussionPage.tsx
//
// Teacher discussions page — monitor student discussions across assigned sections.
// Filters: section, course, status, student search.

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { cn } from '../../design-system/theme/cn';
import { usePageTitle } from '../../hooks/usePageTitle';
import api from '../../config/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Author {
  id: string | null;
  name: string;
  role: string | null;
  avatar: string | null;
}

interface DiscussionThread {
  id: string;
  title: string;
  body: string;
  author: Author;
  section_id: string;
  section_name: string | null;
  grade_name: string | null;
  course_id: string | null;
  course_title: string | null;
  content_id: string | null;
  content_title: string | null;
  status: 'open' | 'closed' | 'archived';
  is_pinned: boolean;
  is_announcement: boolean;
  reply_count: number;
  view_count: number;
  created_at: string;
  last_reply_at: string | null;
}

interface ThreadsResponse {
  results: DiscussionThread[];
  count: number;
  next: string | null;
}

interface SectionOption {
  id: string;
  name: string;
  grade_name: string | null;
  display_name: string;
}

type StatusFilter = 'all' | 'open' | 'closed' | 'archived';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return months < 12 ? `${months}mo ago` : `${Math.floor(months / 12)}y ago`;
}

function truncate(text: string, max: number): string {
  return text.length <= max ? text : text.slice(0, max).trimEnd() + '\u2026';
}

// ---------------------------------------------------------------------------
// SVG Icons
// ---------------------------------------------------------------------------

const ChatBubbleIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
    <path fillRule="evenodd" d="M3.43 2.524A41.29 41.29 0 0110 2c2.236 0 4.43.18 6.57.524 1.437.231 2.43 1.49 2.43 2.902v5.148c0 1.413-.993 2.67-2.43 2.902a41.102 41.102 0 01-3.55.414c-.28.02-.521.18-.643.413l-1.712 3.293a.75.75 0 01-1.33 0l-1.713-3.293a.783.783 0 00-.642-.413 41.108 41.108 0 01-3.55-.414C1.993 13.245 1 11.986 1 10.574V5.426c0-1.413.993-2.67 2.43-2.902z" clipRule="evenodd" />
  </svg>
);

const EyeIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
    <path d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" />
    <path fillRule="evenodd" d="M.664 10.59a1.651 1.651 0 010-1.186A10.004 10.004 0 0110 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0110 17c-4.257 0-7.893-2.66-9.336-6.41zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
  </svg>
);

const PinIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
    <path d="M8.5 3.528v4.644c0 .729-.29 1.428-.805 1.944l-1.217 1.216a8.75 8.75 0 013.55.621l.502.201a7.25 7.25 0 004.178.365l-2.403-2.403a2.75 2.75 0 01-.805-1.944V3.528a40.205 40.205 0 00-3 0zm4.5.084a.75.75 0 00.75-.75 2.25 2.25 0 00-2.25-2.25h-3A2.25 2.25 0 006.25 2.862a.75.75 0 00.75.75h6zM9.206 17.708l-4.066-4.066a10.251 10.251 0 014.066 4.066z" />
  </svg>
);

const EmptyIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-12 w-12">
    <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
  </svg>
);

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const DiscussionPage: React.FC = () => {
  usePageTitle('Student Discussions');
  const navigate = useNavigate();

  // Filters
  const [sectionFilter, setSectionFilter] = useState<string>('all');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [page, setPage] = useState(1);

  // Fetch teacher's sections for filter dropdown
  const { data: sections = [] } = useQuery<SectionOption[]>({
    queryKey: ['teacher-sections'],
    queryFn: async () => {
      const res = await api.get('/v1/teacher/discussions/sections/');
      return res.data;
    },
  });

  // Fetch threads
  const { data, isLoading, isFetching } = useQuery<ThreadsResponse>({
    queryKey: ['teacher-discussions', sectionFilter, statusFilter, page],
    queryFn: async () => {
      const params: Record<string, string> = { page: String(page) };
      if (sectionFilter !== 'all') params.section_id = sectionFilter;
      if (statusFilter !== 'all') params.status = statusFilter;
      const res = await api.get('/v1/teacher/discussions/threads/', { params });
      return res.data;
    },
  });

  const threads = data?.results ?? [];
  const totalCount = data?.count ?? 0;
  const hasMore = !!data?.next;

  const handleFilterChange = (setter: (v: string) => void, val: string) => {
    setter(val);
    setPage(1);
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-[22px] font-bold text-tp-text tracking-tight">
          Student Discussions
        </h1>
        <p className="mt-0.5 text-[13px] text-gray-400">
          Monitor and participate in student discussions across your sections
        </p>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Section filter */}
        <select
          value={sectionFilter}
          onChange={(e) => handleFilterChange(setSectionFilter, e.target.value)}
          className="rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-[12px] font-medium text-gray-600 focus:outline-none focus:ring-2 focus:ring-tp-accent/20 focus:border-tp-accent"
        >
          <option value="all">All Sections</option>
          {sections.map((s) => (
            <option key={s.id} value={s.id}>{s.display_name}</option>
          ))}
        </select>

        {/* Status filter */}
        <div className="flex items-center gap-0.5 rounded-xl bg-gray-50 border border-gray-100 p-0.5">
          {(['all', 'open', 'closed', 'archived'] as StatusFilter[]).map((s) => (
            <button
              key={s}
              onClick={() => handleFilterChange(v => setStatusFilter(v as StatusFilter), s)}
              className={cn(
                'px-3 py-1.5 rounded-lg text-[12px] font-medium capitalize transition-colors',
                statusFilter === s
                  ? 'bg-white text-tp-text shadow-sm'
                  : 'text-gray-400 hover:text-gray-600',
              )}
            >
              {s}
            </button>
          ))}
        </div>

        <span className="text-[12px] text-gray-400 ml-auto">
          {totalCount} {totalCount === 1 ? 'thread' : 'threads'}
        </span>
      </div>

      {/* Thread List */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 tp-skeleton rounded-2xl" />
          ))}
        </div>
      ) : threads.length === 0 ? (
        <div className="text-center py-20">
          <div className="mx-auto text-gray-200 mb-4 flex justify-center">
            <EmptyIcon />
          </div>
          <h3 className="text-[15px] font-semibold text-tp-text mb-1">
            No discussions yet
          </h3>
          <p className="text-[13px] text-gray-400">
            Student discussions will appear here once students start threads.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {threads.map((thread) => (
            <button
              key={thread.id}
              onClick={() => navigate(`/teacher/discussions/${thread.id}`)}
              className="w-full text-left bg-white rounded-2xl border border-gray-100 p-4 hover:shadow-md transition-all shadow-sm group"
            >
              <div className="flex items-start gap-3">
                <div className="min-w-0 flex-1">
                  {/* Section & course labels */}
                  <div className="flex flex-wrap items-center gap-1.5 mb-1.5">
                    {thread.grade_name && thread.section_name && (
                      <span className="px-2 py-[2px] rounded-md text-[10px] font-semibold bg-blue-50 text-blue-600 uppercase tracking-wide">
                        {thread.grade_name} - {thread.section_name}
                      </span>
                    )}
                    {thread.course_title && (
                      <span className="px-2 py-[2px] rounded-md text-[10px] font-semibold bg-purple-50 text-purple-600 tracking-wide truncate max-w-[200px]">
                        {thread.course_title}
                      </span>
                    )}
                    {thread.content_title && (
                      <span className="px-2 py-[2px] rounded-md text-[10px] font-medium bg-gray-50 text-gray-500 tracking-wide truncate max-w-[200px]">
                        {thread.content_title}
                      </span>
                    )}
                  </div>

                  {/* Title */}
                  <div className="flex items-center gap-2 mb-1">
                    {thread.is_pinned && (
                      <span className="text-tp-accent flex-shrink-0" title="Pinned">
                        <PinIcon />
                      </span>
                    )}
                    <h3 className="text-[14px] font-semibold text-tp-text truncate group-hover:text-tp-accent transition-colors">
                      {thread.title}
                    </h3>
                  </div>

                  {/* Body preview */}
                  <p className="text-[12px] text-gray-400 leading-relaxed mb-2.5">
                    {truncate(thread.body, 120)}
                  </p>

                  {/* Meta row */}
                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-gray-400">
                    <span className="font-medium text-gray-500">
                      {thread.author.name}
                    </span>
                    {thread.author.role && (
                      <span className={cn(
                        'px-1.5 py-[1px] rounded text-[9px] font-semibold uppercase',
                        thread.author.role === 'STUDENT'
                          ? 'bg-green-50 text-green-600'
                          : 'bg-orange-50 text-orange-600'
                      )}>
                        {thread.author.role === 'STUDENT' ? 'Student' : 'Teacher'}
                      </span>
                    )}
                    <span>{relativeTime(thread.created_at)}</span>
                    <span className="inline-flex items-center gap-1">
                      <ChatBubbleIcon /> {thread.reply_count}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <EyeIcon /> {thread.view_count}
                    </span>
                  </div>
                </div>

                {/* Status badge */}
                <span
                  className={cn(
                    'flex-shrink-0 px-2 py-[3px] rounded-md text-[10px] font-semibold uppercase tracking-wide leading-none',
                    thread.status === 'open'
                      ? 'bg-emerald-50 text-emerald-600'
                      : thread.status === 'closed'
                        ? 'bg-gray-100 text-gray-500'
                        : 'bg-amber-50 text-amber-600',
                  )}
                >
                  {thread.status}
                </span>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Load More */}
      {hasMore && (
        <div className="flex justify-center pt-2">
          <button
            onClick={() => setPage((p) => p + 1)}
            disabled={isFetching}
            className={cn(
              'px-5 py-2 rounded-xl text-[13px] font-medium border transition-colors',
              isFetching
                ? 'border-gray-100 text-gray-300 cursor-not-allowed'
                : 'border-gray-200 text-gray-600 hover:bg-gray-50 hover:text-tp-text',
            )}
          >
            {isFetching ? 'Loading\u2026' : 'Load More'}
          </button>
        </div>
      )}
    </div>
  );
};
