// src/components/maic/RoundtablePanel.tsx
//
// Discussion mode overlay supporting qa, roundtable, and classroom session
// types. Displays agent avatars with speaking indicators, speech bubbles,
// and allows user participation via SSE streaming.

import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { X, Send, Loader2, MessageCircle, RotateCcw } from 'lucide-react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useAuthStore } from '../../stores/authStore';
import { streamMAIC } from '../../lib/maicSSE';
import type { MAICSSEEvent, MAICAgent } from '../../types/maic';
import { AgentAvatar } from './AgentAvatar';
import { cn } from '../../lib/utils';

interface RoundtablePanelProps {
  sessionType: 'qa' | 'roundtable' | 'classroom';
  topic: string;
  agentIds: string[];
  onClose: () => void;
}

interface DiscussionMessage {
  id: string;
  agentId?: string;
  role: 'user' | 'agent';
  content: string;
}

const AGENT_BUBBLE_COLORS = [
  'bg-blue-50 border-blue-200 text-blue-900',
  'bg-green-50 border-green-200 text-green-900',
  'bg-purple-50 border-purple-200 text-purple-900',
  'bg-amber-50 border-amber-200 text-amber-900',
  'bg-rose-50 border-rose-200 text-rose-900',
  'bg-cyan-50 border-cyan-200 text-cyan-900',
];

const SESSION_LABELS: Record<string, string> = {
  qa: 'Q&A Session',
  roundtable: 'Roundtable Discussion',
  classroom: 'Classroom Discussion',
};

export const RoundtablePanel = React.memo<RoundtablePanelProps>(
  function RoundtablePanel({ sessionType, topic, agentIds, onClose }) {
    const allAgents = useMAICStageStore((s) => s.agents);
    const scenes = useMAICStageStore((s) => s.scenes);
    const currentSceneIndex = useMAICStageStore((s) => s.currentSceneIndex);
    const accessToken = useAuthStore((s) => s.accessToken);

    const [messages, setMessages] = useState<DiscussionMessage[]>([]);
    const [input, setInput] = useState('');
    const [isSending, setIsSending] = useState(false);
    const [speakingAgentId, setSpeakingAgentId] = useState<string | null>(null);

    const messagesEndRef = useRef<HTMLDivElement>(null);
    const abortRef = useRef<AbortController | null>(null);

    // Resolve agents that are part of this discussion
    const discussionAgents = allAgents.filter((a) => agentIds.includes(a.id));

    // Map agent index to bubble color
    const agentColorMap = new Map<string, string>();
    discussionAgents.forEach((agent, idx) => {
      agentColorMap.set(agent.id, AGENT_BUBBLE_COLORS[idx % AGENT_BUBBLE_COLORS.length]);
    });

    // ─── Suggested Topics ─────────────────────────────────────────────
    const suggestedTopics = useMemo(() => {
      const currentScene = scenes[currentSceneIndex];
      if (!currentScene) return [];
      const title = currentScene.title;
      return [
        `What are the key implications of ${title}?`,
        `How does ${title} apply in practice?`,
        `What are common misconceptions about ${title}?`,
        `Can you explain the main concepts of ${title} in simpler terms?`,
      ];
    }, [scenes, currentSceneIndex]);

    // ─── Turn-taking indicators ───────────────────────────────────────
    const [respondingAgentIds, setRespondingAgentIds] = useState<string[]>([]);

    useEffect(() => {
      if (isSending && !speakingAgentId) {
        // Show sequential response indicators for agents
        const ids = discussionAgents.map((a) => a.id);
        setRespondingAgentIds(ids);
      } else {
        setRespondingAgentIds([]);
      }
    }, [isSending, speakingAgentId, discussionAgents]);

    // ─── Teacher Controls ─────────────────────────────────────────────
    const handleNewTopic = useCallback(() => {
      setMessages([]);
      setInput('');
    }, []);

    // Auto-scroll
    useEffect(() => {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages.length]);

    // Cleanup
    useEffect(() => {
      return () => {
        abortRef.current?.abort();
      };
    }, []);

    const getAgent = useCallback(
      (agentId?: string): MAICAgent | null => {
        if (!agentId) return null;
        return discussionAgents.find((a) => a.id === agentId) || null;
      },
      [discussionAgents],
    );

    const handleSend = useCallback(async () => {
      const trimmed = input.trim();
      if (!trimmed || isSending || !accessToken) return;

      setInput('');
      setIsSending(true);

      const userMsg: DiscussionMessage = {
        id: `disc-${Date.now()}`,
        role: 'user',
        content: trimmed,
      };
      setMessages((prev) => [...prev, userMsg]);

      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      await streamMAIC({
        url: '/api/v1/teacher/maic/chat/',
        body: {
          message: trimmed,
          sessionType,
          topic,
          agentIds,
        },
        token: accessToken,
        signal: controller.signal,
        onEvent: (event: MAICSSEEvent) => {
          if (event.type === 'chat_message') {
            const data = event.data as { content: string; agentId?: string };
            const agentMsg: DiscussionMessage = {
              id: `disc-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
              role: 'agent',
              agentId: data.agentId || event.agentId,
              content: data.content,
            };
            setMessages((prev) => [...prev, agentMsg]);
            setSpeakingAgentId(null);
          } else if (event.type === 'agent_speaking') {
            const data = event.data as { agentId: string };
            setSpeakingAgentId(data.agentId);
          }
        },
        onError: (err) => {
          const errorMsg: DiscussionMessage = {
            id: `disc-err-${Date.now()}`,
            role: 'agent',
            content: `Error: ${err.message}`,
          };
          setMessages((prev) => [...prev, errorMsg]);
        },
        onDone: () => {
          setIsSending(false);
          setSpeakingAgentId(null);
        },
      });

      setIsSending(false);
    }, [input, isSending, accessToken, sessionType, topic, agentIds]);

    const handleKeyDown = useCallback(
      (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
          e.preventDefault();
          handleSend();
        }
      },
      [handleSend],
    );

    return (
      <div
        className="absolute inset-0 z-40 flex flex-col bg-black/40 backdrop-blur-sm"
        role="dialog"
        aria-label={SESSION_LABELS[sessionType]}
      >
        <div className="flex flex-col max-w-3xl w-full mx-auto my-4 bg-white rounded-xl shadow-2xl overflow-hidden flex-1 min-h-0">
          {/* Header */}
          <div className="shrink-0 flex items-center justify-between px-5 py-3 border-b border-gray-100 bg-gray-50">
            <div>
              <h3 className="text-sm font-semibold text-gray-900">
                {SESSION_LABELS[sessionType]}
              </h3>
              <p className="text-xs text-gray-500 mt-0.5">{topic}</p>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={handleNewTopic}
                className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-gray-500 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                title="Clear and start new topic"
              >
                <RotateCcw className="h-3 w-3" />
                <span className="hidden sm:inline">New Topic</span>
              </button>
              <button
                type="button"
                onClick={onClose}
                className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-red-500 hover:text-red-700 hover:bg-red-50 transition-colors"
                aria-label="End discussion"
              >
                <X className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">End</span>
              </button>
            </div>
          </div>

          {/* Agent avatars row */}
          <div className="shrink-0 flex items-center justify-center gap-3 px-5 py-3 border-b border-gray-50">
            {discussionAgents.map((agent) => {
              const isSpeaking = speakingAgentId === agent.id;
              const isResponding = respondingAgentIds.includes(agent.id) && !speakingAgentId;
              return (
                <div key={agent.id} className="flex flex-col items-center gap-1 relative">
                  <AgentAvatar agent={agent} isSpeaking={isSpeaking} size="md" />
                  {isResponding && !isSpeaking && (
                    <div className="absolute -top-0.5 -right-0.5 h-3 w-3 rounded-full bg-amber-400 border-2 border-white animate-pulse" />
                  )}
                  <span
                    className={cn(
                      'text-[10px] font-medium',
                      isSpeaking
                        ? 'text-gray-900'
                        : isResponding
                          ? 'text-amber-600'
                          : 'text-gray-400',
                    )}
                  >
                    {isSpeaking ? 'Speaking...' : isResponding ? 'Thinking...' : agent.name}
                  </span>
                </div>
              );
            })}
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-5 py-4 space-y-3" aria-live="polite">
            {messages.length === 0 && (
              <div className="mt-4 space-y-4">
                <p className="text-sm text-gray-400 text-center">
                  Start the discussion or pick a suggested topic below.
                </p>

                {/* Suggested topics */}
                {suggestedTopics.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide px-1">
                      Suggested Topics
                    </p>
                    <div className="grid gap-1.5">
                      {suggestedTopics.map((t, idx) => (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => {
                            setInput(t);
                          }}
                          className="flex items-start gap-2 text-left px-3 py-2.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 hover:border-gray-300 transition-colors group"
                        >
                          <MessageCircle className="h-3.5 w-3.5 text-gray-400 group-hover:text-primary-500 mt-0.5 shrink-0" />
                          <span className="text-xs text-gray-600 group-hover:text-gray-900 leading-relaxed">
                            {t}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {messages.map((msg) => {
              const agent = getAgent(msg.agentId);
              const isUser = msg.role === 'user';
              const bubbleColor = msg.agentId
                ? agentColorMap.get(msg.agentId) || 'bg-gray-50 border-gray-200 text-gray-800'
                : '';

              return (
                <div
                  key={msg.id}
                  className={cn('flex gap-2', isUser ? 'flex-row-reverse' : 'flex-row')}
                >
                  {!isUser && agent && (
                    <div className="shrink-0 mt-0.5">
                      <AgentAvatar agent={agent} size="sm" />
                    </div>
                  )}

                  <div className="max-w-[75%] min-w-0">
                    {!isUser && agent && (
                      <p
                        className="text-xs font-medium mb-0.5 px-1"
                        style={{ color: agent.color }}
                      >
                        {agent.name}
                      </p>
                    )}
                    <div
                      className={cn(
                        'rounded-2xl px-3 py-2 text-sm leading-relaxed border',
                        isUser
                          ? 'bg-primary-600 text-white border-primary-600 rounded-br-md'
                          : cn(bubbleColor || 'bg-gray-100 text-gray-800 border-gray-200', 'rounded-bl-md'),
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

            {/* Thinking indicator */}
            {isSending && (
              <div className="flex gap-2 items-center">
                {speakingAgentId ? (
                  <div className="shrink-0">
                    {(() => {
                      const agent = getAgent(speakingAgentId);
                      return agent ? <AgentAvatar agent={agent} isSpeaking size="sm" /> : null;
                    })()}
                  </div>
                ) : (
                  <div className="h-8 w-8 rounded-full bg-gray-200 flex items-center justify-center text-xs text-gray-500">
                    AI
                  </div>
                )}
                <div className="bg-gray-100 rounded-2xl rounded-bl-md px-4 py-2.5 border border-gray-200">
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
          <div className="shrink-0 px-5 py-3 border-t border-gray-100 bg-gray-50">
            <div className="flex items-end gap-2">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Join the discussion..."
                rows={1}
                disabled={isSending}
                className={cn(
                  'flex-1 resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm bg-white',
                  'placeholder:text-gray-400',
                  'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                  'max-h-20 overflow-y-auto',
                  'disabled:opacity-50',
                )}
                aria-label="Discussion message input"
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
    );
  },
);
