// src/components/maic/ChatbotCard.tsx
//
// Card component for chatbot library grid. Shows name, status,
// section tags, knowledge/conversation counts, and actions.

import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Bot, Pencil, Trash2, Copy, MessageCircle, BookOpen,
} from 'lucide-react';
import type { AIChatbot } from '../../types/chatbot';
import { cn } from '../../lib/utils';

// ─── Props ───────────────────────────────────────────────────────────────────

interface Props {
  chatbot: AIChatbot;
  onDelete?: (id: string) => void;
  onClone?: (id: string) => void;
  /** Whether to show the Edit button. Defaults to true. Set to false for student views. */
  showEdit?: boolean;
}

// ─── Component ───────────────────────────────────────────────────────────────

export const ChatbotCard = React.memo<Props>(function ChatbotCard({
  chatbot,
  onDelete,
  onClone,
  showEdit = true,
}) {
  const navigate = useNavigate();

  return (
    <div
      className={cn(
        'group relative w-full text-left rounded-xl border bg-white p-5',
        'shadow-sm transition-all duration-300',
        'hover:shadow-lg hover:shadow-gray-200/50 hover:-translate-y-0.5',
        'focus-within:ring-2 focus-within:ring-indigo-500 focus-within:ring-offset-2',
        chatbot.is_active
          ? 'border-gray-200/80 hover:border-indigo-200'
          : 'border-gray-200 opacity-60',
      )}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="shrink-0 h-9 w-9 rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-600 flex items-center justify-center shadow-sm shadow-indigo-200">
            <Bot className="h-4.5 w-4.5 text-white" aria-hidden="true" />
          </div>
          <h3 className="text-base font-semibold text-gray-900 truncate group-hover:text-indigo-600 transition-colors duration-200">
            {chatbot.name}
          </h3>
        </div>

        {/* Active / Inactive indicator */}
        <span
          className={cn(
            'shrink-0 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold',
            chatbot.is_active
              ? 'bg-emerald-50 text-emerald-700'
              : 'bg-gray-100 text-gray-500',
          )}
        >
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full',
              chatbot.is_active ? 'bg-emerald-500 animate-pulse' : 'bg-gray-400',
            )}
          />
          {chatbot.is_active ? 'Active' : 'Inactive'}
        </span>
      </div>

      {/* Section tags */}
      {chatbot.sections && chatbot.sections.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {chatbot.sections.slice(0, 3).map((sec) => (
            <span
              key={sec.id}
              className="inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium bg-indigo-50/80 text-indigo-600 border border-indigo-100"
            >
              {sec.grade_short_code}-{sec.name}
            </span>
          ))}
          {chatbot.sections.length > 3 && (
            <span className="inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-medium bg-gray-50 text-gray-500 border border-gray-100">
              +{chatbot.sections.length - 3} more
            </span>
          )}
        </div>
      )}

      {/* Meta row */}
      <div className="flex items-center gap-4 text-xs text-gray-400 mb-4">
        <span className="inline-flex items-center gap-1.5">
          <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="font-medium text-gray-500">{chatbot.knowledge_count}</span>
          source{chatbot.knowledge_count !== 1 ? 's' : ''}
        </span>
        {showEdit && (
          <span className="inline-flex items-center gap-1.5">
            <MessageCircle className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="font-medium text-gray-500">{chatbot.conversation_count}</span>
            conversation{chatbot.conversation_count !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1 pt-3 border-t border-gray-100">
        {showEdit && (
          <button
            type="button"
            onClick={() => navigate(`/teacher/chatbots/${chatbot.id}`)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-indigo-600 hover:bg-indigo-50 active:bg-indigo-100 transition-all duration-200"
            aria-label={`Edit chatbot: ${chatbot.name}`}
          >
            <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
            Edit
          </button>
        )}

        {onClone && (
          <button
            type="button"
            onClick={() => onClone(chatbot.id)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 active:bg-gray-200 transition-all duration-200"
            aria-label={`Clone chatbot: ${chatbot.name}`}
          >
            <Copy className="h-3.5 w-3.5" aria-hidden="true" />
            Clone
          </button>
        )}

        {onDelete && (
          <button
            type="button"
            onClick={() => onDelete(chatbot.id)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-red-600 hover:bg-red-50 active:bg-red-100 transition-all duration-200 ml-auto"
            aria-label={`Delete chatbot: ${chatbot.name}`}
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            Delete
          </button>
        )}
      </div>
    </div>
  );
});
