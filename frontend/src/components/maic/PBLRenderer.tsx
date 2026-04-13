// src/components/maic/PBLRenderer.tsx
//
// Project-Based Learning renderer. Displays project overview, role selection,
// milestone tracking, deliverables checklist, and a simple AI chat panel
// for agent feedback via SSE streaming.

import React, { useState, useRef, useEffect, useCallback } from 'react';
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

interface PBLRendererProps {
  content: MAICPBLContent;
  sceneId: string;
  mode?: 'autonomous' | 'playback';
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

export const PBLRenderer = React.memo<PBLRendererProps>(function PBLRenderer({
  content,
  sceneId,
  mode = 'autonomous',
}) {
  const accessToken = useAuthStore((s) => s.accessToken);

  const [selectedRole, setSelectedRole] = useState<string | null>(null);
  const [completedMilestones, setCompletedMilestones] = useState<Set<string>>(new Set());
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [isSending, setIsSending] = useState(false);

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

  const toggleMilestone = useCallback((milestoneId: string) => {
    setCompletedMilestones((prev) => {
      const next = new Set(prev);
      if (next.has(milestoneId)) {
        next.delete(milestoneId);
      } else {
        next.add(milestoneId);
      }
      return next;
    });
  }, []);

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
      url: '/api/v1/teacher/maic/chat/',
      body: {
        message: trimmed,
        sceneId,
        context: 'pbl',
        selectedRole,
        completedMilestones: Array.from(completedMilestones),
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
  }, [chatInput, isSending, accessToken, sceneId, selectedRole, completedMilestones]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSendChat();
      }
    },
    [handleSendChat],
  );

  const sortedMilestones = [...content.milestones].sort((a, b) => a.order - b.order);
  const progress = sortedMilestones.length > 0
    ? Math.round((completedMilestones.size / sortedMilestones.length) * 100)
    : 0;

  return (
    <div className="flex flex-col h-full overflow-hidden bg-white">
      {/* Header */}
      <div className="shrink-0 px-6 py-4 border-b border-gray-100 bg-gradient-to-r from-indigo-50 to-purple-50">
        <h2 className="text-lg font-bold text-gray-900">{content.projectTitle}</h2>
        <p className="text-sm text-gray-600 mt-1">{content.description}</p>
      </div>

      {/* Main content grid */}
      <div className="flex-1 min-h-0 flex overflow-hidden">
        {/* Left panel: roles, milestones, deliverables */}
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

          {/* Milestones */}
          <section>
            <h3 className="flex items-center gap-2 text-sm font-semibold text-gray-800 mb-1">
              <Target className="h-4 w-4 text-emerald-500" />
              Milestones
            </h3>
            {/* Progress bar */}
            <div className="flex items-center gap-2 mb-3">
              <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-emerald-500 rounded-full transition-all duration-300"
                  style={{ width: `${progress}%` }}
                />
              </div>
              <span className="text-xs text-gray-400 tabular-nums">{progress}%</span>
            </div>
            <ol className="space-y-2">
              {sortedMilestones.map((milestone, idx) => (
                <li key={milestone.id}>
                  <label
                    className={cn(
                      'flex items-start gap-3 rounded-lg border px-3 py-2 cursor-pointer transition-colors',
                      completedMilestones.has(milestone.id)
                        ? 'border-emerald-200 bg-emerald-50'
                        : 'border-gray-200 hover:bg-gray-50',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={completedMilestones.has(milestone.id)}
                      onChange={() => toggleMilestone(milestone.id)}
                      className="mt-0.5 h-4 w-4 rounded text-emerald-600 focus:ring-emerald-500 border-gray-300"
                    />
                    <div className="min-w-0">
                      <p className={cn(
                        'text-sm font-medium',
                        completedMilestones.has(milestone.id)
                          ? 'text-emerald-700 line-through'
                          : 'text-gray-900',
                      )}>
                        {idx + 1}. {milestone.title}
                      </p>
                      <p className="text-xs text-gray-500 mt-0.5">{milestone.description}</p>
                    </div>
                  </label>
                </li>
              ))}
            </ol>
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
