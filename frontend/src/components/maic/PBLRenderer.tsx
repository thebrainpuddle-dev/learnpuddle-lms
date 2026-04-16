// src/components/maic/PBLRenderer.tsx
//
// Project-Based Learning renderer. Displays project overview, role selection,
// issue board with status tracking, deliverables checklist, and a simple AI
// chat panel for agent feedback via SSE streaming.
//
// Phase 3C: replaced simple milestones checklist with a 3-column issue board.

import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  Users,
  Target,
  CheckSquare,
  PackageCheck,
  Send,
  Loader2,
} from 'lucide-react';
import { useAuthStore } from '../../stores/authStore';
import { streamMAIC } from '../../lib/maicSSE';
import type { MAICSSEEvent } from '../../types/maic';
import type { MAICPBLContent } from '../../types/maic-scenes';
import { cn } from '../../lib/utils';
import { maicChatUrl, type MAICRole } from '../../lib/maic/endpoints';

// ─── Issue Board Types ───────────────────────────────────────────────────────

type IssueStatus = 'pending' | 'active' | 'done';
type IssuePriority = 'low' | 'medium' | 'high';

interface PBLIssue {
  id: string;
  title: string;
  description: string;
  status: IssueStatus;
  assignee?: string; // role id
  priority?: IssuePriority;
}

// ─── Component Props ─────────────────────────────────────────────────────────

interface PBLRendererProps {
  content: MAICPBLContent;
  sceneId: string;
  mode?: 'autonomous' | 'playback';
  /** Role-aware URL selection. Defaults to 'teacher' for backward compatibility. */
  role?: MAICRole;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

// ─── Status cycling helper ───────────────────────────────────────────────────

const STATUS_CYCLE: Record<IssueStatus, IssueStatus> = {
  pending: 'active',
  active: 'done',
  done: 'pending',
};

// ─── Priority dot color ──────────────────────────────────────────────────────

const PRIORITY_DOT_COLOR: Record<IssuePriority, string> = {
  low: 'bg-green-500',
  medium: 'bg-yellow-500',
  high: 'bg-red-500',
};

// ─── Column config ───────────────────────────────────────────────────────────

const COLUMNS: { key: IssueStatus; label: string; headerColor: string; badgeBg: string }[] = [
  { key: 'pending', label: 'Pending', headerColor: 'bg-gray-500', badgeBg: 'bg-gray-100 text-gray-600' },
  { key: 'active', label: 'Active', headerColor: 'bg-blue-500', badgeBg: 'bg-blue-100 text-blue-600' },
  { key: 'done', label: 'Done', headerColor: 'bg-green-500', badgeBg: 'bg-green-100 text-green-600' },
];

// ─── Main Component ──────────────────────────────────────────────────────────

export const PBLRenderer = React.memo<PBLRendererProps>(function PBLRenderer({
  content,
  sceneId,
  mode = 'autonomous',
  role,
}) {
  const accessToken = useAuthStore((s) => s.accessToken);

  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isSending, setIsSending] = useState(false);

  // ─── Issue board state ──────────────────────────────────────────────────
  const [issues, setIssues] = useState<PBLIssue[]>(() =>
    [...content.milestones]
      .sort((a, b) => a.order - b.order)
      .map((m) => ({
        id: m.id,
        title: m.title,
        description: m.description,
        status: 'pending' as IssueStatus,
        assignee: undefined,
        priority: undefined,
      })),
  );

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Auto-scroll chat
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages.length]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // ─── Issue board callbacks ──────────────────────────────────────────────

  const updateIssueStatus = useCallback((id: string, status: IssueStatus) => {
    setIssues((prev) =>
      prev.map((issue) => (issue.id === id ? { ...issue, status } : issue)),
    );
  }, []);

  const cycleIssueStatus = useCallback((id: string) => {
    setIssues((prev) =>
      prev.map((issue) =>
        issue.id === id ? { ...issue, status: STATUS_CYCLE[issue.status] } : issue,
      ),
    );
  }, []);

  // Grouped issues per column
  const issuesByStatus = useMemo(() => {
    const grouped: Record<IssueStatus, PBLIssue[]> = {
      pending: [],
      active: [],
      done: [],
    };
    for (const issue of issues) {
      grouped[issue.status].push(issue);
    }
    return grouped;
  }, [issues]);

  // Overall progress
  const doneCount = issuesByStatus.done.length;
  const totalCount = issues.length;
  const progress = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;

  // Derive completed milestone IDs for chat context
  const completedMilestoneIds = useMemo(
    () => issues.filter((i) => i.status === 'done').map((i) => i.id),
    [issues],
  );

  // Role lookup for assignee display
  const roleMap = useMemo(() => {
    const map = new Map<string, string>();
    for (const role of content.roles) {
      map.set(role.id, role.name);
    }
    return map;
  }, [content.roles]);

  // ─── Chat handlers ─────────────────────────────────────────────────────

  const handleSendChat = useCallback(async () => {
    const trimmed = chatInput.trim();
    if (!trimmed || isSending || !accessToken) return;

    setChatInput('');
    setIsSending(true);

    const userMsg: ChatMessage = {
      id: `pbl-msg-${Date.now()}`,
      role: 'user',
      content: trimmed,
    };
    setChatMessages((prev) => [...prev, userMsg]);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    await streamMAIC({
      url: maicChatUrl(role ?? 'teacher'),
      body: {
        message: trimmed,
        sceneId,
        context: 'pbl',
        selectedRole,
        completedMilestones: completedMilestoneIds,
      },
      token: accessToken,
      signal: controller.signal,
      onEvent: (event: MAICSSEEvent) => {
        if (event.type === 'chat_message') {
          const data = event.data as { content: string };
          const assistantMsg: ChatMessage = {
            id: `pbl-msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            role: 'assistant',
            content: data.content,
          };
          setChatMessages((prev) => [...prev, assistantMsg]);
        }
      },
      onError: (err) => {
        const errorMsg: ChatMessage = {
          id: `pbl-err-${Date.now()}`,
          role: 'assistant',
          content: `Error: ${err.message}`,
        };
        setChatMessages((prev) => [...prev, errorMsg]);
      },
      onDone: () => {
        setIsSending(false);
      },
    });

    setIsSending(false);
  }, [chatInput, isSending, accessToken, sceneId, selectedRole, completedMilestoneIds, role]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendChat();
      }
    },
    [handleSendChat],
  );

  return (
    <div className="flex flex-col h-full overflow-hidden bg-white">
      {/* Header */}
      <div className="shrink-0 px-6 py-4 border-b border-gray-100 bg-gradient-to-r from-indigo-50 to-purple-50">
        <h2 className="text-lg font-bold text-gray-900">{content.projectTitle}</h2>
        <p className="text-sm text-gray-600 mt-1">{content.description}</p>
      </div>

      {/* Main content grid */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        {/* Left panel: roles, issue board, deliverables */}
        <div className="flex-1 min-w-0 overflow-y-auto px-6 py-4 space-y-6">
          {/* Role Selection */}
          <section>
            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-800 mb-3">
              <Users className="h-4 w-4 text-indigo-500" />
              Select Your Role
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {content.roles.map((role) => (
                <button
                  key={role.id}
                  type="button"
                  onClick={() => setSelectedRole(role.id)}
                  className={cn(
                    'text-left rounded-lg border px-3 py-2.5 transition-colors',
                    selectedRole === role.id
                      ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-500'
                      : 'border-gray-200 hover:border-indigo-300 hover:bg-indigo-50/50',
                  )}
                >
                  <p className="text-sm font-medium text-gray-900">{role.name}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{role.description}</p>
                </button>
              ))}
            </div>
          </section>

          {/* Issue Board */}
          <section>
            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-800 mb-1">
              <Target className="h-4 w-4 text-emerald-500" />
              Issue Board
            </h3>

            {/* Overall progress */}
            <div className="flex items-center gap-2 mb-3">
              <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <span className="text-xs text-gray-500 tabular-nums whitespace-nowrap">
                {doneCount} of {totalCount} tasks done
              </span>
            </div>

            {/* 3-column board */}
            <div className="flex gap-3 overflow-x-auto pb-2">
              {COLUMNS.map((col) => {
                const columnIssues = issuesByStatus[col.key];
                return (
                  <div key={col.key} className="min-w-[200px] flex-1 flex flex-col">
                    {/* Column header */}
                    <div className="flex items-center gap-2 mb-2">
                      <div className={cn('h-2 w-2 rounded-full', col.headerColor)} />
                      <span className="text-xs font-semibold text-gray-700">{col.label}</span>
                      <span className={cn(
                        'text-xs font-medium rounded-full px-1.5 py-0.5 ml-auto',
                        col.badgeBg,
                      )}>
                        {columnIssues.length}
                      </span>
                    </div>

                    {/* Column body */}
                    <div className="flex-1 space-y-2 min-h-[60px]">
                      {columnIssues.length === 0 && (
                        <div className="text-xs text-gray-300 text-center py-4 border border-dashed border-gray-200 rounded-lg">
                          No items
                        </div>
                      )}
                      {columnIssues.map((issue) => (
                        <IssueCard
                          key={issue.id}
                          issue={issue}
                          roleName={issue.assignee ? roleMap.get(issue.assignee) : undefined}
                          onClick={() => cycleIssueStatus(issue.id)}
                        />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          {/* Deliverables */}
          <section>
            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-800 mb-3">
              <PackageCheck className="h-4 w-4 text-amber-500" />
              Deliverables
            </h3>
            <ul className="space-y-1.5">
              {content.deliverables.map((deliverable, idx) => (
                <li
                  key={idx}
                  className="flex items-start gap-2 text-sm text-gray-700"
                >
                  <CheckSquare className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                  {deliverable}
                </li>
              ))}
            </ul>
          </section>
        </div>

        {/* Right panel: AI Chat */}
        <div className="hidden md:flex flex-col w-72 shrink-0 border-l border-gray-200 bg-gray-50">
          <div className="shrink-0 px-4 py-3 border-b border-gray-100">
            <h3 className="text-sm font-semibold text-gray-800">AI Mentor</h3>
            <p className="text-xs text-gray-400">Ask questions about the project</p>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3" aria-live="polite">
            {chatMessages.length === 0 && (
              <p className="text-xs text-gray-400 text-center mt-8">
                Ask a question to get guidance on your project.
              </p>
            )}

            {chatMessages.map((msg) => (
              <div
                key={msg.id}
                className={cn('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}
              >
                <div
                  className={cn(
                    'max-w-[85%] rounded-2xl px-3 py-2 text-sm leading-relaxed',
                    msg.role === 'user'
                      ? 'bg-indigo-600 text-white rounded-br-md'
                      : 'bg-white text-gray-800 rounded-bl-md border border-gray-200',
                  )}
                >
                  {msg.content}
                </div>
              </div>
            ))}

            {isSending && (
              <div className="flex justify-start">
                <div className="bg-white rounded-2xl rounded-bl-md px-4 py-2.5 border border-gray-200">
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                    <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                    <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="shrink-0 px-4 py-3 border-t border-gray-100">
            <div className="flex items-end gap-2">
              <textarea
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask the AI mentor..."
                rows={1}
                disabled={isSending}
                className={cn(
                  'flex-1 resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm',
                  'placeholder:text-gray-400 bg-white',
                  'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent',
                  'max-h-20 overflow-y-auto',
                  'disabled:opacity-50',
                )}
                aria-label="PBL chat input"
              />
              <button
                type="button"
                onClick={handleSendChat}
                disabled={!chatInput.trim() || isSending}
                className={cn(
                  'shrink-0 h-9 w-9 rounded-lg flex items-center justify-center',
                  'bg-indigo-600 text-white hover:bg-indigo-700',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                  'transition-colors',
                )}
                aria-label="Send message"
              >
                {isSending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
});

// ─── Issue Card Component ────────────────────────────────────────────────────

const STATUS_BADGE: Record<IssueStatus, { bg: string; text: string; label: string }> = {
  pending: { bg: 'bg-gray-100', text: 'text-gray-600', label: 'Pending' },
  active: { bg: 'bg-blue-100', text: 'text-blue-600', label: 'Active' },
  done: { bg: 'bg-green-100', text: 'text-green-600', label: 'Done' },
};

interface IssueCardProps {
  issue: PBLIssue;
  roleName?: string;
  onClick: () => void;
}

const IssueCard = React.memo<IssueCardProps>(function IssueCard({ issue, roleName, onClick }) {
  const badge = STATUS_BADGE[issue.status];

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full text-left rounded-lg border px-3 py-2.5 transition-all',
        'hover:shadow-sm hover:border-gray-300 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:ring-offset-1',
        issue.status === 'done'
          ? 'border-green-200 bg-green-50/50'
          : issue.status === 'active'
            ? 'border-blue-200 bg-blue-50/30'
            : 'border-gray-200 bg-white',
      )}
      aria-label={`${issue.title} - ${badge.label}. Click to change status.`}
    >
      {/* Title */}
      <p className={cn(
        'text-sm font-medium leading-snug',
        issue.status === 'done' ? 'text-green-800 line-through' : 'text-gray-900',
      )}>
        {issue.title}
      </p>

      {/* Description (truncated to 2 lines) */}
      <p className="text-xs text-gray-500 mt-1 line-clamp-2">{issue.description}</p>

      {/* Footer: badges */}
      <div className="flex items-center gap-1.5 mt-2 flex-wrap">
        {/* Status badge */}
        <span className={cn('text-[10px] font-medium rounded-full px-1.5 py-0.5', badge.bg, badge.text)}>
          {badge.label}
        </span>

        {/* Assignee badge */}
        {roleName && (
          <span className="text-[10px] font-medium rounded-full px-1.5 py-0.5 bg-indigo-100 text-indigo-600">
            {roleName}
          </span>
        )}

        {/* Priority indicator */}
        {issue.priority && (
          <span className="flex items-center gap-1 ml-auto">
            <span className={cn('h-2 w-2 rounded-full', PRIORITY_DOT_COLOR[issue.priority])} />
            <span className="text-[10px] text-gray-400 capitalize">{issue.priority}</span>
          </span>
        )}
      </div>
    </button>
  );
});
