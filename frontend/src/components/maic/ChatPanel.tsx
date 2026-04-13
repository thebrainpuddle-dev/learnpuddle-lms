// src/components/maic/ChatPanel.tsx
//
// Right sidebar panel for multi-agent classroom chat. Displays conversation
// history with agent avatars and allows user participation via SSE streaming.

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Send } from 'lucide-react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useAuthStore } from '../../stores/authStore';
import { streamMAIC } from '../../lib/maicSSE';
import type { MAICChatMessage, MAICPlayerRole, MAICSSEEvent } from '../../types/maic';
import { AgentAvatar } from './AgentAvatar';
import { cn } from '../../lib/utils';

interface ChatPanelProps {
  role: MAICPlayerRole;
  classroomId: string;
}

export const ChatPanel = React.memo<ChatPanelProps>(function ChatPanel({ role, classroomId }) {
  const chatMessages = useMAICStageStore((s) => s.chatMessages);
  const addChatMessage = useMAICStageStore((s) => s.addChatMessage);
  const agents = useMAICStageStore((s) => s.agents);
  const accessToken = useAuthStore((s) => s.accessToken);

  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Auto-scroll to newest message
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages.length]);

  // Resolve agent by id
  const getAgent = useCallback(
    (agentId?: string) => {
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

  return (
    <div className="flex flex-col h-full bg-white border-l border-gray-200" role="complementary" aria-label="Chat panel">
      {/* Header */}
      <div className="shrink-0 px-4 py-3 border-b border-gray-100">
        <h3 className="text-sm font-semibold text-gray-800">Classroom Chat</h3>
        <p className="text-xs text-gray-400">{agents.length} agent{agents.length !== 1 ? 's' : ''} in this session</p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3" aria-live="polite">
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
                {/* Name */}
                {!isUser && (
                  <p
                    className="text-xs font-medium mb-0.5 px-1"
                    style={{ color: agent?.color || '#6B7280' }}
                  >
                    {msg.agentName || agent?.name || 'Assistant'}
                  </p>
                )}
                <div
                  className={cn(
                    'rounded-2xl px-3 py-2 text-sm leading-relaxed',
                    isUser
                      ? 'bg-primary-600 text-white rounded-br-md'
                      : 'bg-gray-100 text-gray-800 rounded-bl-md',
                  )}
                >
                  {msg.content}
                </div>
                {isUser && (
                  <p className="text-[10px] text-gray-300 text-right mt-0.5 px-1">You</p>
                )}
              </div>
            </div>
          );
        })}

        {/* Typing indicator */}
        {isSending && (
          <div className="flex gap-2 items-center">
            <div className="h-8 w-8 rounded-full bg-gray-200 flex items-center justify-center text-xs text-gray-500">
              AI
            </div>
            <div className="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-2.5">
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

      {/* Input area */}
      <div className="shrink-0 px-4 py-3 border-t border-gray-100">
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
