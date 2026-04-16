// src/components/maic/ChatPanel.tsx
//
// Right sidebar panel for multi-agent classroom chat. Displays conversation
// history with agent-colored bubbles, role badges, relative timestamps,
// typing indicator, and allows user participation via SSE streaming.

import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { Send, BookOpen, MessageCircle } from 'lucide-react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useAuthStore } from '../../stores/authStore';
import { streamMAIC } from '../../lib/maicSSE';
import { updateClassroomChat } from '../../lib/maicDb';
import type { MAICChatMessage, MAICPlayerRole, MAICSSEEvent, MAICAgent } from '../../types/maic';
import { AgentAvatar } from './AgentAvatar';
import { cn } from '../../lib/utils';

type ChatTab = 'chat' | 'notes';

interface ChatPanelProps {
  role: MAICPlayerRole;
  classroomId: string;
}

// ─── Role badge labels ─────────────────────────────────────────────────────
const ROLE_LABELS: Record<string, string> = {
  professor: 'Professor',
  teaching_assistant: 'TA',
  assistant: 'Assistant',
  student: 'Student',
  student_rep: 'Student Rep',
  moderator: 'Moderator',
};

/** Format a timestamp as a relative time string (e.g., "2m ago", "just now"). */
function formatRelativeTime(ts: number): string {
  const diff = Math.max(0, Date.now() - ts);
  const seconds = Math.floor(diff / 1000);
  if (seconds < 10) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

/** Derive a subtle background tint from an agent color for message bubbles. */
function agentBubbleBg(color: string): string {
  // Append low opacity — works for hex colors
  return `${color}0D`; // ~5% opacity
}

export const ChatPanel = React.memo<ChatPanelProps>(function ChatPanel({ role, classroomId }) {
  const chatMessages = useMAICStageStore((s) => s.chatMessages);
  const addChatMessage = useMAICStageStore((s) => s.addChatMessage);
  const agents = useMAICStageStore((s) => s.agents);
  const scenes = useMAICStageStore((s) => s.scenes);
  const currentSceneIndex = useMAICStageStore((s) => s.currentSceneIndex);
  const speechText = useMAICStageStore((s) => s.speechText);
  const speakingAgentId = useMAICStageStore((s) => s.speakingAgentId);
  const accessToken = useAuthStore((s) => s.accessToken);

  const [activeTab, setActiveTab] = useState<ChatTab>('chat');
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [thinkingAgentId, setThinkingAgentId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Build lecture notes from scene speech actions
  const lectureNotes = useMemo(() => {
    return scenes.map((scene, idx) => {
      const speechTexts = (scene.actions || [])
        .filter((a) => a.type === 'speech' && (a as { text?: string }).text)
        .map((a) => (a as { text: string }).text);
      return {
        sceneIndex: idx,
        title: scene.title,
        notes: speechTexts,
        isCurrent: idx === currentSceneIndex,
      };
    }).filter((s) => s.notes.length > 0);
  }, [scenes, currentSceneIndex]);

  // Auto-scroll to newest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages.length]);

  // Persist chat history to IndexedDB when messages change
  useEffect(() => {
    if (chatMessages.length > 0 && classroomId) {
      updateClassroomChat(classroomId, chatMessages).catch(() => {});
    }
  }, [chatMessages.length, classroomId]);

  // Resolve agent by id
  const getAgent = useCallback(
    (agentId?: string): MAICAgent | null => {
      if (!agentId) return null;
      return agents.find((a) => a.id === agentId) || null;
    },
    [agents],
  );

  const handleSend = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || isSending || !accessToken) return;

    setInput('');
    setIsSending(true);

    // Add user message locally
    const userMsg: MAICChatMessage = {
      id: `msg-${Date.now()}`,
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    };
    addChatMessage(userMsg);

    // Cancel any in-flight request
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const endpoint = role === 'teacher'
      ? '/api/v1/teacher/maic/chat/'
      : '/api/v1/student/maic/chat/';

    await streamMAIC({
      url: endpoint,
      body: {
        classroomId,
        message: trimmed,
      },
      token: accessToken,
      signal: controller.signal,
      onEvent: (event: MAICSSEEvent) => {
        if (event.type === 'chat_message') {
          setThinkingAgentId(null);
          const data = event.data as { content: string; agentId?: string; agentName?: string };
          const assistantMsg: MAICChatMessage = {
            id: `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
            role: 'assistant',
            agentId: data.agentId || event.agentId,
            agentName: data.agentName,
            content: data.content,
            timestamp: Date.now(),
          };
          addChatMessage(assistantMsg);
        } else if (event.type === 'agent_thinking' || event.type === 'agent_speaking') {
          const data = event.data as { agentId?: string };
          setThinkingAgentId(data.agentId || event.agentId || null);
        }
      },
      onError: (err) => {
        const errorMsg: MAICChatMessage = {
          id: `msg-err-${Date.now()}`,
          role: 'system',
          content: `Error: ${err.message}`,
          timestamp: Date.now(),
        };
        addChatMessage(errorMsg);
      },
      onDone: () => {
        setIsSending(false);
        setThinkingAgentId(null);
      },
    });

    setIsSending(false);
  }, [input, isSending, accessToken, role, classroomId, addChatMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // Re-render timestamps periodically (every 30s)
  const [, setTick] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => setTick((t) => t + 1), 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col h-full bg-white border-l border-gray-200" role="complementary" aria-label="Chat panel">
      {/* Header with tabs */}
      <div className="shrink-0 border-b border-gray-100">
        <div className="flex">
          <button
            type="button"
            onClick={() => setActiveTab('chat')}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-colors',
              activeTab === 'chat'
                ? 'text-primary-600 border-b-2 border-primary-600'
                : 'text-gray-500 hover:text-gray-700',
            )}
          >
            <MessageCircle className="h-3.5 w-3.5" />
            Chat
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('notes')}
            className={cn(
              'flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-colors',
              activeTab === 'notes'
                ? 'text-primary-600 border-b-2 border-primary-600'
                : 'text-gray-500 hover:text-gray-700',
            )}
          >
            <BookOpen className="h-3.5 w-3.5" />
            Lecture Notes
          </button>
        </div>
      </div>

      {/* Lecture Notes Tab */}
      {activeTab === 'notes' && (
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
          {lectureNotes.length === 0 ? (
            <p className="text-sm text-gray-400 text-center mt-8">
              No lecture notes available yet.
            </p>
          ) : (
            lectureNotes.map((section) => (
              <div
                key={section.sceneIndex}
                className={cn(
                  'rounded-lg border p-3 transition-colors',
                  section.isCurrent
                    ? 'border-primary-200 bg-primary-50'
                    : 'border-gray-100 bg-white',
                )}
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className={cn(
                    'flex items-center justify-center h-5 w-5 rounded text-[10px] font-medium',
                    section.isCurrent
                      ? 'bg-primary-600 text-white'
                      : 'bg-gray-200 text-gray-600',
                  )}>
                    {section.sceneIndex + 1}
                  </span>
                  <h4 className="text-xs font-semibold text-gray-800 truncate">
                    {section.title}
                  </h4>
                  {section.isCurrent && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-primary-100 text-primary-700 font-medium">
                      Current
                    </span>
                  )}
                </div>
                <div className="space-y-1.5">
                  {section.notes.map((note, ni) => (
                    <p key={ni} className="text-xs text-gray-600 leading-relaxed">
                      {note}
                    </p>
                  ))}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* Chat Messages Tab */}
      <div className={cn('flex-1 overflow-y-auto px-4 py-3 space-y-3', activeTab !== 'chat' && 'hidden')} aria-live="polite">
        {chatMessages.length === 0 && (
          <p className="text-sm text-gray-400 text-center mt-8">
            No messages yet. Ask a question to start the conversation.
          </p>
        )}

        {chatMessages.map((msg) => {
          const agent = getAgent(msg.agentId);
          const isUser = msg.role === 'user';
          const isSystem = msg.role === 'system';

          if (isSystem) {
            return (
              <div key={msg.id} className="text-center">
                <span className="inline-block text-xs text-red-500 bg-red-50 rounded-full px-3 py-1">
                  {msg.content}
                </span>
              </div>
            );
          }

          const roleLabel = agent ? (ROLE_LABELS[agent.role] || agent.role) : null;

          return (
            <div
              key={msg.id}
              className={cn('flex gap-2', isUser ? 'flex-row-reverse' : 'flex-row')}
            >
              {/* Avatar */}
              {!isUser && agent ? (
                <div className="shrink-0 mt-0.5">
                  <AgentAvatar agent={agent} size="sm" />
                </div>
              ) : !isUser ? (
                <div className="shrink-0 h-8 w-8 rounded-full bg-gray-200 flex items-center justify-center text-xs text-gray-500 mt-0.5">
                  AI
                </div>
              ) : null}

              {/* Bubble */}
              <div className={cn('max-w-[80%] min-w-0')}>
                {/* Name + Role badge */}
                {!isUser && (
                  <div className="flex items-center gap-1.5 mb-0.5 px-1">
                    <p
                      className="text-xs font-medium"
                      style={{ color: agent?.color || '#6B7280' }}
                    >
                      {msg.agentName || agent?.name || 'Assistant'}
                    </p>
                    {roleLabel && (
                      <span
                        className="text-[9px] px-1.5 py-0.5 rounded-full font-medium"
                        style={{
                          backgroundColor: agent ? `${agent.color}1A` : '#F3F4F6',
                          color: agent?.color || '#6B7280',
                        }}
                      >
                        {roleLabel}
                      </span>
                    )}
                  </div>
                )}
                <div
                  className={cn(
                    'rounded-2xl px-3 py-2 text-sm leading-relaxed',
                    isUser
                      ? 'bg-primary-600 text-white rounded-br-md'
                      : 'bg-gray-100 text-gray-800 rounded-bl-md',
                  )}
                  style={
                    !isUser && agent
                      ? {
                          borderLeft: `3px solid ${agent.color}`,
                          backgroundColor: agentBubbleBg(agent.color),
                        }
                      : undefined
                  }
                >
                  {msg.content}
                </div>
                {/* Timestamp */}
                <p
                  className={cn(
                    'text-[10px] text-gray-300 mt-0.5 px-1',
                    isUser ? 'text-right' : 'text-left',
                  )}
                >
                  {isUser ? 'You' : ''}{isUser ? ' \u00b7 ' : ''}{formatRelativeTime(msg.timestamp)}
                </p>
              </div>
            </div>
          );
        })}

        {/* Thinking indicator with agent identity */}
        {isSending && (
          <div className="flex items-center gap-2 px-1">
            {(() => {
              const thinkingAgent = thinkingAgentId ? getAgent(thinkingAgentId) : null;
              return thinkingAgent ? (
                <div className="shrink-0">
                  <AgentAvatar agent={thinkingAgent} isSpeaking size="sm" />
                </div>
              ) : (
                <div className="shrink-0 h-8 w-8 rounded-full bg-gray-200 flex items-center justify-center text-xs text-gray-500">
                  AI
                </div>
              );
            })()}
            <div className="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-2.5 border border-gray-200">
              <div className="flex items-center gap-1.5">
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <div className="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                <span className="text-[10px] text-gray-400 ml-1">
                  {thinkingAgentId ? `${getAgent(thinkingAgentId)?.name || 'Agent'} is thinking...` : 'Agents are thinking...'}
                </span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area (chat tab only) */}
      <div className={cn('shrink-0 px-4 py-3 border-t border-gray-100', activeTab !== 'chat' && 'hidden')}>
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask the classroom..."
            rows={1}
            disabled={isSending}
            className={cn(
              'flex-1 resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm',
              'placeholder:text-gray-400',
              'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
              'max-h-20 overflow-y-auto',
              'disabled:opacity-50',
            )}
            aria-label="Chat message input"
          />
          <button
            type="button"
            onClick={handleSend}
            disabled={!input.trim() || isSending}
            className={cn(
              'shrink-0 h-9 w-9 rounded-lg flex items-center justify-center',
              'bg-primary-600 text-white hover:bg-primary-700',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'transition-colors',
            )}
            aria-label="Send message"
          >
            <Send className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
});
