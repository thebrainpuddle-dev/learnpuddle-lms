// src/components/maic/ChatPanel.tsx
//
// Right sidebar panel for multi-agent classroom chat. Displays conversation
// history with agent-colored bubbles, role badges, relative timestamps,
// typing indicator, and allows user participation via SSE streaming.
// Uses ConversationContainer for auto-scrolling and PromptInput for enhanced
// input with slash commands and suggestions.

import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { BookOpen, MessageCircle } from 'lucide-react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useAuthStore } from '../../stores/authStore';
import { streamMAIC } from '../../lib/maicSSE';
import { updateClassroomChat } from '../../lib/maicDb';
import {
  hydrateChatFromSession,
  persistChatToSession,
  serializeChatHistoryForBackend,
} from '../../lib/maicChatSession';
import type { MAICChatMessage, MAICPlayerRole, MAICSSEEvent, MAICAgent } from '../../types/maic';
import { AgentAvatar } from './AgentAvatar';
import { StreamMarkdown } from './StreamMarkdown';
import { PromptInput } from './PromptInput';
import { ConversationContainer } from './ConversationContainer';
import { cn } from '../../lib/utils';
import { maicChatUrl } from '../../lib/maic/endpoints';
import {
  ChainOfThought,
  ChainOfThoughtTrigger,
  ChainOfThoughtContent,
  ChainOfThoughtStep,
} from './ai-elements/ChainOfThought';
import { CodeBlock } from './ai-elements/CodeBlock';

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

/** Check if content contains a fenced code block. */
function hasCodeBlock(content: string): boolean {
  return /```(\w+)?\n[\s\S]*?```/.test(content);
}

/** Split content into segments: text and code blocks. */
function splitCodeBlocks(content: string): Array<{ type: 'text' | 'code'; value: string; language?: string }> {
  const segments: Array<{ type: 'text' | 'code'; value: string; language?: string }> = [];
  const regex = /```(\w+)?\n([\s\S]*?)```/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: 'text', value: content.slice(lastIndex, match.index) });
    }
    segments.push({ type: 'code', value: match[2], language: match[1] });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < content.length) {
    segments.push({ type: 'text', value: content.slice(lastIndex) });
  }

  return segments;
}

/** Derive a subtle background tint from an agent color for message bubbles. */
function agentBubbleBg(color: string): string {
  // Append low opacity — works for hex colors
  return `${color}0D`; // ~5% opacity
}

export const ChatPanel = React.memo<ChatPanelProps>(function ChatPanel({ role, classroomId }) {
  const chatMessages = useMAICStageStore((s) => s.chatMessages);
  const addChatMessage = useMAICStageStore((s) => s.addChatMessage);
  const setChatMessages = useMAICStageStore((s) => s.setChatMessages);
  const agents = useMAICStageStore((s) => s.agents);
  const scenes = useMAICStageStore((s) => s.scenes);
  const currentSceneIndex = useMAICStageStore((s) => s.currentSceneIndex);
  const currentSlideIndex = useMAICStageStore((s) => s.currentSlideIndex);
  const userNotes = useMAICStageStore((s) => s.notes);
  const addUserNote = useMAICStageStore((s) => s.addNote);
  const accessToken = useAuthStore((s) => s.accessToken);

  const [activeTab, setActiveTab] = useState<ChatTab>('chat');
  const [input, setInput] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [thinkingAgentId, setThinkingAgentId] = useState<string | null>(null);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);
  const [reasoningSteps, setReasoningSteps] = useState<string[]>([]);
  const [showReasoning, setShowReasoning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Build lecture notes per scene: auto-generated speaker scripts +
  // user-added notes that were saved against slides in this scene.
  // A scene shows up even if it has no auto notes as long as the user
  // added a note against one of its slides.
  const lectureNotes = useMemo(() => {
    return scenes.map((scene, idx) => {
      const speechTexts = (scene.actions || [])
        .filter((a) => a.type === 'speech' && (a as { text?: string }).text)
        .map((a) => (a as { text: string }).text);
      const sceneUserNotes = userNotes
        .filter((n) => n.sceneIdx === idx)
        .sort((a, b) => a.timestamp - b.timestamp);
      return {
        sceneIndex: idx,
        title: scene.title,
        notes: speechTexts,
        userNotes: sceneUserNotes,
        isCurrent: idx === currentSceneIndex,
      };
    }).filter((s) => s.notes.length > 0 || s.userNotes.length > 0);
  }, [scenes, currentSceneIndex, userNotes]);

  // User-note composer — writes to the current scene + slide.
  const [noteDraft, setNoteDraft] = useState('');
  const handleAddNote = useCallback(() => {
    const trimmed = noteDraft.trim();
    if (!trimmed) return;
    addUserNote({
      sceneIdx: currentSceneIndex,
      slideIdx: currentSlideIndex,
      text: trimmed,
      timestamp: Date.now(),
    });
    setNoteDraft('');
  }, [noteDraft, currentSceneIndex, currentSlideIndex, addUserNote]);

  // Hydrate chat history from sessionStorage on mount / classroom
  // switch. If the store already has messages (e.g., IndexedDB path
  // populated it first) skip — the store wins. Ref guards against
  // re-hydrating after we've written new messages into the store.
  const hydratedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!classroomId) return;
    if (hydratedRef.current === classroomId) return;
    hydratedRef.current = classroomId;
    const persisted = hydrateChatFromSession(classroomId);
    if (persisted.length > 0 && chatMessages.length === 0) {
      setChatMessages(persisted);
    }
    // Intentionally omit chatMessages from deps — we only want to
    // hydrate once per classroomId, not every time messages change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classroomId, setChatMessages]);

  // Persist chat history to sessionStorage (session-scoped) and
  // IndexedDB (classroom-scoped) whenever messages change. Session
  // storage gives us instant refresh-resilient hydration; IndexedDB
  // remains the classroom-level durable record.
  useEffect(() => {
    if (!classroomId) return;
    if (chatMessages.length > 0) {
      persistChatToSession(classroomId, chatMessages);
      updateClassroomChat(classroomId, chatMessages).catch(() => {});
    }
  }, [chatMessages, classroomId]);

  // Resolve agent by id
  const getAgent = useCallback(
    (agentId?: string): MAICAgent | null => {
      if (!agentId) return null;
      return agents.find((a) => a.id === agentId) || null;
    },
    [agents],
  );

  // Context-aware suggestion pills based on current scene
  const suggestions = useMemo(() => {
    const currentScene = scenes[currentSceneIndex];
    const base = ['Explain this concept', 'Quiz me'];
    if (currentScene?.title) {
      base.unshift(`Summarize "${currentScene.title}"`);
    }
    if (chatMessages.length === 0) {
      base.push('Give me an example');
    }
    return base.slice(0, 4);
  }, [scenes, currentSceneIndex, chatMessages.length]);

  const handleSuggestionClick = useCallback((suggestion: string) => {
    setInput(suggestion);
  }, []);

  // Stop ongoing generation
  const handleStop = useCallback(() => {
    abortRef.current?.abort();
    setIsSending(false);
    setThinkingAgentId(null);
    setStreamingMessageId(null);
  }, []);

  // Send a message (accepts text directly from PromptInput)
  const handleSubmit = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || isSending || !accessToken) return;

    setInput('');
    setIsSending(true);
    setReasoningSteps([]);
    setShowReasoning(false);

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

    const endpoint = maicChatUrl(role);

    // Snapshot history BEFORE adding the user message above. The user's
    // current turn is already in `trimmed` + addressed as `message`; we
    // want the prior turns as context. slice(0, -1) drops the just-added
    // user message so the backend doesn't see it twice.
    const history = serializeChatHistoryForBackend(chatMessages.slice(0, -1));

    // Track whether the stream produced a real assistant message. If it
    // errors after a partial payload arrived, keep that payload — don't
    // replace it with an error bubble.
    let assistantArrived = false;

    await streamMAIC({
      url: endpoint,
      body: {
        classroomId,
        message: trimmed,
        history,
      },
      token: accessToken,
      signal: controller.signal,
      onEvent: (event: MAICSSEEvent) => {
        if (event.type === 'chat_message') {
          setThinkingAgentId(null);
          const data = event.data as { content: string; agentId?: string; agentName?: string };
          const msgId = `msg-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
          const assistantMsg: MAICChatMessage = {
            id: msgId,
            role: 'assistant',
            agentId: data.agentId || event.agentId,
            agentName: data.agentName,
            content: data.content,
            timestamp: Date.now(),
          };
          setStreamingMessageId(msgId);
          addChatMessage(assistantMsg);
          assistantArrived = true;
        } else if (event.type === 'agent_thinking' || event.type === 'agent_speaking') {
          const data = event.data as { agentId?: string; step?: string };
          setThinkingAgentId(data.agentId || event.agentId || null);
          if (data.step) {
            setShowReasoning(true);
            setReasoningSteps((prev) => [...prev, data.step as string]);
          }
        }
      },
      onError: (err) => {
        // Keep any partial assistant message already rendered; append a
        // visible error chip below so the user knows something went wrong
        // without losing the response.
        const errorMsg: MAICChatMessage = {
          id: `msg-err-${Date.now()}`,
          role: 'system',
          content: assistantArrived
            ? `Connection dropped: ${err.message}`
            : `Couldn't reach the tutor: ${err.message}`,
          timestamp: Date.now(),
        };
        addChatMessage(errorMsg);
      },
      onDone: () => {
        setIsSending(false);
        setThinkingAgentId(null);
        // Only clear the streaming flag if we actually received an
        // assistant message. If the stream ended before any chat_message
        // event, leave the thinking indicator cleared but keep the
        // streamingMessageId null (nothing was mid-stream).
        setStreamingMessageId(null);
      },
    });

    setIsSending(false);
  }, [isSending, accessToken, role, classroomId, addChatMessage, chatMessages]);

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

      {/* Lecture Notes Tab (auto-generated speaker scripts + user notes) */}
      {activeTab === 'notes' && (
        <div className="flex-1 flex flex-col min-h-0">
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
                      <div key={`lect-${ni}`} className="text-xs text-gray-600">
                        <StreamMarkdown
                          content={note}
                          className="text-xs leading-relaxed"
                        />
                      </div>
                    ))}
                  </div>
                  {section.userNotes.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-100 space-y-1.5">
                      {section.userNotes.map((un, ui) => (
                        <div
                          key={`user-${ui}`}
                          className="text-xs text-amber-900 bg-amber-50 border border-amber-200 rounded-md px-2 py-1.5"
                        >
                          <div className="flex items-center gap-1.5 mb-0.5">
                            <span className="text-[9px] font-semibold text-amber-700 uppercase tracking-wide">My note</span>
                            <span className="text-[9px] text-amber-400 tabular-nums">
                              Slide {un.slideIdx + 1}
                            </span>
                          </div>
                          <p className="leading-relaxed">{un.text}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Add note composer — ties to current slide */}
          <div className="shrink-0 px-4 py-3 border-t border-gray-100 bg-white">
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={noteDraft}
                onChange={(e) => setNoteDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    e.stopPropagation();
                    handleAddNote();
                  }
                }}
                placeholder="Add a note for this slide..."
                className="flex-1 text-xs px-3 py-2 bg-gray-50 border border-gray-200 rounded-lg placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-400/50 focus:border-transparent"
              />
              <button
                type="button"
                onClick={handleAddNote}
                disabled={!noteDraft.trim()}
                className={cn(
                  'shrink-0 h-8 px-3 rounded-lg text-xs font-medium transition-colors',
                  noteDraft.trim()
                    ? 'bg-amber-500 text-white hover:bg-amber-600'
                    : 'bg-gray-100 text-gray-300 cursor-not-allowed',
                )}
                title="Add note"
              >
                Add
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Chat Messages Tab — wrapped in ConversationContainer for auto-scroll */}
      <ConversationContainer
        className={cn(activeTab !== 'chat' && 'hidden')}
        autoScroll
        showScrollToBottom
      >
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
              data-testid={isUser ? 'chat-user-message' : 'chat-agent-message'}
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
                  {isUser ? (
                    msg.content
                  ) : hasCodeBlock(msg.content) && msg.id !== streamingMessageId ? (
                    splitCodeBlocks(msg.content).map((seg, si) =>
                      seg.type === 'code' ? (
                        <CodeBlock
                          key={si}
                          code={seg.value}
                          language={seg.language}
                          showLineNumbers={seg.value.split('\n').length > 3}
                          className="my-2 -mx-1"
                        />
                      ) : (
                        <StreamMarkdown
                          key={si}
                          content={seg.value}
                          className="text-sm leading-relaxed"
                        />
                      ),
                    )
                  ) : (
                    <StreamMarkdown
                      content={msg.content}
                      isStreaming={msg.id === streamingMessageId}
                      className="text-sm leading-relaxed"
                    />
                  )}
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

        {/* Chain of Thought reasoning display */}
        {showReasoning && reasoningSteps.length > 0 && (
          <div className="px-1">
            <ChainOfThought defaultOpen={true}>
              <ChainOfThoughtTrigger>
                {thinkingAgentId
                  ? `${getAgent(thinkingAgentId)?.name ?? 'Agent'}'s reasoning`
                  : 'AI reasoning'}
              </ChainOfThoughtTrigger>
              <ChainOfThoughtContent>
                {reasoningSteps.map((step, i) => (
                  <ChainOfThoughtStep
                    key={i}
                    number={i + 1}
                    type={i === reasoningSteps.length - 1 && isSending ? 'analyzing' : 'completed'}
                  >
                    {step}
                  </ChainOfThoughtStep>
                ))}
              </ChainOfThoughtContent>
            </ChainOfThought>
          </div>
        )}

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
      </ConversationContainer>

      {/* Enhanced PromptInput (chat tab only) */}
      <div
        className={cn('shrink-0 px-4 py-3 border-t border-gray-100', activeTab !== 'chat' && 'hidden')}
        data-testid="chat-input"
      >
        <PromptInput
          value={input}
          onChange={setInput}
          onSubmit={handleSubmit}
          onStop={handleStop}
          placeholder="Ask the classroom..."
          loading={isSending}
          disabled={!accessToken}
          suggestions={suggestions}
          onSuggestionClick={handleSuggestionClick}
          maxLength={2000}
          showCharCount
        />
      </div>
    </div>
  );
});
