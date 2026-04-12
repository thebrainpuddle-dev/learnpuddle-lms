// src/pages/student/StudentChatbotsPage.tsx
//
// Browse page for student-facing AI chatbots. Displays a searchable grid of
// read-only ChatbotCards; clicking one navigates to the chat interface.

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Bot, Search } from 'lucide-react';
import { usePageTitle } from '../../hooks/usePageTitle';
import { chatbotStudentApi } from '../../services/openmaicService';
import { ChatbotCard } from '../../components/maic/ChatbotCard';
import type { AIChatbot } from '../../types/chatbot';

// ─── Main Component ───────────────────────────────────────────────────────────

export function StudentChatbotsPage() {
  usePageTitle('AI Chatbots');
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data: chatbots = [], isLoading } = useQuery({
    queryKey: ['student-chatbots'],
    queryFn: async () => {
      const res = await chatbotStudentApi.list();
      return res.data;
    },
  });

  // Client-side name filter
  const filtered = search.trim()
    ? chatbots.filter((c: AIChatbot) =>
        c.name.toLowerCase().includes(search.trim().toLowerCase()),
      )
    : chatbots;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">AI Chatbots</h1>
        <p className="mt-1 text-sm text-gray-500">
          Browse AI chatbots created by your teachers and start a conversation.
        </p>
      </div>

      {/* Search */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1 max-w-sm">
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
            <Search className="h-4 w-4 text-gray-400" />
          </div>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search chatbots..."
            className="w-full pl-9 pr-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>
      </div>

      {/* Grid */}
      {isLoading ? (
        <div className="flex justify-center py-16">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600" />
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16">
          <Bot className="mx-auto h-12 w-12 text-gray-300" />
          <h3 className="mt-4 text-lg font-medium text-gray-900">
            {search.trim() ? 'No matching chatbots' : 'No chatbots available'}
          </h3>
          <p className="mt-2 text-sm text-gray-500">
            {search.trim()
              ? 'Try a different search term.'
              : 'Check back later for new AI chatbots from your teachers.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((chatbot: AIChatbot) => (
            <div
              key={chatbot.id}
              role="button"
              tabIndex={0}
              className="cursor-pointer"
              onClick={() => navigate(`/student/chatbots/${chatbot.id}`)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  navigate(`/student/chatbots/${chatbot.id}`);
                }
              }}
            >
              <ChatbotCard chatbot={chatbot} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
