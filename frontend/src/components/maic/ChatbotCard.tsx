// src/components/maic/ChatbotCard.tsx
//
// Card component for the teacher chatbot library grid. Shows name, persona
// preset badge, knowledge/conversation counts, active status, and actions.

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Bot, Pencil, Trash2, MessageCircle, BookOpen } from 'lucide-react';
import type { AIChatbot } from '../../types/chatbot';
import { cn } from '../../lib/utils';

// ─── Persona Badge Config ────────────────────────────────────────────────────

const presetConfig: Record<
  AIChatbot['persona_preset'],
  { label: string; classes: string }
> = {
  tutor: { label: 'Tutor', classes: 'bg-blue-100 text-blue-700' },
  reference: { label: 'Reference', classes: 'bg-purple-100 text-purple-700' },
  open: { label: 'Open', classes: 'bg-green-100 text-green-700' },
};

// ─── Props ───────────────────────────────────────────────────────────────────

interface Props {
  chatbot: AIChatbot;
  onDelete?: (id: string) => void;
  /** Whether to show the Edit button. Defaults to true. Set to false for student views. */
  showEdit?: boolean;
}

// ─── Component ───────────────────────────────────────────────────────────────

export const ChatbotCard = React.memo<Props>(function ChatbotCard({
  chatbot,
  onDelete,
  showEdit = true,
}) {
  const navigate = useNavigate();
  const preset = presetConfig[chatbot.persona_preset] || presetConfig.open;

  return (
    <div
      className={cn(
        'group relative w-full text-left rounded-xl border bg-white p-5',
        'shadow-sm hover:shadow-md transition-all duration-200',
        'focus-within:ring-2 focus-within:ring-primary-500 focus-within:ring-offset-2',
        chatbot.is_active
          ? 'border-gray-200 hover:border-gray-300'
          : 'border-gray-200 opacity-60',
      )}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <Bot className="h-5 w-5 shrink-0 text-indigo-500" aria-hidden="true" />
          <h3 className="text-base font-semibold text-gray-900 truncate group-hover:text-primary-600 transition-colors">
            {chatbot.name}
          </h3>
        </div>

        {/* Active / Inactive indicator */}
        <span
          className={cn(
            'shrink-0 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium',
            chatbot.is_active
              ? 'bg-emerald-100 text-emerald-700'
              : 'bg-gray-100 text-gray-500',
          )}
        >
          <span
            className={cn(
              'h-1.5 w-1.5 rounded-full',
              chatbot.is_active ? 'bg-emerald-500' : 'bg-gray-400',
            )}
          />
          {chatbot.is_active ? 'Active' : 'Inactive'}
        </span>
      </div>

      {/* Persona badge */}
      <div className="mb-3">
        <span
          className={cn(
            'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
            preset.classes,
          )}
        >
          {preset.label}
        </span>
      </div>

      {/* Meta row */}
      <div className="flex items-center gap-4 text-xs text-gray-400 mb-4">
        <span className="inline-flex items-center gap-1">
          <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
          {chatbot.knowledge_count} source{chatbot.knowledge_count !== 1 ? 's' : ''}
        </span>
        <span className="inline-flex items-center gap-1">
          <MessageCircle className="h-3.5 w-3.5" aria-hidden="true" />
          {chatbot.conversation_count} conversation{chatbot.conversation_count !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-3 border-t border-gray-100">
        {showEdit && (
          <button
            type="button"
            onClick={() => navigate(`/teacher/chatbots/${chatbot.id}`)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-indigo-600 hover:bg-indigo-50 transition-colors"
            aria-label={`Edit chatbot: ${chatbot.name}`}
          >
            <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
            Edit
          </button>
        )}

        {onDelete && (
          <button
            type="button"
            onClick={() => onDelete(chatbot.id)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium text-red-600 hover:bg-red-50 transition-colors ml-auto"
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
