// src/components/ai/ChatWidget.tsx
//
// Embeddable AI chat widget for course view pages. Shows a floating chat
// button that opens a slide-out panel with session management and
// conversational AI interface.

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ChatBubbleLeftRightIcon,
  XMarkIcon,
  PaperAirplaneIcon,
  Bars3Icon,
  SparklesIcon,
} from '@heroicons/react/24/outline';
import { aiService } from '../../services/aiService';
import type { ChatMessage as ChatMessageType, ChatSession } from '../../services/aiService';
import { ChatMessage } from './ChatMessage';
import { ChatSessionList } from './ChatSessionList';
import { cn } from '../../lib/utils';
import { useToast } from '../common';

export interface ContentContext {
  type: 'interactive_lesson' | 'scenario';
  content_title: string;
  scene_title?: string;
  scene_narrative?: string;
  reflection_prompt?: string;
  situation?: string;
}

interface ChatWidgetProps {
  courseId: string;
  contentContext?: ContentContext | null;
}

// ─── Typing indicator ───────────────────────────────────────────────────────
const TypingIndicator: React.FC = () => (
  <div className="flex justify-start mb-4">
    <div className="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-3">
      <div className="flex items-center gap-1.5">
        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
      </div>
    </div>
  </div>
);

// ─── Main ChatWidget ────────────────────────────────────────────────────────
export const ChatWidget: React.FC<ChatWidgetProps> = ({ courseId, contentContext }) => {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [isOpen, setIsOpen] = useState(false);
  const [showSessions, setShowSessions] = useState(false);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [input, setInput] = useState('');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // ─── Queries ────────────────────────────────────────────────────────────
  const sessionsQuery = useQuery({
    queryKey: ['chatSessions', courseId],
    queryFn: () => aiService.chatSessions.list(courseId).then((r) => r.data),
    enabled: isOpen,
  });

  const messagesQuery = useQuery({
    queryKey: ['chatMessages', courseId, activeSessionId],
    queryFn: () =>
      activeSessionId
        ? aiService.chatSessions.messages(courseId, activeSessionId).then((r) => r.data)
        : Promise.resolve([]),
    enabled: isOpen && !!activeSessionId,
  });

  // ─── Mutations ──────────────────────────────────────────────────────────
  const createSessionMutation = useMutation({
    mutationFn: () => aiService.chatSessions.create(courseId).then((r) => r.data),
    onSuccess: (session: ChatSession) => {
      queryClient.invalidateQueries({ queryKey: ['chatSessions', courseId] });
      setActiveSessionId(session.id);
      setShowSessions(false);
    },
    onError: () => {
      toast.error('Failed to create chat session', 'Please try again.');
    },
  });

  const deleteSessionMutation = useMutation({
    mutationFn: (sessionId: string) =>
      aiService.chatSessions.delete(courseId, sessionId),
    onSuccess: (_data, deletedId) => {
      queryClient.invalidateQueries({ queryKey: ['chatSessions', courseId] });
      if (activeSessionId === deletedId) {
        setActiveSessionId(null);
      }
      toast.success('Chat session deleted');
    },
    onError: () => {
      toast.error('Failed to delete session', 'Please try again.');
    },
  });

  const sendMessageMutation = useMutation({
    mutationFn: (content: string) => {
      if (!activeSessionId) throw new Error('No active session');
      const ctx = contentContext ? ({ ...contentContext } as Record<string, unknown>) : undefined;
      return aiService.chatSessions.sendMessage(courseId, activeSessionId, content, ctx).then((r) => r.data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['chatMessages', courseId, activeSessionId] });
      queryClient.invalidateQueries({ queryKey: ['chatSessions', courseId] });
    },
    onError: () => {
      toast.error('Failed to send message', 'Please try again.');
    },
  });

  // ─── Auto-scroll to bottom ─────────────────────────────────────────────
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messagesQuery.data, sendMessageMutation.isPending, scrollToBottom]);

  // ─── Auto-select or create session on open ──────────────────────────────
  useEffect(() => {
    if (!isOpen || activeSessionId) return;
    const sessions = sessionsQuery.data;
    if (sessions && sessions.length > 0) {
      setActiveSessionId(sessions[0].id);
    }
  }, [isOpen, sessionsQuery.data, activeSessionId]);

  // ─── Handlers ───────────────────────────────────────────────────────────
  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || sendMessageMutation.isPending) return;

    // If no session, create one first then send
    if (!activeSessionId) {
      createSessionMutation.mutate(undefined, {
        onSuccess: (session) => {
          setActiveSessionId(session.id);
          // The message will be sent after re-render with new session
          const ctx = contentContext ? ({ ...contentContext } as Record<string, unknown>) : undefined;
          aiService.chatSessions
            .sendMessage(courseId, session.id, trimmed, ctx)
            .then(() => {
              queryClient.invalidateQueries({ queryKey: ['chatMessages', courseId, session.id] });
              queryClient.invalidateQueries({ queryKey: ['chatSessions', courseId] });
            })
            .catch(() => {
              toast.error('Failed to send message', 'Please try again.');
            });
        },
      });
    } else {
      sendMessageMutation.mutate(trimmed);
    }
    setInput('');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const messages: ChatMessageType[] = messagesQuery.data || [];

  return (
    <>
      {/* Floating trigger button */}
      {!isOpen && (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className={cn(
            'fixed bottom-6 right-6 z-40',
            'h-14 w-14 rounded-full shadow-lg',
            'bg-primary-600 text-white hover:bg-primary-700',
            'flex items-center justify-center',
            'transition-all duration-200 hover:scale-105',
            'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
          )}
          title="Open AI Chat"
          aria-label="Open AI tutor chat"
        >
          <SparklesIcon className="h-6 w-6" />
        </button>
      )}

      {/* Chat panel */}
      {isOpen && (
        <div
          className={cn(
            'fixed bottom-0 right-0 z-50',
            'w-full sm:w-[420px] h-[600px] sm:h-[640px]',
            'sm:bottom-6 sm:right-6',
            'bg-white rounded-t-2xl sm:rounded-2xl shadow-2xl border border-gray-200',
            'flex flex-col overflow-hidden',
          )}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 bg-primary-600 text-white sm:rounded-t-2xl">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setShowSessions(!showSessions)}
                className="p-1 rounded hover:bg-primary-500 transition-colors"
                title="Chat history"
                aria-label="Toggle sessions"
              >
                <Bars3Icon className="h-5 w-5" />
              </button>
              <SparklesIcon className="h-5 w-5" />
              <div className="min-w-0">
                <h2 className="text-sm font-semibold">AI Course Assistant</h2>
                {contentContext && (
                  <p className="truncate text-[10px] font-medium text-white/70">
                    {contentContext.type === 'interactive_lesson' ? 'Lesson' : 'Scenario'}:{' '}
                    {contentContext.scene_title || contentContext.content_title}
                  </p>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={() => {
                setIsOpen(false);
                setShowSessions(false);
              }}
              className="p-1 rounded hover:bg-primary-500 transition-colors"
              title="Close chat"
              aria-label="Close chat"
            >
              <XMarkIcon className="h-5 w-5" />
            </button>
          </div>

          {/* Body */}
          <div className="flex flex-1 overflow-hidden">
            {/* Sessions sidebar */}
            {showSessions && (
              <div className="w-56 border-r border-gray-200 bg-white shrink-0 overflow-hidden">
                <ChatSessionList
                  sessions={sessionsQuery.data || []}
                  activeSessionId={activeSessionId}
                  onSelectSession={(id) => {
                    setActiveSessionId(id);
                    setShowSessions(false);
                  }}
                  onCreateSession={() => createSessionMutation.mutate()}
                  onDeleteSession={(id) => deleteSessionMutation.mutate(id)}
                  isCreating={createSessionMutation.isPending}
                />
              </div>
            )}

            {/* Messages area */}
            <div className="flex-1 flex flex-col min-w-0">
              <div className="flex-1 overflow-y-auto px-4 py-4">
                {!activeSessionId && !messagesQuery.isLoading ? (
                  // Empty state: no session selected
                  <div className="flex flex-col items-center justify-center h-full text-center px-4">
                    <div className="w-16 h-16 rounded-full bg-primary-50 flex items-center justify-center mb-4">
                      <SparklesIcon className="h-8 w-8 text-primary-500" />
                    </div>
                    <h3 className="text-base font-semibold text-gray-900 mb-1">
                      AI Course Assistant
                    </h3>
                    <p className="text-sm text-gray-500 mb-4">
                      Ask questions about the course content. I can help explain concepts,
                      summarize materials, and more.
                    </p>
                    <button
                      type="button"
                      onClick={() => createSessionMutation.mutate()}
                      disabled={createSessionMutation.isPending}
                      className={cn(
                        'inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg',
                        'bg-primary-600 text-white hover:bg-primary-700',
                        'disabled:opacity-50 disabled:cursor-not-allowed',
                        'transition-colors',
                      )}
                    >
                      <ChatBubbleLeftRightIcon className="h-4 w-4" />
                      Start a Conversation
                    </button>
                  </div>
                ) : messagesQuery.isLoading ? (
                  <div className="flex items-center justify-center h-full">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
                  </div>
                ) : messages.length === 0 ? (
                  // Session exists but no messages yet
                  <div className="flex flex-col items-center justify-center h-full text-center px-4">
                    <SparklesIcon className="h-10 w-10 text-gray-300 mb-3" />
                    <p className="text-sm text-gray-500">
                      Start the conversation by typing a message below.
                    </p>
                  </div>
                ) : (
                  // Messages list
                  <>
                    {messages.map((msg) => (
                      <ChatMessage key={msg.id} message={msg} />
                    ))}
                    {sendMessageMutation.isPending && <TypingIndicator />}
                  </>
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Input area */}
              <div className="border-t border-gray-200 px-4 py-3">
                <div className="flex items-end gap-2">
                  <textarea
                    ref={inputRef}
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={handleKeyDown}
                    placeholder={
                      contentContext
                        ? contentContext.type === 'interactive_lesson'
                          ? 'Ask about this lesson...'
                          : 'Ask about this scenario...'
                        : 'Ask about this course...'
                    }
                    rows={1}
                    className={cn(
                      'flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm',
                      'placeholder:text-gray-400',
                      'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                      'max-h-24 overflow-y-auto',
                    )}
                  />
                  <button
                    type="button"
                    onClick={handleSend}
                    disabled={!input.trim() || sendMessageMutation.isPending}
                    className={cn(
                      'shrink-0 h-9 w-9 rounded-lg flex items-center justify-center',
                      'bg-primary-600 text-white hover:bg-primary-700',
                      'disabled:opacity-50 disabled:cursor-not-allowed',
                      'transition-colors',
                    )}
                    title="Send message"
                    aria-label="Send message"
                  >
                    <PaperAirplaneIcon className="h-4 w-4" />
                  </button>
                </div>
                <p className="text-[10px] text-gray-400 mt-1.5 text-center">
                  AI responses may not always be accurate. Verify important information.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
