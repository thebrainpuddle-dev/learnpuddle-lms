// src/pages/teacher/DiscussionThreadPage.tsx
//
// Teacher view of a single student discussion thread.
// Includes moderation controls (close, pin, hide replies) plus reply capability.

import React, { useState, useCallback, useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { cn } from '../../design-system/theme/cn';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useAuthStore } from '../../stores/authStore';
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

interface DiscussionReply {
  id: string;
  body: string;
  author: Author;
  like_count: number;
  is_liked: boolean;
  is_edited: boolean;
  depth: number;
  parent_id: string | null;
  created_at: string;
  children: DiscussionReply[];
}

interface ThreadDetail {
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
  is_subscribed: boolean;
  can_moderate: boolean;
  reply_count: number;
  view_count: number;
  created_at: string;
  last_reply_at: string | null;
  replies: DiscussionReply[];
}

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

function formatFullDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
  });
}

// ---------------------------------------------------------------------------
// SVG Icons
// ---------------------------------------------------------------------------

const ArrowLeftIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
    <path fillRule="evenodd" d="M17 10a.75.75 0 01-.75.75H5.612l4.158 3.96a.75.75 0 11-1.04 1.08l-5.5-5.25a.75.75 0 010-1.08l5.5-5.25a.75.75 0 111.04 1.08L5.612 9.25H16.25A.75.75 0 0117 10z" clipRule="evenodd" />
  </svg>
);

const HeartOutlineIcon = ({ className }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className || 'h-4 w-4'}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M21 8.25c0-2.485-2.099-4.5-4.688-4.5-1.935 0-3.597 1.126-4.312 2.733-.715-1.607-2.377-2.733-4.313-2.733C5.1 3.75 3 5.765 3 8.25c0 7.22 9 12 9 12s9-4.78 9-12z" />
  </svg>
);

const HeartFilledIcon = ({ className }: { className?: string }) => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className={className || 'h-4 w-4'}>
    <path d="M11.645 20.91l-.007-.003-.022-.012a15.247 15.247 0 01-.383-.218 25.18 25.18 0 01-4.244-3.17C4.688 15.36 2.25 12.174 2.25 8.25 2.25 5.322 4.714 3 7.688 3A5.5 5.5 0 0112 5.052 5.5 5.5 0 0116.313 3c2.973 0 5.437 2.322 5.437 5.25 0 3.925-2.438 7.111-4.739 9.256a25.175 25.175 0 01-4.244 3.17 15.247 15.247 0 01-.383.219l-.022.012-.007.004-.003.001a.752.752 0 01-.704 0l-.003-.001z" />
  </svg>
);

const ReplyIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
    <path fillRule="evenodd" d="M7.793 2.232a.75.75 0 01-.025 1.06L3.622 7.25h10.003a5.375 5.375 0 010 10.75H10.75a.75.75 0 010-1.5h2.875a3.875 3.875 0 000-7.75H3.622l4.146 3.957a.75.75 0 01-1.036 1.085l-5.5-5.25a.75.75 0 010-1.085l5.5-5.25a.75.75 0 011.06.025z" clipRule="evenodd" />
  </svg>
);

const SendIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
    <path d="M3.105 2.289a.75.75 0 00-.826.95l1.414 4.925A1.5 1.5 0 005.135 9.25h6.115a.75.75 0 010 1.5H5.135a1.5 1.5 0 00-1.442 1.086l-1.414 4.926a.75.75 0 00.826.95 28.896 28.896 0 0015.293-7.154.75.75 0 000-1.115A28.897 28.897 0 003.105 2.289z" />
  </svg>
);

const BellIcon = ({ filled }: { filled?: boolean }) =>
  filled ? (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
      <path fillRule="evenodd" d="M10 2a6 6 0 00-6 6c0 1.887-.454 3.665-1.257 5.234a.75.75 0 00.515 1.076 32.91 32.91 0 003.256.508 3.5 3.5 0 006.972 0 32.903 32.903 0 003.256-.508.75.75 0 00.515-1.076A11.448 11.448 0 0116 8a6 6 0 00-6-6z" clipRule="evenodd" />
    </svg>
  ) : (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-4 w-4">
      <path strokeLinecap="round" strokeLinejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
    </svg>
  );

const XIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
    <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
  </svg>
);

const ChatBubbleIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
    <path fillRule="evenodd" d="M3.43 2.524A41.29 41.29 0 0110 2c2.236 0 4.43.18 6.57.524 1.437.231 2.43 1.49 2.43 2.902v5.148c0 1.413-.993 2.67-2.43 2.902a41.102 41.102 0 01-3.55.414c-.28.02-.521.18-.643.413l-1.712 3.293a.75.75 0 01-1.33 0l-1.713-3.293a.783.783 0 00-.642-.413 41.108 41.108 0 01-3.55-.414C1.993 13.245 1 11.986 1 10.574V5.426c0-1.413.993-2.67 2.43-2.902z" clipRule="evenodd" />
  </svg>
);

const EyeIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
    <path d="M10 12.5a2.5 2.5 0 100-5 2.5 2.5 0 000 5z" />
    <path fillRule="evenodd" d="M.664 10.59a1.651 1.651 0 010-1.186A10.004 10.004 0 0110 3c4.257 0 7.893 2.66 9.336 6.41.147.381.146.804 0 1.186A10.004 10.004 0 0110 17c-4.257 0-7.893-2.66-9.336-6.41zM14 10a4 4 0 11-8 0 4 4 0 018 0z" clipRule="evenodd" />
  </svg>
);

// ---------------------------------------------------------------------------
// Like button
// ---------------------------------------------------------------------------

const LikeButton: React.FC<{
  isLiked: boolean;
  count: number;
  onToggle: () => void;
  disabled?: boolean;
}> = ({ isLiked, count, onToggle, disabled }) => {
  const [animating, setAnimating] = useState(false);

  const handleClick = () => {
    if (disabled) return;
    setAnimating(true);
    onToggle();
    setTimeout(() => setAnimating(false), 400);
  };

  return (
    <button
      onClick={handleClick}
      disabled={disabled}
      className={cn(
        'inline-flex items-center gap-1 text-[12px] font-medium transition-colors',
        isLiked ? 'text-rose-500 hover:text-rose-600' : 'text-gray-400 hover:text-rose-400',
        disabled && 'opacity-50 cursor-not-allowed',
      )}
    >
      <span className={cn('transition-transform', animating && 'animate-[like-pop_0.4s_ease-out]')}>
        {isLiked ? <HeartFilledIcon className="h-3.5 w-3.5" /> : <HeartOutlineIcon className="h-3.5 w-3.5" />}
      </span>
      {count > 0 && <span className="tabular-nums">{count}</span>}
      <style>{`@keyframes like-pop { 0% { transform: scale(1); } 30% { transform: scale(1.35); } 60% { transform: scale(0.9); } 100% { transform: scale(1); } }`}</style>
    </button>
  );
};

// ---------------------------------------------------------------------------
// Reply card (recursive)
// ---------------------------------------------------------------------------

const MAX_NESTING_DEPTH = 3;

const ReplyCard: React.FC<{
  reply: DiscussionReply;
  threadId: string;
  currentUserId: string | undefined;
  onReplyTo: (replyId: string, authorName: string) => void;
  onLikeToggle: (replyId: string, isLiked: boolean) => void;
  onHide: (replyId: string) => void;
  likingIds: Set<string>;
  canModerate: boolean;
}> = ({ reply, threadId, currentUserId, onReplyTo, onLikeToggle, onHide, likingIds, canModerate }) => {
  const canNest = reply.depth < MAX_NESTING_DEPTH;
  const indentPx = Math.min(reply.depth, MAX_NESTING_DEPTH) * 24;
  const isTeacher = reply.author.role && reply.author.role !== 'STUDENT';

  return (
    <div style={{ marginLeft: indentPx > 0 ? `${indentPx}px` : undefined }}>
      <div
        className={cn(
          'rounded-xl border p-3.5 mb-2 transition-colors',
          isTeacher
            ? 'border-orange-100 bg-orange-50/30'
            : reply.depth > 0
              ? 'border-gray-100 bg-gray-50/50'
              : 'border-gray-100 bg-white',
        )}
      >
        {/* Author line */}
        <div className="flex items-center gap-2 mb-2">
          <div className={cn(
            'h-6 w-6 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0',
            isTeacher
              ? 'bg-gradient-to-br from-orange-200 to-orange-300 text-orange-700'
              : 'bg-gradient-to-br from-tp-accent/20 to-tp-accent/40 text-tp-accent',
          )}>
            {reply.author.name.charAt(0).toUpperCase()}
          </div>
          <span className="text-[12px] font-semibold text-tp-text">{reply.author.name}</span>
          {isTeacher && (
            <span className="px-1.5 py-[1px] rounded text-[9px] font-semibold uppercase bg-orange-100 text-orange-600">
              Teacher
            </span>
          )}
          <span className="text-[11px] text-gray-400">{relativeTime(reply.created_at)}</span>
          {reply.is_edited && <span className="text-[10px] text-gray-400 italic">(edited)</span>}
        </div>

        <p className="text-[13px] text-gray-700 leading-relaxed whitespace-pre-wrap mb-2.5">{reply.body}</p>

        {/* Actions */}
        <div className="flex items-center gap-3">
          <LikeButton
            isLiked={reply.is_liked}
            count={reply.like_count}
            onToggle={() => onLikeToggle(reply.id, reply.is_liked)}
            disabled={likingIds.has(reply.id)}
          />
          {canNest && (
            <button
              onClick={() => onReplyTo(reply.id, reply.author.name)}
              className="inline-flex items-center gap-1 text-[12px] font-medium text-gray-400 hover:text-tp-accent transition-colors"
            >
              <ReplyIcon /> Reply
            </button>
          )}
          {canModerate && (
            <button
              onClick={() => onHide(reply.id)}
              className="inline-flex items-center gap-1 text-[12px] font-medium text-gray-400 hover:text-red-500 transition-colors"
            >
              Hide
            </button>
          )}
        </div>
      </div>

      {reply.children.length > 0 && (
        <div>
          {reply.children.map((child) => (
            <ReplyCard
              key={child.id}
              reply={child}
              threadId={threadId}
              currentUserId={currentUserId}
              onReplyTo={onReplyTo}
              onLikeToggle={onLikeToggle}
              onHide={onHide}
              likingIds={likingIds}
              canModerate={canModerate}
            />
          ))}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export const DiscussionThreadPage: React.FC = () => {
  usePageTitle('Discussion');
  const navigate = useNavigate();
  const { threadId } = useParams<{ threadId: string }>();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [replyBody, setReplyBody] = useState('');
  const [replyingTo, setReplyingTo] = useState<{ id: string; name: string } | null>(null);
  const [likingIds, setLikingIds] = useState<Set<string>>(new Set());

  // Fetch thread
  const { data: thread, isLoading } = useQuery<ThreadDetail>({
    queryKey: ['teacher-discussion-thread', threadId],
    enabled: Boolean(threadId),
    queryFn: async () => {
      const res = await api.get(`/v1/teacher/discussions/threads/${threadId}/`);
      return res.data;
    },
  });

  // Subscribe/unsubscribe
  const subscribeMutation = useMutation({
    mutationFn: async () => {
      if (thread?.is_subscribed) {
        await api.delete(`/v1/teacher/discussions/threads/${threadId}/subscribe/`);
      } else {
        await api.post(`/v1/teacher/discussions/threads/${threadId}/subscribe/`);
      }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['teacher-discussion-thread', threadId] }),
  });

  // Post reply
  const replyMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, string> = { body: replyBody };
      if (replyingTo) payload.parent_id = replyingTo.id;
      return api.post(`/v1/teacher/discussions/threads/${threadId}/replies/`, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['teacher-discussion-thread', threadId] });
      setReplyBody('');
      setReplyingTo(null);
    },
  });

  // Moderate thread
  const moderateMutation = useMutation({
    mutationFn: async (data: Record<string, unknown>) => {
      return api.patch(`/v1/teacher/discussions/threads/${threadId}/moderate/`, data);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['teacher-discussion-thread', threadId] }),
  });

  // Hide reply
  const hideReplyMutation = useMutation({
    mutationFn: async (replyId: string) => {
      return api.post(`/v1/teacher/discussions/threads/${threadId}/replies/${replyId}/moderate/`, {
        action: 'hide',
        reason: 'Hidden by teacher',
      });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['teacher-discussion-thread', threadId] }),
  });

  // Like toggle
  const handleLikeToggle = useCallback(
    async (replyId: string, currentlyLiked: boolean) => {
      setLikingIds((prev) => new Set(prev).add(replyId));
      try {
        if (currentlyLiked) {
          await api.delete(`/v1/teacher/discussions/threads/${threadId}/replies/${replyId}/like/`);
        } else {
          await api.post(`/v1/teacher/discussions/threads/${threadId}/replies/${replyId}/like/`);
        }
        queryClient.invalidateQueries({ queryKey: ['teacher-discussion-thread', threadId] });
      } finally {
        setLikingIds((prev) => {
          const next = new Set(prev);
          next.delete(replyId);
          return next;
        });
      }
    },
    [threadId, queryClient],
  );

  const handleReplyTo = useCallback((replyId: string, authorName: string) => {
    setReplyingTo({ id: replyId, name: authorName });
    textareaRef.current?.focus();
  }, []);

  const handleHide = useCallback((replyId: string) => {
    if (window.confirm('Hide this reply? It will no longer be visible to students.')) {
      hideReplyMutation.mutate(replyId);
    }
  }, [hideReplyMutation]);

  const handleSubmitReply = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!replyBody.trim()) return;
    replyMutation.mutate();
  }, [replyBody, replyMutation]);

  const handleTextareaInput = useCallback(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
    }
  }, []);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-8 w-32 tp-skeleton rounded-lg" />
        <div className="h-48 tp-skeleton rounded-2xl" />
        <div className="h-24 tp-skeleton rounded-2xl" />
      </div>
    );
  }

  if (!thread) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="inline-flex items-center gap-1.5 text-[13px] text-gray-500 hover:text-tp-text transition-colors">
          <ArrowLeftIcon /> Back
        </button>
        <div className="bg-white rounded-2xl border border-gray-100 p-8 text-center shadow-sm">
          <h2 className="text-[15px] font-semibold text-tp-text">Thread not found</h2>
          <p className="text-[13px] text-gray-400 mt-1">This discussion thread may have been deleted.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Back */}
      <button
        onClick={() => navigate('/teacher/discussions')}
        className="inline-flex items-center gap-1.5 text-[13px] text-gray-500 hover:text-tp-text transition-colors"
      >
        <ArrowLeftIcon /> Back to Discussions
      </button>

      {/* Thread header */}
      <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
        {/* Labels */}
        <div className="flex flex-wrap items-center gap-1.5 mb-3">
          {thread.grade_name && thread.section_name && (
            <span className="px-2 py-[2px] rounded-md text-[10px] font-semibold bg-blue-50 text-blue-600 uppercase tracking-wide">
              {thread.grade_name} - {thread.section_name}
            </span>
          )}
          {thread.course_title && (
            <span className="px-2 py-[2px] rounded-md text-[10px] font-semibold bg-purple-50 text-purple-600">
              {thread.course_title}
            </span>
          )}
          {thread.content_title && (
            <span className="px-2 py-[2px] rounded-md text-[10px] font-medium bg-gray-50 text-gray-500">
              {thread.content_title}
            </span>
          )}
        </div>

        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              {thread.is_pinned && (
                <span className="text-tp-accent flex-shrink-0" title="Pinned">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
                    <path d="M8.5 3.528v4.644c0 .729-.29 1.428-.805 1.944l-1.217 1.216a8.75 8.75 0 013.55.621l.502.201a7.25 7.25 0 004.178.365l-2.403-2.403a2.75 2.75 0 01-.805-1.944V3.528a40.205 40.205 0 00-3 0zm4.5.084a.75.75 0 00.75-.75 2.25 2.25 0 00-2.25-2.25h-3A2.25 2.25 0 006.25 2.862a.75.75 0 00.75.75h6zM9.206 17.708l-4.066-4.066a10.251 10.251 0 014.066 4.066z" />
                  </svg>
                </span>
              )}
              <span className={cn(
                'px-2 py-[3px] rounded-md text-[10px] font-semibold uppercase tracking-wide leading-none',
                thread.status === 'open' ? 'bg-emerald-50 text-emerald-600'
                  : thread.status === 'closed' ? 'bg-gray-100 text-gray-500'
                  : 'bg-amber-50 text-amber-600',
              )}>
                {thread.status}
              </span>
            </div>
            <h1 className="text-[20px] font-bold text-tp-text tracking-tight leading-tight">{thread.title}</h1>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            {/* Subscribe */}
            <button
              onClick={() => subscribeMutation.mutate()}
              disabled={subscribeMutation.isPending}
              className={cn(
                'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[12px] font-semibold border transition-colors',
                thread.is_subscribed
                  ? 'bg-tp-accent/10 border-tp-accent/20 text-tp-accent hover:bg-tp-accent/20'
                  : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300',
                subscribeMutation.isPending && 'opacity-50 cursor-not-allowed',
              )}
            >
              <BellIcon filled={thread.is_subscribed} />
              {thread.is_subscribed ? 'Subscribed' : 'Subscribe'}
            </button>
          </div>
        </div>

        {/* Author */}
        <div className="flex items-center gap-2 mb-3">
          <div className="h-7 w-7 rounded-full bg-gradient-to-br from-tp-accent/20 to-tp-accent/40 flex items-center justify-center text-[11px] font-bold text-tp-accent">
            {thread.author.name.charAt(0).toUpperCase()}
          </div>
          <div>
            <span className="text-[13px] font-semibold text-tp-text">{thread.author.name}</span>
            {thread.author.role === 'STUDENT' && (
              <span className="ml-1.5 px-1.5 py-[1px] rounded text-[9px] font-semibold uppercase bg-green-50 text-green-600">
                Student
              </span>
            )}
            <span className="text-[12px] text-gray-400 ml-2">{formatFullDate(thread.created_at)}</span>
          </div>
        </div>

        {/* Body */}
        <div className="text-[14px] text-gray-700 leading-relaxed whitespace-pre-wrap mb-4">{thread.body}</div>

        {/* Meta + moderation */}
        <div className="flex items-center justify-between border-t border-gray-100 pt-3">
          <div className="flex items-center gap-4 text-[12px] text-gray-400">
            <span className="inline-flex items-center gap-1.5"><EyeIcon /> {thread.view_count} views</span>
            <span className="inline-flex items-center gap-1.5"><ChatBubbleIcon /> {thread.reply_count} replies</span>
            {thread.last_reply_at && <span>Last reply {relativeTime(thread.last_reply_at)}</span>}
          </div>

          {/* Moderation controls */}
          {thread.can_moderate && (
            <div className="flex items-center gap-2">
              <button
                onClick={() => moderateMutation.mutate({ status: thread.status === 'open' ? 'closed' : 'open' })}
                disabled={moderateMutation.isPending}
                className="px-3 py-1 rounded-lg text-[11px] font-semibold border border-gray-200 text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                {thread.status === 'open' ? 'Close Thread' : 'Reopen Thread'}
              </button>
              <button
                onClick={() => moderateMutation.mutate({ is_pinned: !thread.is_pinned })}
                disabled={moderateMutation.isPending}
                className={cn(
                  'px-3 py-1 rounded-lg text-[11px] font-semibold border transition-colors disabled:opacity-50',
                  thread.is_pinned
                    ? 'border-tp-accent/30 text-tp-accent bg-tp-accent/5 hover:bg-tp-accent/10'
                    : 'border-gray-200 text-gray-600 hover:bg-gray-50',
                )}
              >
                {thread.is_pinned ? 'Unpin' : 'Pin'}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Replies heading */}
      <div className="flex items-center gap-2">
        <h2 className="text-[15px] font-bold text-tp-text">Replies</h2>
        <span className="text-[12px] text-gray-400 tabular-nums">({thread.reply_count})</span>
      </div>

      {/* Replies */}
      {thread.replies.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-2xl border border-gray-100 shadow-sm">
          <div className="text-gray-200 mb-2 flex justify-center">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" className="h-10 w-10">
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.625 9.75a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H8.25m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0H12m4.125 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm0 0h-.375m-13.5 3.01c0 1.6 1.123 2.994 2.707 3.227 1.087.16 2.185.283 3.293.369V21l4.184-4.183a1.14 1.14 0 01.778-.332 48.294 48.294 0 005.83-.498c1.585-.233 2.708-1.626 2.708-3.228V6.741c0-1.602-1.123-2.995-2.707-3.228A48.394 48.394 0 0012 3c-2.392 0-4.744.175-7.043.513C3.373 3.746 2.25 5.14 2.25 6.741v6.018z" />
            </svg>
          </div>
          <p className="text-[13px] text-gray-400">No replies yet.</p>
        </div>
      ) : (
        <div className="space-y-1">
          {thread.replies.map((reply) => (
            <ReplyCard
              key={reply.id}
              reply={reply}
              threadId={thread.id}
              currentUserId={user?.id}
              onReplyTo={handleReplyTo}
              onLikeToggle={handleLikeToggle}
              onHide={handleHide}
              likingIds={likingIds}
              canModerate={thread.can_moderate}
            />
          ))}
        </div>
      )}

      {/* Reply input */}
      {thread.status === 'open' && (
        <div className="bg-white rounded-2xl border border-gray-100 p-4 shadow-sm sticky bottom-4">
          {replyingTo && (
            <div className="flex items-center justify-between mb-2 px-1">
              <span className="text-[12px] text-gray-500">
                Replying to <span className="font-semibold text-tp-accent">{replyingTo.name}</span>
              </span>
              <button onClick={() => setReplyingTo(null)} className="text-gray-400 hover:text-gray-600 transition-colors">
                <XIcon />
              </button>
            </div>
          )}
          <form onSubmit={handleSubmitReply} className="flex gap-2">
            <textarea
              ref={textareaRef}
              value={replyBody}
              onChange={(e) => { setReplyBody(e.target.value); handleTextareaInput(); }}
              placeholder="Reply to this discussion..."
              rows={1}
              className="flex-1 rounded-xl border border-gray-200 px-3.5 py-2.5 text-[13px] text-tp-text placeholder:text-gray-300 focus:outline-none focus:ring-2 focus:ring-tp-accent/20 focus:border-tp-accent transition-colors resize-none min-h-[40px]"
            />
            <button
              type="submit"
              disabled={replyMutation.isPending || !replyBody.trim()}
              className={cn(
                'self-end px-4 py-2.5 rounded-xl text-white font-semibold text-[13px] transition-colors shadow-sm flex-shrink-0',
                replyMutation.isPending || !replyBody.trim()
                  ? 'bg-gray-300 cursor-not-allowed'
                  : 'bg-tp-accent hover:bg-tp-accent-dark',
              )}
            >
              {replyMutation.isPending ? (
                <span className="inline-flex items-center gap-1">
                  <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
                    <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" className="opacity-25" />
                    <path fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" className="opacity-75" />
                  </svg>
                  Sending
                </span>
              ) : (
                <span className="inline-flex items-center gap-1"><SendIcon /> Reply</span>
              )}
            </button>
          </form>
        </div>
      )}
    </div>
  );
};
