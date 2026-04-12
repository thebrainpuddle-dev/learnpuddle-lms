// src/components/maic/ChatbotChat.tsx
//
// SSE-streaming chat component. Sends messages via fetch() + ReadableStream
// (not EventSource) so JWT headers can be attached. Parses SSE "data:" lines
// and handles content / sources / done / error event types.

import { useState, useRef, useEffect, useCallback } from 'react';
import { Send, Bot, User, Loader2 } from 'lucide-react';
import { useChatbotStore } from '../../stores/chatbotStore';
import { getAccessToken } from '../../utils/authSession';
import api from '../../config/api';
import type { ChatMessage, ChatSSEEvent } from '../../types/chatbot';
import { cn } from '../../lib/utils';

// Derive the base URL from the shared axios instance so SSE fetch() calls
// hit the same backend as every other API call.
const API_BASE_URL = api.defaults.baseURL ?? '';

// ─── Props ──────────────────────────────────────────────────────────────────

interface Props {
  chatbotId: string;
  conversationId: string | null;
  welcomeMessage: string;
  onConversationCreated: (id: string) => void;
}

/** Parse an SSE text chunk into individual event objects. */
function parseSSEChunk(chunk: string): ChatSSEEvent[] {
  const events: ChatSSEEvent[] = [];
  const lines = chunk.split('\n');
  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const raw = line.slice(6).trim();
      if (!raw || raw === '[DONE]') continue;
      try {
        events.push(JSON.parse(raw) as ChatSSEEvent);
      } catch {
        // non-JSON data line, skip
      }
    }
  }
  return events;
}

// ─── Component ──────────────────────────────────────────────────────────────

export function ChatbotChat({
  chatbotId,
  conversationId,
  welcomeMessage,
  onConversationCreated,
}: Props) {
  const [input, setInput] = useState('');
  const [localMessages, setLocalMessages] = useState<ChatMessage[]>([]);
  const [sources, setSources] = useState<
    Map<number, Array<{ title: string; page?: number | null }>>
  >(new Map());
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
  const messageCountRef = useRef(localMessages.length);
  messageCountRef.current = localMessages.length;

  // Track current conversation id locally (may be created mid-stream)
  const convIdRef = useRef<string | null>(conversationId);
  useEffect(() => {
    convIdRef.current = conversationId;
  }, [conversationId]);

  // Abort any in-flight SSE stream on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  // Reset messages when conversation changes
  useEffect(() => {
    setLocalMessages([]);
    setSources(new Map());
    setError(null);
    setStreamingContent('');
    setStreaming(false);

    // If switching to an existing conversation, fetch its messages
    const controller = new AbortController();
    if (conversationId && chatbotId) {
      (async () => {
        try {
          const token = getAccessToken();
          const res = await fetch(
            `${API_BASE_URL}/v1/student/chatbots/${chatbotId}/conversations/${conversationId}/`,
            {
              headers: {
                Authorization: `Bearer ${token}`,
                'Content-Type': 'application/json',
              },
              signal: controller.signal,
            },
          );
          if (res.ok) {
            const data = await res.json();
            if (data.messages && Array.isArray(data.messages)) {
              setLocalMessages(data.messages);
            }
          }
        } catch {
          // silently fail — user can still send a new message
        }
      })();
    }

    return () => {
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId, chatbotId]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [localMessages, streamingContent]);

  // ── Send message & handle SSE stream ──────────────────────────────

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isStreaming) return;

      const userMsg: ChatMessage = {
        role: 'user',
        content: text.trim(),
        timestamp: Date.now(),
      };

      setLocalMessages((prev) => [...prev, userMsg]);
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
      let streamSources: Array<{ title: string; page?: number | null }> | null =
        null;

      try {
        const token = getAccessToken();
        const res = await fetch(
          `${API_BASE_URL}/v1/student/chatbots/${chatbotId}/chat/`,
          {
            method: 'POST',
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              message: text.trim(),
              conversation_id: convIdRef.current,
            }),
            signal: controller.signal,
          },
        );

        if (!res.ok) {
          const errBody = await res.text();
          throw new Error(errBody || `HTTP ${res.status}`);
        }

        const reader = res.body?.getReader();
        if (!reader) throw new Error('No readable stream');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });

          // Process complete lines in buffer
          const events = parseSSEChunk(buffer);
          // Keep only the last incomplete line in buffer
          const lastNewline = buffer.lastIndexOf('\n');
          buffer =
            lastNewline >= 0 ? buffer.slice(lastNewline + 1) : buffer;

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
                // Extract conversation_id if returned
                const doneData = evt as ChatSSEEvent & {
                  conversation_id?: string;
                };
                if (
                  doneData.conversation_id &&
                  !convIdRef.current
                ) {
                  convIdRef.current = doneData.conversation_id;
                  onConversationCreated(doneData.conversation_id);
                }
                break;
              }

              case 'error':
                setError(evt.error ?? 'An error occurred');
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
          setSources((prev) => {
            const next = new Map(prev);
            next.set(messageCountRef.current, streamSources!);
            return next;
          });
        }
      } catch (err: unknown) {
        if ((err as Error).name !== 'AbortError') {
          setError((err as Error).message || 'Failed to send message');
        }
      } finally {
        setStreaming(false);
        setStreamingContent('');
        abortRef.current = null;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [chatbotId, isStreaming, onConversationCreated],
  );

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
    <div className="flex flex-col h-full">
      {/* ── Messages area ──────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-4">
        {/* Welcome message when no conversation started */}
        {!hasMessages && (
          <div className="flex items-start gap-3 max-w-2xl mx-auto mt-8">
            <div className="shrink-0 h-8 w-8 rounded-full bg-indigo-100 flex items-center justify-center">
              <Bot className="h-4 w-4 text-indigo-600" />
            </div>
            <div className="rounded-2xl rounded-tl-sm bg-gray-100 px-4 py-3 text-sm text-gray-700 max-w-prose">
              {welcomeMessage}
            </div>
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
                'flex items-start gap-3 max-w-2xl',
                isUser ? 'ml-auto flex-row-reverse' : 'mr-auto',
              )}
            >
              {/* Avatar */}
              <div
                className={cn(
                  'shrink-0 h-8 w-8 rounded-full flex items-center justify-center',
                  isUser ? 'bg-indigo-600' : 'bg-indigo-100',
                )}
              >
                {isUser ? (
                  <User className="h-4 w-4 text-white" />
                ) : (
                  <Bot className="h-4 w-4 text-indigo-600" />
                )}
              </div>

              {/* Bubble */}
              <div className="space-y-1 min-w-0">
                <div
                  className={cn(
                    'rounded-2xl px-4 py-3 text-sm whitespace-pre-wrap break-words max-w-prose',
                    isUser
                      ? 'bg-indigo-600 text-white rounded-tr-sm'
                      : 'bg-gray-100 text-gray-700 rounded-tl-sm',
                  )}
                >
                  {msg.content || (isLastAssistant ? '' : '\u200B')}

                  {/* Typing indicator */}
                  {isLastAssistant && !msg.content && (
                    <span className="inline-flex gap-1 items-center">
                      <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:0ms]" />
                      <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:150ms]" />
                      <span className="h-1.5 w-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:300ms]" />
                    </span>
                  )}
                </div>

                {/* Source citations */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="flex flex-wrap gap-1 pl-1">
                    {msg.sources.map((src, si) => (
                      <span
                        key={si}
                        className="inline-flex items-center rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-600"
                      >
                        {src.title}
                        {src.page != null && ` (p.${src.page})`}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Error message */}
        {error && (
          <div className="max-w-2xl mx-auto rounded-lg bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ── Input area ─────────────────────────────────────────────── */}
      <div className="border-t border-gray-200 px-4 py-3 bg-white">
        <form
          onSubmit={handleSubmit}
          className="flex items-end gap-2 max-w-2xl mx-auto"
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            rows={1}
            disabled={isStreaming}
            className={cn(
              'flex-1 resize-none rounded-xl border border-gray-300 px-4 py-2.5 text-sm',
              'focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'max-h-32 overflow-y-auto',
            )}
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className={cn(
              'shrink-0 inline-flex items-center justify-center rounded-xl h-10 w-10',
              'bg-indigo-600 text-white transition-colors',
              'hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed',
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
      </div>
    </div>
  );
}
