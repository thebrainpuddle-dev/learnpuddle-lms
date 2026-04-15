// src/pages/student/StudentChatPage.tsx
//
// Chat interface for a single AI chatbot. Uses the detail endpoint to fetch
// the chatbot, and shows a conversation history sidebar so students can
// resume past conversations.

import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Bot, ChevronLeft, Loader2, MessageSquare, Plus, Clock, PanelLeftClose, PanelLeft,
} from 'lucide-react';
import { usePageTitle } from '../../hooks/usePageTitle';
import { chatbotStudentApi } from '../../services/openmaicService';
import { ChatbotChat } from '../../components/maic/ChatbotChat';
import type { ConversationListItem } from '../../types/chatbot';
import { cn } from '../../lib/utils';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHrs = Math.floor(diffMins / 60);
  if (diffHrs < 24) return `${diffHrs}h ago`;
  const diffDays = Math.floor(diffHrs / 24);
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

// ─── Main Component ───────────────────────────────────────────────────────────

export function StudentChatPage() {
  const { id: chatbotId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);

  // Fetch chatbot detail via dedicated endpoint
  const { data: chatbot, isLoading: chatbotLoading } = useQuery({
    queryKey: ['student-chatbot-detail', chatbotId],
    queryFn: async () => {
      const res = await chatbotStudentApi.detail(chatbotId!);
      return res.data;
    },
    enabled: !!chatbotId,
  });

  // Fetch conversation history
  const { data: conversations = [], isLoading: convsLoading } = useQuery({
    queryKey: ['student-chatbot-conversations', chatbotId],
    queryFn: async () => {
      const res = await chatbotStudentApi.conversations(chatbotId!);
      return res.data as ConversationListItem[];
    },
    enabled: !!chatbotId,
  });

  usePageTitle(chatbot?.name ?? 'AI Tutor');

  // When a new conversation is created by the chat component, refresh the list
  const handleConversationCreated = useCallback(
    (convId: string) => {
      setActiveConversationId(convId);
      queryClient.invalidateQueries({ queryKey: ['student-chatbot-conversations', chatbotId] });
    },
    [chatbotId, queryClient],
  );

  // Start a new conversation (clear active selection)
  const handleNewConversation = useCallback(() => {
    setActiveConversationId(null);
  }, []);

  // Select an existing conversation
  const handleSelectConversation = useCallback((convId: string) => {
    setActiveConversationId(convId);
  }, []);

  if (!chatbotId) return null;

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden rounded-xl border border-gray-200/80 bg-white shadow-sm">
      {/* ── Conversation History Sidebar ────────────────────────────── */}
      {sidebarOpen && (
        <div className="w-64 flex-shrink-0 flex flex-col border-r border-gray-100 bg-gray-50/50">
          {/* Sidebar Header */}
          <div className="flex items-center justify-between px-3 py-3 border-b border-gray-100">
            <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
              Conversations
            </h3>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={handleNewConversation}
                className={cn(
                  'inline-flex items-center justify-center h-7 w-7 rounded-lg',
                  'text-gray-400 hover:text-indigo-600 hover:bg-indigo-50',
                  'transition-colors duration-150',
                )}
                title="New conversation"
              >
                <Plus className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setSidebarOpen(false)}
                className={cn(
                  'inline-flex items-center justify-center h-7 w-7 rounded-lg',
                  'text-gray-400 hover:text-gray-600 hover:bg-gray-100',
                  'transition-colors duration-150',
                )}
                title="Close sidebar"
              >
                <PanelLeftClose className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Conversation List */}
          <div className="flex-1 overflow-y-auto py-1.5">
            {convsLoading ? (
              <div className="flex justify-center py-8">
                <Loader2 className="h-5 w-5 animate-spin text-gray-300" />
              </div>
            ) : conversations.length === 0 ? (
              <div className="px-3 py-8 text-center">
                <MessageSquare className="mx-auto h-8 w-8 text-gray-300" />
                <p className="mt-2 text-xs text-gray-400">
                  No conversations yet. Start chatting below!
                </p>
              </div>
            ) : (
              conversations.map((conv) => {
                const isActive = conv.id === activeConversationId;
                return (
                  <button
                    key={conv.id}
                    type="button"
                    onClick={() => handleSelectConversation(conv.id)}
                    className={cn(
                      'w-full text-left px-3 py-2.5 mx-1.5 mb-0.5 rounded-lg transition-all duration-150',
                      'hover:bg-white hover:shadow-sm',
                      isActive
                        ? 'bg-white shadow-sm border border-indigo-100'
                        : 'border border-transparent',
                    )}
                    style={{ width: 'calc(100% - 0.75rem)' }}
                  >
                    <p
                      className={cn(
                        'text-sm truncate leading-5',
                        isActive ? 'font-medium text-gray-900' : 'text-gray-700',
                      )}
                    >
                      {conv.title || 'Untitled conversation'}
                    </p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <span className="inline-flex items-center gap-1 text-[10px] text-gray-400">
                        <Clock className="h-2.5 w-2.5" />
                        {formatRelativeTime(conv.last_message_at)}
                      </span>
                      <span className="text-[10px] text-gray-300">
                        {conv.message_count} msg{conv.message_count !== 1 ? 's' : ''}
                      </span>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* ── Main Chat Panel ────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100 bg-white">
          {!sidebarOpen && (
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className={cn(
                'inline-flex items-center justify-center h-7 w-7 rounded-lg',
                'text-gray-400 hover:text-gray-600 hover:bg-gray-100',
                'transition-colors duration-150',
              )}
              title="Show conversations"
            >
              <PanelLeft className="h-4 w-4" />
            </button>
          )}

          <button
            type="button"
            onClick={() => navigate('/student/chatbots')}
            className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            All Tutors
          </button>

          {chatbotLoading ? (
            <div className="flex items-center gap-2 ml-2">
              <Loader2 className="h-4 w-4 animate-spin text-gray-400" />
              <span className="text-sm text-gray-400">Loading...</span>
            </div>
          ) : chatbot ? (
            <div className="flex items-center gap-2.5 ml-2">
              <div className="h-7 w-7 rounded-lg bg-gradient-to-br from-indigo-500 to-indigo-600 flex items-center justify-center shadow-sm shadow-indigo-200">
                <Bot className="h-3.5 w-3.5 text-white" />
              </div>
              <h2 className="text-sm font-semibold text-gray-900 truncate">
                {chatbot.name}
              </h2>
            </div>
          ) : (
            <span className="text-sm text-gray-400 ml-2">Tutor not found</span>
          )}
        </div>

        {/* Chat Area */}
        <div className="flex-1 min-h-0">
          {chatbot ? (
            <ChatbotChat
              key={activeConversationId ?? 'new'}
              chatbotId={chatbotId}
              conversationId={activeConversationId}
              welcomeMessage={chatbot.welcome_message || `Hi! I'm ${chatbot.name}. How can I help you?`}
              onConversationCreated={handleConversationCreated}
            />
          ) : chatbotLoading ? (
            <div className="flex-1 flex items-center justify-center h-full">
              <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
            </div>
          ) : (
            <div className="flex-1 flex items-center justify-center h-full text-gray-400">
              Tutor not found.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
