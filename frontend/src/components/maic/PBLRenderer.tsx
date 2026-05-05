// src/components/maic/PBLRenderer.tsx
//
// Project-Based Learning renderer (Phase 7, MAIC-705).
//
// Reads upstream's `PBLProjectConfig` shape from
// `content.projectConfig` (lifted from THU-MAIC/OpenMAIC's
// `lib/pbl/types.ts` under ADR-001a). Three panels:
//   1. Role selector  — built from agents where `is_user_role` is true
//   2. Issue board    — 3 columns driven by `is_active` / `is_done`
//   3. Chat panel     — sends to legacy SSE endpoint until MAIC-706
//                       swaps in the WS hook for /ws/maic/pbl/<id>/
//
// Issue status is DERIVED from upstream's flags rather than held in
// local state — the Judge agent's `COMPLETE` verdict (handled
// server-side at apps/maic_pbl/consumers.py) is what advances issues,
// and the renderer just reflects whatever the backend persisted.

import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  Users,
  Target,
  Send,
  Loader2,
} from 'lucide-react';
import { useAuthStore } from '../../stores/authStore';
import { streamMAIC } from '../../lib/maicSSE';
import type { MAICSSEEvent } from '../../types/maic';
import type { MAICPBLContent } from '../../types/maic-scenes';
import type { PBLAgent, PBLIssue } from '../../types/pbl';
import { cn } from '../../lib/utils';
import { maicChatUrl, type MAICRole } from '../../lib/maic/endpoints';
import { useMaicPBLChannel } from '../../hooks/useMaicPBLChannel';

// ─── Issue Board Types ───────────────────────────────────────────────────────

type IssueStatus = 'pending' | 'active' | 'done';

interface BoardIssue {
  id: string;
  title: string;
  description: string;
  status: IssueStatus;
  personInCharge: string;
}

// ─── Component Props ─────────────────────────────────────────────────────────

interface PBLRendererProps {
  content: MAICPBLContent;
  sceneId: string;
  mode?: 'autonomous' | 'playback';
  /** Role-aware URL selection. Defaults to 'teacher' for backward compatibility. */
  role?: MAICRole;
  /** Phase 7: when set, chat is driven by the PBL WS at
   *  `/ws/maic/pbl/<id>/` (apps/maic_pbl/consumers.py). When unset,
   *  the legacy SSE path is used (kept for any pre-Phase-7 callers). */
  pblSessionId?: string;
  /** Phase 7: model id for the WS chat. Required when `pblSessionId`
   *  is set; ignored otherwise. Same scheme as the create endpoint. */
  languageModelId?: string;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

// ─── Column config ───────────────────────────────────────────────────────────

const COLUMNS: { key: IssueStatus; label: string; headerColor: string; badgeBg: string }[] = [
  { key: 'pending', label: 'Pending', headerColor: 'bg-gray-500', badgeBg: 'bg-gray-100 text-gray-600' },
  { key: 'active', label: 'Active', headerColor: 'bg-blue-500', badgeBg: 'bg-blue-100 text-blue-600' },
  { key: 'done', label: 'Done', headerColor: 'bg-green-500', badgeBg: 'bg-green-100 text-green-600' },
];

function _toBoardIssue(i: PBLIssue): BoardIssue {
  const status: IssueStatus = i.is_done ? 'done' : i.is_active ? 'active' : 'pending';
  return {
    id: i.id,
    title: i.title,
    description: i.description,
    status,
    personInCharge: i.person_in_charge,
  };
}

// ─── Main Component ──────────────────────────────────────────────────────────

export const PBLRenderer = React.memo<PBLRendererProps>(function PBLRenderer({
  content,
  sceneId,
  mode: _mode = 'autonomous',
  role,
  pblSessionId,
  languageModelId,
}) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const config = content.projectConfig;
  const projectInfo = config.projectInfo;
  const wsMode = Boolean(pblSessionId);

  const [selectedRole, setSelectedRole] = useState<string | null>(
    config.selectedRole ?? null,
  );
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isSending, setIsSending] = useState(false);

  // ─── Derived data ───────────────────────────────────────────────────────

  // Roles are agents flagged is_user_role:true (upstream design loop
  // marks one human-driven agent per project). actor_role is the
  // displayed label; system_prompt seeds the description blurb.
  const userRoles = useMemo<PBLAgent[]>(
    () => config.agents.filter((a) => a.is_user_role),
    [config.agents],
  );

  const issues = useMemo<BoardIssue[]>(
    () =>
      [...config.issueboard.issues]
        .sort((a, b) => a.index - b.index)
        .map(_toBoardIssue),
    [config.issueboard.issues],
  );

  const issuesByStatus = useMemo(() => {
    const grouped: Record<IssueStatus, BoardIssue[]> = {
      pending: [],
      active: [],
      done: [],
    };
    for (const issue of issues) {
      grouped[issue.status].push(issue);
    }
    return grouped;
  }, [issues]);

  const doneCount = issuesByStatus.done.length;
  const totalCount = issues.length;
  const progress = totalCount > 0 ? Math.round((doneCount / totalCount) * 100) : 0;

  const completedIssueIds = useMemo(
    () => issues.filter((i) => i.status === 'done').map((i) => i.id),
    [issues],
  );

  // ─── Refs / effects ─────────────────────────────────────────────────────

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ─── WS chat hook (Phase 7, MAIC-706/707) ──────────────────────────────
  // autoConnect is gated on pblSessionId — when this prop is unset we
  // fall back to the legacy SSE path. The hook always returns a stable
  // value so we can call it unconditionally and keep React's hook order.

  const wsChannel = useMaicPBLChannel({
    sessionId: pblSessionId ?? '',
    autoConnect: wsMode,
  });
  const [wsUserMessages, setWsUserMessages] = useState<ChatMessage[]>([]);

  // Merge user-sent messages (local) with assistant turns (from hook)
  // into a single chronological list. We trust insertion order since
  // user sends are recorded synchronously before the WS replies.
  const wsMergedMessages = useMemo<ChatMessage[]>(() => {
    if (!wsMode) return [];
    const assistant: ChatMessage[] = wsChannel.messages.map((m, i) => ({
      id: `ws-asst-${i}`,
      role: 'assistant',
      content: m.content || (m.finished ? '' : '…'),
    }));
    // Interleave: each user message is followed by the next assistant
    // turn in order. With N user msgs and M assistant turns we render
    // u0, a0, u1, a1, ... and any trailing items in the longer list.
    const out: ChatMessage[] = [];
    const max = Math.max(wsUserMessages.length, assistant.length);
    for (let i = 0; i < max; i++) {
      if (i < wsUserMessages.length) out.push(wsUserMessages[i]);
      if (i < assistant.length) out.push(assistant[i]);
    }
    return out;
  }, [wsMode, wsUserMessages, wsChannel.messages]);

  // The chat panel reads from one source. wsMode → merged WS view.
  const displayedMessages: ChatMessage[] = wsMode ? wsMergedMessages : chatMessages;

  // isSending in wsMode = there's a turn in flight (last assistant
  // unfinished) OR there are more user msgs than assistant turns.
  const wsBusy =
    wsMode &&
    (wsUserMessages.length > wsChannel.messages.length ||
      (wsChannel.messages.length > 0 &&
        !wsChannel.messages[wsChannel.messages.length - 1].finished));
  const effectiveSending = wsMode ? wsBusy : isSending;

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [displayedMessages.length]);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // ─── Chat send (branches WS vs SSE) ─────────────────────────────────────

  const handleSendChat = useCallback(async () => {
    const trimmed = chatInput.trim();
    if (!trimmed || effectiveSending || !accessToken) return;

    setChatInput('');

    // ── WS path (Phase 7) ────────────────────────────────────────────
    if (wsMode) {
      if (wsChannel.status !== 'open') return;
      const userMsg: ChatMessage = {
        id: `ws-user-${Date.now()}`,
        role: 'user',
        content: trimmed,
      };
      setWsUserMessages((prev) => [...prev, userMsg]);
      wsChannel.send({
        action: 'chat',
        data: {
          message: trimmed,
          userRole: selectedRole ?? '',
          languageModelId: languageModelId ?? '',
        },
      });
      return;
    }

    // ── SSE legacy path ──────────────────────────────────────────────
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
        completedMilestones: completedIssueIds,
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
  }, [
    chatInput, effectiveSending, accessToken, sceneId, selectedRole,
    completedIssueIds, role, wsMode, wsChannel, languageModelId,
  ]);

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
        <h2 className="text-lg font-bold text-gray-900">{projectInfo.title}</h2>
        <p className="text-sm text-gray-600 mt-1">{projectInfo.description}</p>
      </div>

      {/* Main content grid */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        {/* Left panel: roles + issue board */}
        <div className="flex-1 min-w-0 overflow-y-auto px-6 py-4 space-y-6">
          {/* Role Selection */}
          {userRoles.length > 0 && (
            <section>
              <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-800 mb-3">
                <Users className="h-4 w-4 text-indigo-500" />
                Select Your Role
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {userRoles.map((agent) => (
                  <button
                    key={agent.name}
                    type="button"
                    onClick={() => setSelectedRole(agent.name)}
                    className={cn(
                      'text-left rounded-lg border px-3 py-2.5 transition-colors',
                      selectedRole === agent.name
                        ? 'border-indigo-500 bg-indigo-50 ring-1 ring-indigo-500'
                        : 'border-gray-200 hover:border-indigo-300 hover:bg-indigo-50/50',
                    )}
                  >
                    <p className="text-sm font-medium text-gray-900">{agent.actor_role}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{agent.name}</p>
                  </button>
                ))}
              </div>
            </section>
          )}

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
                        <IssueCard key={issue.id} issue={issue} />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
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
            {displayedMessages.length === 0 && (
              <p className="text-xs text-gray-400 text-center mt-8">
                Ask a question to get guidance on your project.
              </p>
            )}

            {displayedMessages.map((msg) => (
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

            {effectiveSending && (
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
                disabled={effectiveSending}
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
                disabled={
                  !chatInput.trim() ||
                  effectiveSending ||
                  (wsMode && wsChannel.status !== 'open')
                }
                className={cn(
                  'shrink-0 h-9 w-9 rounded-lg flex items-center justify-center',
                  'bg-indigo-600 text-white hover:bg-indigo-700',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                  'transition-colors',
                )}
                aria-label="Send message"
              >
                {effectiveSending ? (
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
  issue: BoardIssue;
}

const IssueCard = React.memo<IssueCardProps>(function IssueCard({ issue }) {
  const badge = STATUS_BADGE[issue.status];

  return (
    <div
      className={cn(
        'w-full text-left rounded-lg border px-3 py-2.5',
        issue.status === 'done'
          ? 'border-green-200 bg-green-50/50'
          : issue.status === 'active'
            ? 'border-blue-200 bg-blue-50/30'
            : 'border-gray-200 bg-white',
      )}
      aria-label={`${issue.title} - ${badge.label}`}
    >
      <p className={cn(
        'text-sm font-medium leading-snug',
        issue.status === 'done' ? 'text-green-800 line-through' : 'text-gray-900',
      )}>
        {issue.title}
      </p>

      <p className="text-xs text-gray-500 mt-1 line-clamp-2">{issue.description}</p>

      <div className="flex items-center gap-1.5 mt-2 flex-wrap">
        <span className={cn('text-[10px] font-medium rounded-full px-1.5 py-0.5', badge.bg, badge.text)}>
          {badge.label}
        </span>

        {issue.personInCharge && (
          <span className="text-[10px] font-medium rounded-full px-1.5 py-0.5 bg-indigo-100 text-indigo-600">
            {issue.personInCharge}
          </span>
        )}
      </div>
    </div>
  );
});
