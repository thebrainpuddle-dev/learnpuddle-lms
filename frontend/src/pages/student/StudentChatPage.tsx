// src/pages/student/StudentChatPage.tsx
//
// Full chat interface for a single AI chatbot. Left sidebar lists the
// student's conversations; main area renders the ChatbotChat streaming
// component. A "New Chat" button creates a fresh conversation.

import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Bot, Plus, MessageCircle, ChevronLeft, Loader2 } from 'lucide-react';
import { usePageTitle } from '../../hooks/usePageTitle';
import { chatbotStudentApi } from '../../services/openmaicService';
import { ChatbotChat } from '../../components/maic/ChatbotChat';
import type { AIChatbot, ConversationListItem } from '../../types/chatbot';
import { cn } from '../../lib/utils';

// ─── Persona Badge Config ────────────────────────────────────────────────────

const presetBadge: Record<string, { label: string; classes: string }> = {
  tutor: { label: 'Tutor', classes: 'bg-blue-100 text-blue-700' },
  reference: { label: 'Reference', classes: 'bg-purple-100 text-purple-700' },
  open: { label: 'Open', classes: 'bg-green-100 text-green-700' },
};

// ─── Main Component ───────────────────────────────────────────────────────────

export function StudentChatPage() {
  const { id: chatbotId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Fetch chatbot detail — the backend has no dedicated student detail endpoint
  // (see backend/apps/courses/chatbot_urls.py student_urlpatterns), so we fetch
  // the full list and filter client-side. Replace with a direct detail call if/when
  // the backend adds GET /v1/student/chatbots/<id>/.
  const { data: chatbot, isLoading: chatbotLoading } = useQuery({
    queryKey: ['student-chatbot-detail', chatbotId],
    queryFn: async () => {
      const res = await chatbotStudentApi.list();
      return res.data.find((c: AIChatbot) => c.id === chatbotId) ?? null;
    },
    enabled: !!chatbotId,
  });

  usePageTitle(chatbot?.name ?? 'AI Chatbot');

  // Fetch conversations
  const {
    data: conversations = [],
    isLoading: convsLoading,
    refetch: refetchConversations,
  } = useQuery({
    queryKey: ['student-chatbot-conversations', chatbotId],
    queryFn: async () => {
      if (!chatbotId) return [];
      const res = await chatbotStudentApi.conversations(chatbotId);
      // Map to ConversationListItem shape (omit messages array)
      return res.data.map(
        (c): ConversationListItem => ({
          id: c.id,
          title: c.title,
          student_name: c.student_name,
          message_count: c.message_count,
          is_flagged: c.is_flagged,
          started_at: c.started_at,
          last_message_at: c.last_message_at,
        }),
      );
    },
    enabled: !!chatbotId,
  });

  // Select the most recent conversation on first load
  useEffect(() => {
    if (!activeConvId && conversations.length > 0) {
      setActiveConvId(conversations[0].id);
    }
  }, [conversations, activeConvId]);

  // Callback when a new conversation is created from the chat component
  const handleConversationCreated = useCallback(
    (newId: string) => {
      setActiveConvId(newId);
      refetchConversations();
    },
    [refetchConversations],
  );

  // Start a new (empty) conversation
  const handleNewChat = () => {
    setActiveConvId(null);
  };

  if (!chatbotId) return null;

  const badge = presetBadge[chatbot?.persona_preset ?? 'open'] ?? presetBadge.open;

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden rounded-xl border border-gray-200 bg-white">
      {/* ── Left Sidebar ────────────────────────────────────────────────── */}
      <aside
        className={cn(
          'flex flex-col border-r border-gray-200 bg-gray-50 transition-all duration-200',
          sidebarOpen ? 'w-72' : 'w-0 overflow-hidden',
        )}
      >
        {/* Back link + chatbot name */}
        <div className="p-4 border-b border-gray-200">
          <button
            type="button"
            onClick={() => navigate('/student/chatbots')}
            className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 mb-3"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            All Chatbots
          </button>

          {chatbotLoading ? (
            <div className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
              <span className="text-sm text-gray-400">Loading...</span>
            </div>
          ) : chatbot ? (
            <div>
              <div className="flex items-center gap-2 mb-1">
                <Bot className="h-5 w-5 text-indigo-500 shrink-0" />
                <h2 className="text-sm font-semibold text-gray-900 truncate">
                  {chatbot.name}
                </h2>
              </div>
              <span
                className={cn(
                  'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                  badge.classes,
                )}
              >
                {badge.label}
              </span>
            </div>
          ) : (
            <p className="text-sm text-gray-400">Chatbot not found</p>
          )}
        </div>

        {/* New Chat button */}
        <div className="p-3">
          <button
            type="button"
            onClick={handleNewChat}
            className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            New Chat
          </button>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto px-2 pb-3">
          {convsLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-gray-400" />
            </div>
          ) : conversations.length === 0 ? (
            <p className="text-center text-xs text-gray-400 py-8">
              No conversations yet
            </p>
          ) : (
            <ul className="space-y-1">
              {conversations.map((conv) => (
                <li key={conv.id}>
                  <button
                    type="button"
                    onClick={() => setActiveConvId(conv.id)}
                    className={cn(
                      'w-full text-left rounded-lg px-3 py-2 text-sm transition-colors',
                      activeConvId === conv.id
                        ? 'bg-indigo-50 text-indigo-700 font-medium'
                        : 'text-gray-700 hover:bg-gray-100',
                    )}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <MessageCircle className="h-3.5 w-3.5 shrink-0 text-gray-400" />
                      <span className="truncate">{conv.title || 'Untitled'}</span>
                    </div>
                    <div className="mt-0.5 text-[11px] text-gray-400 pl-5">
                      {conv.message_count} message{conv.message_count !== 1 ? 's' : ''}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </aside>

      {/* ── Sidebar Toggle (visible when collapsed) ──────────────────── */}
      <button
        type="button"
        onClick={() => setSidebarOpen((o) => !o)}
        className="hidden sm:flex items-center justify-center w-6 hover:bg-gray-100 transition-colors border-r border-gray-200 text-gray-400 hover:text-gray-600"
        aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
      >
        <ChevronLeft
          className={cn(
            'h-4 w-4 transition-transform',
            !sidebarOpen && 'rotate-180',
          )}
        />
      </button>

      {/* ── Main Chat Area ──────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0">
        {chatbot ? (
          <ChatbotChat
            chatbotId={chatbotId}
            conversationId={activeConvId}
            welcomeMessage={chatbot.welcome_message || `Hi! I'm ${chatbot.name}. How can I help you?`}
            onConversationCreated={handleConversationCreated}
          />
        ) : chatbotLoading ? (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            Chatbot not found.
          </div>
        )}
      </main>
    </div>
  );
}
