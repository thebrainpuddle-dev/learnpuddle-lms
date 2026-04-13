// src/pages/student/StudentChatPage.tsx
//
// Simplified chat interface for a single AI chatbot. Messages are persisted
// in sessionStorage (per chatbot) — no server-side conversation sidebar needed.

import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Bot, ChevronLeft, Loader2 } from 'lucide-react';
import { usePageTitle } from '../../hooks/usePageTitle';
import { chatbotStudentApi } from '../../services/openmaicService';
import { ChatbotChat } from '../../components/maic/ChatbotChat';
import type { AIChatbot } from '../../types/chatbot';

// ─── Main Component ───────────────────────────────────────────────────────────

export function StudentChatPage() {
  const { id: chatbotId } = useParams<{ id: string }>();
  const navigate = useNavigate();

  // Fetch chatbot detail
  const { data: chatbot, isLoading: chatbotLoading } = useQuery({
    queryKey: ['student-chatbot-detail', chatbotId],
    queryFn: async () => {
      const res = await chatbotStudentApi.list();
      return res.data.find((c: AIChatbot) => c.id === chatbotId) ?? null;
    },
    enabled: !!chatbotId,
  });

  usePageTitle(chatbot?.name ?? 'AI Chatbot');

  if (!chatbotId) return null;

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] overflow-hidden rounded-xl border border-gray-200/80 bg-white shadow-sm">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100 bg-white">
        <button
          type="button"
          onClick={() => navigate('/student/chatbots')}
          className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          All Chatbots
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
          <span className="text-sm text-gray-400 ml-2">Chatbot not found</span>
        )}
      </div>

      {/* ── Chat Area ───────────────────────────────────────────────── */}
      <div className="flex-1 min-h-0">
        {chatbot ? (
          <ChatbotChat
            chatbotId={chatbotId}
            welcomeMessage={chatbot.welcome_message || `Hi! I'm ${chatbot.name}. How can I help you?`}
          />
        ) : chatbotLoading ? (
          <div className="flex-1 flex items-center justify-center h-full">
            <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center h-full text-gray-400">
            Chatbot not found.
          </div>
        )}
      </div>
    </div>
  );
}
