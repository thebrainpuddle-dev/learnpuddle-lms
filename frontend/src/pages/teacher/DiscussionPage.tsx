// src/pages/teacher/DiscussionPage.tsx
//
// Discussion forum listing page — threads for a course.

import React, { useState, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cn } from '../../design-system/theme/cn';
import { usePageTitle } from '../../hooks/usePageTitle';
import api from '../../config/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DiscussionThread {
  id: string;
  title: string;
  body: string;
  author_name: string;
  author_id: string;
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

type StatusFilter = 'all' | 'open' | 'closed';
type SortOption = 'recent' | 'popular';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function relativeTime(dateStr: string): string {
  const now = Date.now();
  const then = new Date(dateStr).getTime();
  const diff = now - then;

  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return 'just now';

  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;

  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;

  return `${Math.floor(months / 12)}y ago`;
}

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max).trimEnd() + '\u2026';
}

// ---------------------------------------------------------------------------
// SVG Icons (inline, no library)
// ---------------------------------------------------------------------------

const PlusIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
    <path d="M10.75 4.75a.75.75 0 00-1.5 0v4.5h-4.5a.75.75 0 000 1.5h4.5v4.5a.75.75 0 001.5 0v-4.5h4.5a.75.75 0 000-1.5h-4.5v-4.5z" />
  </svg>
);

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

const XIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
    <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
  </svg>
);

const EmptyThreadsIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-12 w-12">
    <path strokeLinecap="round" strokeLinejoin="round" d="M20.25 8.511c.884.284 1.5 1.128 1.5 2.097v4.286c0 1.136-.847 2.1-1.98 2.193-.34.027-.68.052-1.02.072v3.091l-3-3c-1.354 0-2.694-.055-4.02-.163a2.115 2.115 0 01-.825-.242m9.345-8.334a2.126 2.126 0 00-.476-.095 48.64 48.64 0 00-8.048 0c-1.131.094-1.976 1.057-1.976 2.192v4.286c0 .837.46 1.58 1.155 1.951m9.345-8.334V6.637c0-1.621-1.152-3.026-2.76-3.235A48.455 48.455 0 0011.25 3c-2.115 0-4.198.137-6.24.402-1.608.209-2.76 1.614-2.76 3.235v6.226c0 1.621 1.152 3.026 2.76 3.235.577.075 1.157.14 1.74.194V21l4.155-4.155" />
  </svg>
);

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export const DiscussionPage: React.FC = () => {
  usePageTitle('Discussions');
  const navigate = useNavigate();
  const { courseId } = useParams<{ courseId: string }>();
  const queryClient = useQueryClient();

  // State
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [sort, setSort] = useState<SortOption>('recent');
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newBody, setNewBody] = useState('');

  // Fetch threads
  const {
    data,
    isLoading,
    isFetching,
  } = useQuery<ThreadsResponse>({
    queryKey: ['discussions', courseId, statusFilter, sort, page],
    queryFn: async () => {
      const params: Record<string, string> = {};
      if (courseId) params.course_id = courseId;
      if (statusFilter !== 'all') params.status = statusFilter;
      params.ordering = sort === 'popular' ? '-reply_count' : '-created_at';
      params.page = String(page);
      const res = await api.get('/v1/discussions/threads/', { params });
      return res.data;
    },
  });

  const threads = data?.results ?? [];
  const totalCount = data?.count ?? 0;
  const hasMore = data?.next !== null && data?.next !== undefined;

  // Create thread mutation
  const createMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, string> = { title: newTitle, body: newBody };
      if (courseId) payload.course_id = courseId;
      return api.post('/v1/discussions/threads/', payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['discussions'] });
      setModalOpen(false);
      setNewTitle('');
      setNewBody('');
    },
  });

  const handleCreate = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      if (!newTitle.trim()) return;
      createMutation.mutate();
    },
    [newTitle, newBody, createMutation],
  );

  const handleFilterChange = (s: StatusFilter) => {
    setStatusFilter(s);
    setPage(1);
  };

  const handleSortChange = (s: SortOption) => {
    setSort(s);
    setPage(1);
  };

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-tp-text tracking-tight">
            Discussions
          </h1>
          <p className="mt-0.5 text-[13px] text-gray-400">
            {totalCount} {totalCount === 1 ? 'thread' : 'threads'}
          </p>
        </div>
        <button
          onClick={() => setModalOpen(true)}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-[13px] font-semibold bg-tp-accent text-white hover:bg-tp-accent-dark transition-colors shadow-sm"
        >
          <PlusIcon />
          New Thread
        </button>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Status filter */}
        <div className="flex items-center gap-0.5 rounded-xl bg-gray-50 border border-gray-100 p-0.5">
          {(['all', 'open', 'closed'] as StatusFilter[]).map((s) => (
            <button
              key={s}
              onClick={() => handleFilterChange(s)}
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

        {/* Sort */}
        <select
          value={sort}
          onChange={(e) => handleSortChange(e.target.value as SortOption)}
          className="rounded-xl border border-gray-200 bg-white px-3 py-1.5 text-[12px] font-medium text-gray-600 focus:outline-none focus:ring-2 focus:ring-tp-accent/20 focus:border-tp-accent"
        >
          <option value="recent">Most Recent</option>
          <option value="popular">Most Popular</option>
        </select>
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
          <div className="mx-auto text-gray-200 mb-4">
            <EmptyThreadsIcon />
          </div>
          <h3 className="text-[15px] font-semibold text-tp-text mb-1">
            No discussions yet
          </h3>
          <p className="text-[13px] text-gray-400">
            Start a conversation by creating the first thread.
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {threads.map((thread) => (
            <button
              key={thread.id}
              onClick={() =>
                navigate(
                  courseId
                    ? `/teacher/courses/${courseId}/discussions/${thread.id}`
                    : `/teacher/discussions/${thread.id}`,
                )
              }
              className="w-full text-left bg-white rounded-2xl border border-gray-100 p-4 hover:shadow-md transition-all shadow-sm group"
            >
              <div className="flex items-start gap-3">
                {/* Main content */}
                <div className="min-w-0 flex-1">
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

                  <p className="text-[12px] text-gray-400 leading-relaxed mb-2.5">
                    {truncate(thread.body, 100)}
                  </p>

                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-gray-400">
                    {/* Author */}
                    <span className="font-medium text-gray-500">
                      {thread.author_name}
                    </span>

                    {/* Time */}
                    <span>{relativeTime(thread.created_at)}</span>

                    {/* Reply count */}
                    <span className="inline-flex items-center gap-1">
                      <ChatBubbleIcon />
                      {thread.reply_count}
                    </span>

                    {/* View count */}
                    <span className="inline-flex items-center gap-1">
                      <EyeIcon />
                      {thread.view_count}
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

      {/* New Thread Modal */}
      {modalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            onClick={() => setModalOpen(false)}
          />
          {/* Panel */}
          <div className="relative bg-white rounded-2xl shadow-xl w-full max-w-lg mx-4 p-6">
            <div className="flex items-center justify-between mb-5">
              <h2 className="text-[17px] font-bold text-tp-text">
                New Discussion Thread
              </h2>
              <button
                onClick={() => setModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <XIcon />
              </button>
            </div>

            <form onSubmit={handleCreate} className="space-y-4">
              <div>
                <label
                  htmlFor="thread-title"
                  className="block text-[12px] font-semibold text-gray-600 mb-1.5"
                >
                  Title
                </label>
                <input
                  id="thread-title"
                  type="text"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  placeholder="What would you like to discuss?"
                  className="w-full rounded-xl border border-gray-200 px-3.5 py-2.5 text-[13px] text-tp-text placeholder:text-gray-300 focus:outline-none focus:ring-2 focus:ring-tp-accent/20 focus:border-tp-accent transition-colors"
                  autoFocus
                  required
                />
              </div>

              <div>
                <label
                  htmlFor="thread-body"
                  className="block text-[12px] font-semibold text-gray-600 mb-1.5"
                >
                  Details
                </label>
                <textarea
                  id="thread-body"
                  value={newBody}
                  onChange={(e) => setNewBody(e.target.value)}
                  placeholder="Provide more context or details..."
                  rows={5}
                  className="w-full rounded-xl border border-gray-200 px-3.5 py-2.5 text-[13px] text-tp-text placeholder:text-gray-300 focus:outline-none focus:ring-2 focus:ring-tp-accent/20 focus:border-tp-accent transition-colors resize-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-[13px] font-medium text-gray-500 hover:text-gray-700 hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending || !newTitle.trim()}
                  className={cn(
                    'px-5 py-2 rounded-xl text-[13px] font-semibold text-white shadow-sm transition-colors',
                    createMutation.isPending || !newTitle.trim()
                      ? 'bg-gray-300 cursor-not-allowed'
                      : 'bg-tp-accent hover:bg-tp-accent-dark',
                  )}
                >
                  {createMutation.isPending ? 'Creating\u2026' : 'Create Thread'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
