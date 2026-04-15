// src/pages/student/DiscussionThreadPage.tsx
//
// Student view of a single discussion thread — reply, like, subscribe.

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
  course_title: string | null;
  content_title: string | null;
  status: 'open' | 'closed' | 'archived';
  is_pinned: boolean;
  is_subscribed: boolean;
  can_edit: boolean;
  reply_count: number;
  view_count: number;
  created_at: string;
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
// Icons
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

const PencilIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
    <path d="M2.695 14.763l-1.262 3.154a.5.5 0 00.65.65l3.155-1.262a4 4 0 001.343-.885L17.5 5.5a2.121 2.121 0 00-3-3L3.58 13.42a4 4 0 00-.885 1.343z" />
  </svg>
);

const TrashIcon = () => (
  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="h-3.5 w-3.5">
    <path fillRule="evenodd" d="M8.75 1A2.75 2.75 0 006 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 10.23 1.482l.149-.022.841 10.518A2.75 2.75 0 007.596 19h4.807a2.75 2.75 0 002.742-2.53l.841-10.519.149.023a.75.75 0 00.23-1.482A41.03 41.03 0 0014 4.193V3.75A2.75 2.75 0 0011.25 1h-2.5zM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4zM8.58 7.72a.75.75 0 00-1.5.06l.3 7.5a.75.75 0 101.5-.06l-.3-7.5zm4.34.06a.75.75 0 10-1.5-.06l-.3 7.5a.75.75 0 101.5.06l.3-7.5z" clipRule="evenodd" />
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
  return (
    <button
      onClick={() => { if (!disabled) { setAnimating(true); onToggle(); setTimeout(() => setAnimating(false), 400); }}}
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
// Reply card
// ---------------------------------------------------------------------------

const MAX_NESTING_DEPTH = 3;

const ReplyCard: React.FC<{
  reply: DiscussionReply;
  threadId: string;
  currentUserId: string | undefined;
  onReplyTo: (replyId: string, authorName: string) => void;
  onLikeToggle: (replyId: string, isLiked: boolean) => void;
  onEdit: (replyId: string, body: string) => void;
  onDelete: (replyId: string) => void;
  likingIds: Set<string>;
}> = ({ reply, threadId, currentUserId, onReplyTo, onLikeToggle, onEdit, onDelete, likingIds }) => {
  const [editing, setEditing] = useState(false);
  const [editBody, setEditBody] = useState(reply.body);
  const isOwn = currentUserId === reply.author.id;
  const canNest = reply.depth < MAX_NESTING_DEPTH;
  const isTeacher = reply.author.role && reply.author.role !== 'STUDENT';
  const indentPx = Math.min(reply.depth, MAX_NESTING_DEPTH) * 24;

  return (
    <div style={{ marginLeft: indentPx > 0 ? `${indentPx}px` : undefined }}>
      <div className={cn(
        'rounded-xl border p-3.5 mb-2 transition-colors',
        isTeacher ? 'border-orange-100 bg-orange-50/30'
          : reply.depth > 0 ? 'border-gray-100 bg-gray-50/50'
          : 'border-gray-100 bg-white',
      )}>
        <div className="flex items-center gap-2 mb-2">
          <div className={cn(
            'h-6 w-6 rounded-full flex items-center justify-center text-[10px] font-bold flex-shrink-0',
            isTeacher ? 'bg-gradient-to-br from-orange-200 to-orange-300 text-orange-700' : 'bg-gradient-to-br from-tp-accent/20 to-tp-accent/40 text-tp-accent',
          )}>
            {reply.author.name.charAt(0).toUpperCase()}
          </div>
          <span className="text-[12px] font-semibold text-tp-text">{reply.author.name}</span>
          {isTeacher && <span className="px-1.5 py-[1px] rounded text-[9px] font-semibold uppercase bg-orange-100 text-orange-600">Teacher</span>}
          <span className="text-[11px] text-gray-400">{relativeTime(reply.created_at)}</span>
          {reply.is_edited && <span className="text-[10px] text-gray-400 italic">(edited)</span>}
        </div>

        {editing ? (
          <div className="space-y-2">
            <textarea
              value={editBody}
              onChange={(e) => setEditBody(e.target.value)}
              rows={3}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-[13px] text-tp-text focus:outline-none focus:ring-2 focus:ring-tp-accent/20 focus:border-tp-accent resize-none"
              autoFocus
            />
            <div className="flex gap-2">
              <button onClick={() => { if (editBody.trim()) { onEdit(reply.id, editBody); setEditing(false); }}} disabled={!editBody.trim()} className="px-3 py-1 rounded-lg text-[11px] font-semibold bg-tp-accent text-white hover:bg-tp-accent-dark transition-colors disabled:bg-gray-300">Save</button>
              <button onClick={() => { setEditing(false); setEditBody(reply.body); }} className="px-3 py-1 rounded-lg text-[11px] font-medium text-gray-500 hover:bg-gray-100 transition-colors">Cancel</button>
            </div>
          </div>
        ) : (
          <p className="text-[13px] text-gray-700 leading-relaxed whitespace-pre-wrap mb-2.5">{reply.body}</p>
        )}

        {!editing && (
          <div className="flex items-center gap-3">
            <LikeButton isLiked={reply.is_liked} count={reply.like_count} onToggle={() => onLikeToggle(reply.id, reply.is_liked)} disabled={likingIds.has(reply.id)} />
            {canNest && (
              <button onClick={() => onReplyTo(reply.id, reply.author.name)} className="inline-flex items-center gap-1 text-[12px] font-medium text-gray-400 hover:text-tp-accent transition-colors">
                <ReplyIcon /> Reply
              </button>
            )}
            {isOwn && (
              <>
                <button onClick={() => { setEditBody(reply.body); setEditing(true); }} className="inline-flex items-center gap-1 text-[12px] font-medium text-gray-400 hover:text-blue-500 transition-colors"><PencilIcon /> Edit</button>
                <button onClick={() => onDelete(reply.id)} className="inline-flex items-center gap-1 text-[12px] font-medium text-gray-400 hover:text-red-500 transition-colors"><TrashIcon /> Delete</button>
              </>
            )}
          </div>
        )}
      </div>

      {reply.children.length > 0 && (
        <div>
          {reply.children.map((child) => (
            <ReplyCard key={child.id} reply={child} threadId={threadId} currentUserId={currentUserId} onReplyTo={onReplyTo} onLikeToggle={onLikeToggle} onEdit={onEdit} onDelete={onDelete} likingIds={likingIds} />
          ))}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

export const StudentDiscussionThreadPage: React.FC = () => {
  usePageTitle('Discussion');
  const navigate = useNavigate();
  const { threadId } = useParams<{ threadId: string }>();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [replyBody, setReplyBody] = useState('');
  const [replyingTo, setReplyingTo] = useState<{ id: string; name: string } | null>(null);
  const [likingIds, setLikingIds] = useState<Set<string>>(new Set());

  const { data: thread, isLoading } = useQuery<ThreadDetail>({
    queryKey: ['student-discussion-thread', threadId],
    enabled: Boolean(threadId),
    queryFn: async () => {
      const res = await api.get(`/v1/student/discussions/threads/${threadId}/`);
      return res.data;
    },
  });

  const subscribeMutation = useMutation({
    mutationFn: async () => {
      if (thread?.is_subscribed) {
        await api.delete(`/v1/student/discussions/threads/${threadId}/subscribe/`);
      } else {
        await api.post(`/v1/student/discussions/threads/${threadId}/subscribe/`);
      }
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['student-discussion-thread', threadId] }),
  });

  const replyMutation = useMutation({
    mutationFn: async () => {
      const payload: Record<string, string> = { body: replyBody };
      if (replyingTo) payload.parent_id = replyingTo.id;
      return api.post(`/v1/student/discussions/threads/${threadId}/replies/`, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['student-discussion-thread', threadId] });
      setReplyBody('');
      setReplyingTo(null);
    },
  });

  const editReplyMutation = useMutation({
    mutationFn: async ({ replyId, body }: { replyId: string; body: string }) => {
      return api.put(`/v1/student/discussions/threads/${threadId}/replies/${replyId}/`, { body });
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['student-discussion-thread', threadId] }),
  });

  const deleteReplyMutation = useMutation({
    mutationFn: async (replyId: string) => {
      return api.delete(`/v1/student/discussions/threads/${threadId}/replies/${replyId}/`);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['student-discussion-thread', threadId] }),
  });

  const handleLikeToggle = useCallback(async (replyId: string, currentlyLiked: boolean) => {
    setLikingIds((prev) => new Set(prev).add(replyId));
    try {
      if (currentlyLiked) {
        await api.delete(`/v1/student/discussions/threads/${threadId}/replies/${replyId}/like/`);
      } else {
        await api.post(`/v1/student/discussions/threads/${threadId}/replies/${replyId}/like/`);
      }
      queryClient.invalidateQueries({ queryKey: ['student-discussion-thread', threadId] });
    } finally {
      setLikingIds((prev) => { const next = new Set(prev); next.delete(replyId); return next; });
    }
  }, [threadId, queryClient]);

  const handleReplyTo = useCallback((replyId: string, authorName: string) => {
    setReplyingTo({ id: replyId, name: authorName });
    textareaRef.current?.focus();
  }, []);

  const handleEdit = useCallback((replyId: string, body: string) => {
    editReplyMutation.mutate({ replyId, body });
  }, [editReplyMutation]);

  const handleDelete = useCallback((replyId: string) => {
    if (window.confirm('Delete this reply?')) deleteReplyMutation.mutate(replyId);
  }, [deleteReplyMutation]);

  const handleSubmitReply = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!replyBody.trim()) return;
    replyMutation.mutate();
  }, [replyBody, replyMutation]);

  const handleTextareaInput = useCallback(() => {
    const el = textareaRef.current;
    if (el) { el.style.height = 'auto'; el.style.height = `${Math.min(el.scrollHeight, 200)}px`; }
  }, []);

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
      <button onClick={() => navigate('/student/discussions')} className="inline-flex items-center gap-1.5 text-[13px] text-gray-500 hover:text-tp-text transition-colors">
        <ArrowLeftIcon /> Back to Discussions
      </button>

      {/* Thread header */}
      <div className="bg-white rounded-2xl border border-gray-100 p-5 shadow-sm">
        {/* Labels */}
        {(thread.course_title || thread.content_title) && (
          <div className="flex flex-wrap items-center gap-1.5 mb-3">
            {thread.course_title && <span className="px-2 py-[2px] rounded-md text-[10px] font-semibold bg-purple-50 text-purple-600">{thread.course_title}</span>}
            {thread.content_title && <span className="px-2 py-[2px] rounded-md text-[10px] font-medium bg-gray-50 text-gray-500">{thread.content_title}</span>}
          </div>
        )}

        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 mb-1">
              <span className={cn(
                'px-2 py-[3px] rounded-md text-[10px] font-semibold uppercase tracking-wide leading-none',
                thread.status === 'open' ? 'bg-emerald-50 text-emerald-600' : 'bg-gray-100 text-gray-500',
              )}>{thread.status}</span>
            </div>
            <h1 className="text-[20px] font-bold text-tp-text tracking-tight leading-tight">{thread.title}</h1>
          </div>
          <button
            onClick={() => subscribeMutation.mutate()}
            disabled={subscribeMutation.isPending}
            className={cn(
              'inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[12px] font-semibold border transition-colors flex-shrink-0',
              thread.is_subscribed ? 'bg-tp-accent/10 border-tp-accent/20 text-tp-accent' : 'bg-white border-gray-200 text-gray-500',
              subscribeMutation.isPending && 'opacity-50 cursor-not-allowed',
            )}
          >
            <BellIcon filled={thread.is_subscribed} />
            {thread.is_subscribed ? 'Subscribed' : 'Subscribe'}
          </button>
        </div>

        <div className="flex items-center gap-2 mb-3">
          <div className="h-7 w-7 rounded-full bg-gradient-to-br from-tp-accent/20 to-tp-accent/40 flex items-center justify-center text-[11px] font-bold text-tp-accent">
            {thread.author.name.charAt(0).toUpperCase()}
          </div>
          <div>
            <span className="text-[13px] font-semibold text-tp-text">{thread.author.name}</span>
            <span className="text-[12px] text-gray-400 ml-2">{formatFullDate(thread.created_at)}</span>
          </div>
        </div>

        <div className="text-[14px] text-gray-700 leading-relaxed whitespace-pre-wrap mb-4">{thread.body}</div>

        <div className="flex items-center gap-4 text-[12px] text-gray-400 border-t border-gray-100 pt-3">
          <span className="inline-flex items-center gap-1.5"><EyeIcon /> {thread.view_count} views</span>
          <span className="inline-flex items-center gap-1.5"><ChatBubbleIcon /> {thread.reply_count} replies</span>
        </div>
      </div>

      {/* Replies */}
      <div className="flex items-center gap-2">
        <h2 className="text-[15px] font-bold text-tp-text">Replies</h2>
        <span className="text-[12px] text-gray-400 tabular-nums">({thread.reply_count})</span>
      </div>

      {thread.replies.length === 0 ? (
        <div className="text-center py-12 bg-white rounded-2xl border border-gray-100 shadow-sm">
          <p className="text-[13px] text-gray-400">No replies yet. Be the first to respond!</p>
        </div>
      ) : (
        <div className="space-y-1">
          {thread.replies.map((reply) => (
            <ReplyCard key={reply.id} reply={reply} threadId={thread.id} currentUserId={user?.id} onReplyTo={handleReplyTo} onLikeToggle={handleLikeToggle} onEdit={handleEdit} onDelete={handleDelete} likingIds={likingIds} />
          ))}
        </div>
      )}

      {/* Reply input */}
      {thread.status === 'open' && (
        <div className="bg-white rounded-2xl border border-gray-100 p-4 shadow-sm sticky bottom-4">
          {replyingTo && (
            <div className="flex items-center justify-between mb-2 px-1">
              <span className="text-[12px] text-gray-500">Replying to <span className="font-semibold text-tp-accent">{replyingTo.name}</span></span>
              <button onClick={() => setReplyingTo(null)} className="text-gray-400 hover:text-gray-600 transition-colors"><XIcon /></button>
            </div>
          )}
          <form onSubmit={handleSubmitReply} className="flex gap-2">
            <textarea
              ref={textareaRef}
              value={replyBody}
              onChange={(e) => { setReplyBody(e.target.value); handleTextareaInput(); }}
              placeholder="Write a reply..."
              rows={1}
              className="flex-1 rounded-xl border border-gray-200 px-3.5 py-2.5 text-[13px] text-tp-text placeholder:text-gray-300 focus:outline-none focus:ring-2 focus:ring-tp-accent/20 focus:border-tp-accent transition-colors resize-none min-h-[40px]"
            />
            <button
              type="submit"
              disabled={replyMutation.isPending || !replyBody.trim()}
              className={cn(
                'self-end px-4 py-2.5 rounded-xl text-white font-semibold text-[13px] transition-colors shadow-sm flex-shrink-0',
                replyMutation.isPending || !replyBody.trim() ? 'bg-gray-300 cursor-not-allowed' : 'bg-tp-accent hover:bg-tp-accent-dark',
              )}
            >
              {replyMutation.isPending ? 'Sending\u2026' : <span className="inline-flex items-center gap-1"><SendIcon /> Reply</span>}
            </button>
          </form>
        </div>
      )}
    </div>
  );
};
