// src/components/maic/ChatbotChat.tsx
//
// SSE-streaming chat component. Sends messages via fetch() + ReadableStream
// (not EventSource) so JWT headers can be attached. Parses SSE "data:" lines
// and handles content / sources / done / error event types.
//
// Features:
// - Rich source citation cards with heading + snippet
// - Suggested quick prompts below welcome message
// - SessionStorage persistence scoped per user + tenant + mode + chatbot

import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  Send, Bot, User, Loader2, Trash2, BookOpen, ChevronDown, Sparkles,
} from 'lucide-react';
import { useChatbotStore } from '../../stores/chatbotStore';
import { useAuthStore } from '../../stores/authStore';
import { getAccessToken } from '../../utils/authSession';
import api from '../../config/api';
import type { ChatMessage, ChatSSEEvent } from '../../types/chatbot';
import { cn } from '../../lib/utils';

// Derive the base URL from the shared axios instance so SSE fetch() calls
// hit the same backend as every other API call.
const API_BASE_URL = api.defaults.baseURL ?? '';

// ─── Suggested Prompts ──────────────────────────────────────────────────────

const SUGGESTED_PROMPTS = [
  'Summarize the key concepts',
  'Create a practice quiz for me',
  'Explain in simpler terms',
  'What should I study for the exam?',
];

// ─── Props ──────────────────────────────────────────────────────────────────

interface Props {
  chatbotId: string;
  conversationId?: string | null;
  welcomeMessage: string;
  onConversationCreated?: (id: string) => void;
  suggestedPrompts?: string[];
  /** When 'preview', hits the teacher chat endpoint instead of the student one. */
  mode?: 'student' | 'preview';
}

interface ChatStorageScope {
  chatbotId: string;
  mode: 'student' | 'preview';
  userId?: string | null;
  tenantSubdomain?: string | null;
}

interface PersistedConversationMeta {
  conversationId: string | null;
}

const CHAT_MESSAGES_KEY_PREFIX = 'chatbot_messages_v2';
const CHAT_META_KEY_PREFIX = 'chatbot_meta_v2';

function normalizeScopeValue(value: string | null | undefined, fallback: string) {
  const trimmed = value?.trim();
  if (!trimmed) return fallback;
  return trimmed.replace(/[^a-zA-Z0-9._-]/g, '_');
}

function getStoredTenantSubdomain() {
  return sessionStorage.getItem('tenant_subdomain') || localStorage.getItem('tenant_subdomain');
}

function getScopedStorageKey(prefix: string, scope: ChatStorageScope) {
  const userSegment = normalizeScopeValue(scope.userId, 'anonymous');
  const tenantSegment = normalizeScopeValue(
    scope.tenantSubdomain ?? getStoredTenantSubdomain(),
    'unknown-tenant',
  );
  const modeSegment = normalizeScopeValue(scope.mode, 'student');
  const chatbotSegment = normalizeScopeValue(scope.chatbotId, 'unknown-chatbot');
  return `${prefix}:${tenantSegment}:${userSegment}:${modeSegment}:${chatbotSegment}`;
}

/** Load persisted messages from sessionStorage. */
function loadMessages(scope: ChatStorageScope): ChatMessage[] {
  try {
    const raw = sessionStorage.getItem(getScopedStorageKey(CHAT_MESSAGES_KEY_PREFIX, scope));
    if (raw) return JSON.parse(raw) as ChatMessage[];
  } catch {
    // corrupt data — ignore
  }
  return [];
}

/** Persist messages to sessionStorage. */
function saveMessages(scope: ChatStorageScope, messages: ChatMessage[]) {
  const key = getScopedStorageKey(CHAT_MESSAGES_KEY_PREFIX, scope);
  try {
    if (messages.length === 0) {
      sessionStorage.removeItem(key);
      return;
    }
    sessionStorage.setItem(key, JSON.stringify(messages));
  } catch {
    // storage full — ignore
  }
}

function loadConversationMeta(scope: ChatStorageScope): PersistedConversationMeta | null {
  try {
    const raw = sessionStorage.getItem(getScopedStorageKey(CHAT_META_KEY_PREFIX, scope));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedConversationMeta;
    if (!parsed || typeof parsed.conversationId === 'undefined') return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveConversationMeta(scope: ChatStorageScope, meta: PersistedConversationMeta) {
  try {
    sessionStorage.setItem(
      getScopedStorageKey(CHAT_META_KEY_PREFIX, scope),
      JSON.stringify(meta),
    );
  } catch {
    // storage full — ignore
  }
}

function clearConversationMeta(scope: ChatStorageScope) {
  try {
    sessionStorage.removeItem(getScopedStorageKey(CHAT_META_KEY_PREFIX, scope));
  } catch {
    // storage blocked — ignore
  }
}

/** Parse COMPLETE SSE lines into individual event objects. */
function parseSSELines(completePart: string): ChatSSEEvent[] {
  const events: ChatSSEEvent[] = [];
  const lines = completePart.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || !trimmed.startsWith('data: ')) continue;
    const raw = trimmed.slice(6).trim();
    if (!raw || raw === '[DONE]') continue;
    try {
      events.push(JSON.parse(raw) as ChatSSEEvent);
    } catch {
      // non-JSON data line, skip
    }
  }
  return events;
}

// ─── Source Citation Card ────────────────────────────────────────────────────

function SourceCitation({
  source,
}: {
  source: { title: string; page?: number | null; heading?: string; snippet?: string; is_auto?: boolean };
}) {
  const [expanded, setExpanded] = useState(false);
  const hasSnippet = Boolean(source.snippet);

  return (
    <button
      type="button"
      onClick={() => hasSnippet && setExpanded(!expanded)}
      className={cn(
        'w-full text-left rounded-lg border px-3 py-2.5 text-xs transition-all duration-200',
        'hover:shadow-sm',
        hasSnippet ? 'cursor-pointer' : 'cursor-default',
        source.is_auto
          ? 'border-teal-200/80 bg-gradient-to-r from-teal-50/80 to-teal-50/30 hover:border-teal-300'
          : 'border-indigo-200/80 bg-gradient-to-r from-indigo-50/80 to-indigo-50/30 hover:border-indigo-300',
      )}
    >
      <div className="flex items-start gap-2.5">
        <div
          className={cn(
            'shrink-0 mt-0.5 flex h-5 w-5 items-center justify-center rounded',
            source.is_auto ? 'bg-teal-100' : 'bg-indigo-100',
          )}
        >
          <BookOpen
            className={cn(
              'h-3 w-3',
              source.is_auto ? 'text-teal-600' : 'text-indigo-600',
            )}
            aria-hidden="true"
          />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-medium text-gray-800 truncate leading-5">
            {source.title}
            {source.page != null && (
              <span className="ml-1.5 rounded bg-gray-100 px-1 py-px text-[10px] text-gray-500 font-normal">
                p.{source.page}
              </span>
            )}
          </p>
          {source.heading && (
            <p className="text-gray-500 mt-0.5 truncate text-[11px]">{source.heading}</p>
          )}
          {hasSnippet && expanded && (
            <p className="text-gray-500 mt-1.5 whitespace-pre-wrap break-words leading-relaxed border-t border-gray-100 pt-1.5">
              {source.snippet}
            </p>
          )}
        </div>
        {hasSnippet && (
          <span className="shrink-0 p-0.5 text-gray-400">
            <ChevronDown
              className={cn(
                'h-3.5 w-3.5 transition-transform duration-200',
                expanded && 'rotate-180',
              )}
            />
          </span>
        )}
      </div>
    </button>
  );
}

// ─── Component ──────────────────────────────────────────────────────────────

export function ChatbotChat({
  chatbotId,
  conversationId,
  welcomeMessage,
  onConversationCreated,
  suggestedPrompts = SUGGESTED_PROMPTS,
  mode = 'student',
}: Props) {
  const userId = useAuthStore((s) => s.user?.id) ?? null;

  /** Build the scoped storage key for this chatbot + mode + user. */
  const storageScope = useMemo<ChatStorageScope>(
    () => ({ chatbotId, mode, userId, tenantSubdomain: getStoredTenantSubdomain() }),
    [chatbotId, mode, userId],
  );

  const [input, setInput] = useState('');
  const [localMessages, setLocalMessages] = useState<ChatMessage[]>(() =>
    loadMessages(storageScope),
  );
  const [error, setError] = useState<string | null>(null);

  const {
    isStreaming,
    streamingContent,
    setStreaming,
    setStreamingContent,
  } = useChatbotStore();

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const streamingRef = useRef(false);
  const messageCountRef = useRef(localMessages.length);
  messageCountRef.current = localMessages.length;

  // Track current conversation id locally (may be created mid-stream)
  const convIdRef = useRef<string | null>(conversationId ?? null);
  useEffect(() => {
    convIdRef.current = conversationId ?? null;
  }, [conversationId]);

  // Abort any in-flight SSE stream on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // Reload messages from sessionStorage when chatbotId changes
  useEffect(() => {
    const persisted = loadMessages(storageScope);
    setLocalMessages(persisted);
    setError(null);
    setStreamingContent('');
    setStreaming(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chatbotId, storageScope]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [localMessages, streamingContent]);

  // ── Send message & handle SSE stream ──────────────────────────────

  // Clear chat — wipes sessionStorage for this chatbot
  const handleClearChat = useCallback(() => {
    saveMessages(storageScope, []);
    clearConversationMeta(storageScope);
    convIdRef.current = null;
    setLocalMessages([]);
    setError(null);
    setStreamingContent('');
  }, [storageScope, setStreamingContent]);

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || streamingRef.current) return;
      streamingRef.current = true;

      // Check for valid token before attempting SSE fetch
      const token = getAccessToken();
      if (!token) {
        setError('Session expired. Please refresh the page to continue.');
        streamingRef.current = false;
        return;
      }

      const userMsg: ChatMessage = {
        role: 'user',
        content: text.trim(),
        timestamp: Date.now(),
      };

      // Build the history array from existing messages + the new user message
      const currentMessages = [...localMessages, userMsg];
      const history = currentMessages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      setLocalMessages(currentMessages);
      setInput('');
      setError(null);
      setStreaming(true);
      setStreamingContent('');

      // Placeholder assistant message (will be filled by stream)
      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
      };
      setLocalMessages((prev) => [...prev, assistantMsg]);

      const controller = new AbortController();
      abortRef.current = controller;

      let accumulated = '';
      let streamSources: ChatMessage['sources'] | null = null;

      try {
        const chatPath = mode === 'preview'
          ? `/v1/teacher/chatbots/${chatbotId}/chat/`
          : `/v1/student/chatbots/${chatbotId}/chat/`;
        // Build headers — include tenant subdomain for dev mode (axios interceptor
        // does this automatically, but fetch() bypasses axios).
        const fetchHeaders: Record<string, string> = {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        };
        const hostname = window.location.hostname;
        if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.endsWith('.localhost')) {
          const urlSubdomain = hostname.endsWith('.localhost')
            ? hostname.replace('.localhost', '')
            : null;
          const subdomain =
            urlSubdomain ||
            sessionStorage.getItem('tenant_subdomain') ||
            localStorage.getItem('tenant_subdomain');
          if (subdomain) {
            fetchHeaders['X-Tenant-Subdomain'] = subdomain;
          }
        }

        const res = await fetch(
          `${API_BASE_URL}${chatPath}`,
          {
            method: 'POST',
            headers: fetchHeaders,
            body: JSON.stringify({
              message: text.trim(),
              conversation_id: convIdRef.current,
              history,
            }),
            signal: controller.signal,
          },
        );

        if (!res.ok) {
          let errMsg = `Request failed (${res.status})`;
          if (res.status === 401) {
            errMsg = 'Your session has expired. Please refresh the page.';
          } else {
            try {
              const body = await res.json();
              errMsg = body.detail || body.error || errMsg;
            } catch {
              // Response is not JSON (e.g. HTML error page), ignore
            }
          }
          throw new Error(errMsg);
        }

        const reader = res.body?.getReader();
        if (!reader) throw new Error('No readable stream');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Only parse COMPLETE lines; keep incomplete remainder in buffer
          const lastNewline = buffer.lastIndexOf('\n');
          if (lastNewline < 0) continue; // no complete line yet

          const completePart = buffer.slice(0, lastNewline + 1);
          buffer = buffer.slice(lastNewline + 1);

          const events = parseSSELines(completePart);

          for (const evt of events) {
            switch (evt.type) {
              case 'content':
                accumulated += evt.content ?? '';
                setStreamingContent(accumulated);
                // Update the last assistant message in place
                setLocalMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && last.role === 'assistant') {
                    updated[updated.length - 1] = {
                      ...last,
                      content: accumulated,
                    };
                  }
                  return updated;
                });
                break;

              case 'sources':
                streamSources = evt.sources ?? null;
                break;

              case 'done': {
                // Attach sources and persist messages BEFORE notifying the
                // parent, because the parent changes the React `key` prop
                // which unmounts this component — aborting the stream before
                // the post-loop save can execute.
                setLocalMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && last.role === 'assistant' && streamSources) {
                    updated[updated.length - 1] = { ...last, sources: streamSources };
                    streamSources = null; // consumed
                  }
                  saveMessages(storageScope, updated);
                  return updated;
                });

                if (evt.conversation_id && !convIdRef.current) {
                  convIdRef.current = evt.conversation_id;
                  onConversationCreated?.(evt.conversation_id);
                }
                break;
              }

              case 'error':
                setError(evt.error ?? 'An error occurred');
                // Remove empty assistant placeholder on SSE error
                setLocalMessages((prev) => {
                  const updated = [...prev];
                  const last = updated[updated.length - 1];
                  if (last && last.role === 'assistant' && !last.content) {
                    updated.pop();
                  }
                  return updated;
                });
                break;
            }
          }
        }

        // Finalize: attach sources to the assistant message
        if (streamSources) {
          setLocalMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === 'assistant') {
              updated[updated.length - 1] = { ...last, sources: streamSources! };
            }
            return updated;
          });
        }

        // Persist messages to sessionStorage after successful response
        setLocalMessages((prev) => {
          saveMessages(storageScope, prev);
          return prev;
        });
      } catch (err: unknown) {
        if ((err as Error).name !== 'AbortError') {
          const errMsg = (err as Error).message || 'Failed to send message';
          setError(errMsg);

          // Remove the empty assistant placeholder on error
          setLocalMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            if (last && last.role === 'assistant' && !last.content) {
              updated.pop();
            }
            return updated;
          });
        }
      } finally {
        streamingRef.current = false;
        setStreaming(false);
        setStreamingContent('');
        abortRef.current = null;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [chatbotId, localMessages, onConversationCreated, mode, storageScope],
  );

  // Retry: re-send the last user message after an error
  const handleRetry = useCallback(() => {
    const lastUserMsg = [...localMessages].reverse().find((m) => m.role === 'user');
    if (lastUserMsg) {
      // Remove the failed user message so sendMessage re-adds it
      setLocalMessages((prev) => {
        const idx = prev.lastIndexOf(lastUserMsg);
        if (idx >= 0) return [...prev.slice(0, idx), ...prev.slice(idx + 1)];
        return prev;
      });
      setError(null);
      sendMessage(lastUserMsg.content);
    }
  }, [localMessages, sendMessage]);

  // Handle form submit
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  // Handle Enter key (Shift+Enter for newline)
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  // ── Render ────────────────────────────────────────────────────────

  const hasMessages = localMessages.length > 0;

  return (
    <div className="flex flex-col h-full bg-gradient-to-b from-gray-50/50 to-white">
      {/* ── Messages area ──────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-5">
        {/* Welcome message when no conversation started */}
        {!hasMessages && (
          <div className="max-w-2xl mx-auto mt-12 space-y-6">
            <div className="flex flex-col items-center text-center space-y-3">
              <div className="relative">
                <div className="h-14 w-14 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-200">
                  <Bot className="h-7 w-7 text-white" />
                </div>
                <span className="absolute -bottom-0.5 -right-0.5 h-4 w-4 rounded-full bg-emerald-400 border-2 border-white" />
              </div>
              <div className="rounded-2xl bg-white border border-gray-100 shadow-sm px-5 py-4 text-sm text-gray-600 max-w-md leading-relaxed">
                {welcomeMessage}
              </div>
            </div>

            {/* Suggested prompts */}
            {suggestedPrompts.length > 0 && (
              <div className="flex flex-wrap justify-center gap-2">
                {suggestedPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => sendMessage(prompt)}
                    disabled={isStreaming}
                    className={cn(
                      'group rounded-full border border-gray-200 bg-white px-4 py-2 text-xs font-medium',
                      'text-gray-600 shadow-sm',
                      'hover:border-indigo-300 hover:text-indigo-600 hover:shadow-md hover:shadow-indigo-100/50',
                      'active:scale-[0.97]',
                      'transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed',
                    )}
                  >
                    <Sparkles className="inline h-3 w-3 mr-1.5 text-gray-400 group-hover:text-indigo-400 transition-colors" />
                    {prompt}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Message list */}
        {localMessages.map((msg, idx) => {
          const isUser = msg.role === 'user';
          const isLastAssistant =
            !isUser &&
            idx === localMessages.length - 1 &&
            isStreaming;

          return (
            <div
              key={idx}
              className={cn(
                'flex items-start gap-3 max-w-2xl animate-in fade-in slide-in-from-bottom-2 duration-300',
                isUser ? 'ml-auto flex-row-reverse' : 'mr-auto',
              )}
            >
              {/* Avatar */}
              <div
                className={cn(
                  'shrink-0 h-8 w-8 rounded-xl flex items-center justify-center shadow-sm',
                  isUser
                    ? 'bg-gradient-to-br from-indigo-500 to-indigo-700'
                    : 'bg-white border border-gray-200',
                )}
              >
                {isUser ? (
                  <User className="h-4 w-4 text-white" />
                ) : (
                  <Bot className="h-4 w-4 text-indigo-600" />
                )}
              </div>

              {/* Bubble + sources */}
              <div className="space-y-2 min-w-0">
                <div
                  className={cn(
                    'rounded-2xl px-4 py-3 text-sm break-words max-w-prose',
                    isUser
                      ? 'bg-gradient-to-br from-indigo-600 to-indigo-700 text-white rounded-tr-md shadow-sm shadow-indigo-200 whitespace-pre-wrap'
                      : 'bg-white border border-gray-100 text-gray-700 rounded-tl-md shadow-sm',
                  )}
                >
                  {isUser ? (
                    msg.content || '\u200B'
                  ) : msg.content ? (
                    <div className="chat-markdown prose prose-sm prose-gray max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                      <ReactMarkdown
                        components={{
                          p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
                          strong: ({ children }) => <strong className="font-semibold text-gray-900">{children}</strong>,
                          em: ({ children }) => <em className="italic">{children}</em>,
                          ul: ({ children }) => <ul className="mb-2 ml-4 space-y-1 list-disc marker:text-gray-400">{children}</ul>,
                          ol: ({ children }) => <ol className="mb-2 ml-4 space-y-1 list-decimal marker:text-gray-400">{children}</ol>,
                          li: ({ children }) => <li className="leading-relaxed pl-1">{children}</li>,
                          h1: ({ children }) => <h3 className="text-base font-bold text-gray-900 mt-3 mb-1.5">{children}</h3>,
                          h2: ({ children }) => <h3 className="text-base font-bold text-gray-900 mt-3 mb-1.5">{children}</h3>,
                          h3: ({ children }) => <h4 className="text-sm font-bold text-gray-900 mt-2.5 mb-1">{children}</h4>,
                          code: ({ className, children, ...props }) => {
                            const isBlock = className?.includes('language-');
                            if (isBlock) {
                              return (
                                <pre className="bg-gray-50 border border-gray-200 rounded-lg p-3 overflow-x-auto my-2">
                                  <code className="text-xs text-gray-800 font-mono">{children}</code>
                                </pre>
                              );
                            }
                            return (
                              <code className="bg-gray-100 text-indigo-700 rounded px-1.5 py-0.5 text-xs font-mono" {...props}>
                                {children}
                              </code>
                            );
                          },
                          blockquote: ({ children }) => (
                            <blockquote className="border-l-3 border-indigo-300 pl-3 my-2 text-gray-600 italic">
                              {children}
                            </blockquote>
                          ),
                          hr: () => <hr className="my-3 border-gray-200" />,
                          a: ({ href, children }) => (
                            <a href={href} target="_blank" rel="noopener noreferrer" className="text-indigo-600 underline hover:text-indigo-800">
                              {children}
                            </a>
                          ),
                          table: ({ children }) => (
                            <div className="overflow-x-auto my-2">
                              <table className="min-w-full text-xs border border-gray-200 rounded-lg overflow-hidden">{children}</table>
                            </div>
                          ),
                          th: ({ children }) => <th className="bg-gray-50 px-3 py-1.5 text-left font-semibold text-gray-700 border-b border-gray-200">{children}</th>,
                          td: ({ children }) => <td className="px-3 py-1.5 border-b border-gray-100">{children}</td>,
                        }}
                      >
                        {msg.content}
                      </ReactMarkdown>
                    </div>
                  ) : isLastAssistant ? '' : '\u200B'}

                  {/* Typing indicator */}
                  {isLastAssistant && !msg.content && (
                    <span className="inline-flex gap-1.5 items-center px-1 py-0.5">
                      <span className="h-2 w-2 rounded-full bg-indigo-400/70 animate-bounce [animation-delay:0ms] [animation-duration:0.8s]" />
                      <span className="h-2 w-2 rounded-full bg-indigo-400/70 animate-bounce [animation-delay:150ms] [animation-duration:0.8s]" />
                      <span className="h-2 w-2 rounded-full bg-indigo-400/70 animate-bounce [animation-delay:300ms] [animation-duration:0.8s]" />
                    </span>
                  )}
                </div>

                {/* Source citation cards */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="space-y-1.5 max-w-prose">
                    <p className="flex items-center gap-1.5 text-[11px] font-semibold text-gray-400 uppercase tracking-wider pl-1">
                      <BookOpen className="h-3 w-3" />
                      Sources ({msg.sources.length})
                    </p>
                    {msg.sources.map((src, si) => (
                      <SourceCitation key={si} source={src} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Error message with retry */}
        {error && (
          <div className="max-w-2xl mx-auto flex items-center gap-3 rounded-xl bg-red-50 border border-red-100 px-4 py-3 text-sm text-red-700 shadow-sm">
            <span className="shrink-0 h-5 w-5 rounded-full bg-red-100 flex items-center justify-center">
              <span className="h-2 w-2 rounded-full bg-red-500" />
            </span>
            <span className="flex-1">{error}</span>
            <button
              type="button"
              onClick={handleRetry}
              className="shrink-0 px-3 py-1 rounded-lg text-xs font-medium bg-red-100 text-red-700 hover:bg-red-200 transition-colors"
            >
              Retry
            </button>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ── Input area ─────────────────────────────────────────────── */}
      <div className="px-4 py-3 bg-gradient-to-t from-white via-white to-white/80 backdrop-blur-sm">
        <form
          onSubmit={handleSubmit}
          className={cn(
            'flex items-end gap-2 max-w-2xl mx-auto',
            'rounded-2xl border border-gray-200 bg-white shadow-sm',
            'focus-within:border-indigo-300 focus-within:shadow-md focus-within:shadow-indigo-100/50',
            'transition-all duration-200 px-2 py-1.5',
          )}
        >
          {/* Clear Chat button */}
          {hasMessages && !isStreaming && (
            <button
              type="button"
              onClick={handleClearChat}
              className={cn(
                'shrink-0 inline-flex items-center justify-center rounded-xl h-9 w-9',
                'text-gray-400 hover:text-red-500 hover:bg-red-50 transition-all duration-200',
              )}
              aria-label="Clear chat"
              title="Clear chat"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything about your course..."
            rows={1}
            disabled={isStreaming}
            className={cn(
              'flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm',
              'focus:ring-0 focus:outline-none',
              'placeholder:text-gray-400',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'max-h-32 overflow-y-auto',
            )}
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className={cn(
              'shrink-0 inline-flex items-center justify-center rounded-xl h-9 w-9',
              'bg-indigo-600 text-white transition-all duration-200',
              'hover:bg-indigo-700 hover:shadow-md hover:shadow-indigo-200',
              'active:scale-95',
              'disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:shadow-none',
            )}
            aria-label="Send message"
          >
            {isStreaming ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </button>
        </form>
        <p className="text-center text-[10px] text-gray-400 mt-2">
          AI responses may not always be accurate. Verify important information.
        </p>
      </div>
    </div>
  );
}
