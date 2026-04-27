// src/components/chatbot/ChatbotHistory.tsx
//
// History panel listing recent RAG chatbot queries (last 20).
// Supports optimistic delete with rollback on failure. (TASK-061)

import React from 'react';
import { TrashIcon, ClockIcon } from '@heroicons/react/24/outline';
import type { ChatbotHistoryItem } from '../../services/chatbotService';
import { cn } from '../../lib/utils';

interface ChatbotHistoryProps {
  items: ChatbotHistoryItem[];
  isLoading: boolean;
  onDelete: (id: string) => void;
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMs / 3_600_000);
  const diffDays = Math.floor(diffMs / 86_400_000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

export const ChatbotHistory: React.FC<ChatbotHistoryProps> = ({
  items,
  isLoading,
  onDelete,
}) => {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary-600" aria-label="Loading history" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-center px-4">
        <ClockIcon className="h-8 w-8 text-slate-300 mb-2" />
        <p className="text-sm text-slate-500">No recent questions</p>
        <p className="text-xs text-slate-400 mt-1">Your questions will appear here.</p>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-slate-100" role="list" aria-label="Question history">
      {items.map((item) => (
        <li key={item.id} className="flex items-start gap-2 px-4 py-3 group hover:bg-slate-50">
          <div className="flex-1 min-w-0">
            <p className="text-xs text-slate-500 truncate leading-relaxed">
              {item.answer.slice(0, 120)}
              {item.answer.length > 120 ? '…' : ''}
            </p>
            <div className="mt-1 flex items-center gap-2">
              <span className="text-[10px] text-slate-400">
                {formatRelativeTime(item.created_at)}
              </span>
              {!item.grounded && (
                <span className="text-[10px] font-medium text-amber-600 bg-amber-50 px-1 rounded">
                  Low confidence
                </span>
              )}
              {item.citations.length > 0 && (
                <span className="text-[10px] text-slate-400">
                  {item.citations.length} source{item.citations.length !== 1 ? 's' : ''}
                </span>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={() => onDelete(item.id)}
            className={cn(
              'shrink-0 p-1.5 rounded transition-colors mt-0.5',
              'text-slate-300 opacity-0 group-hover:opacity-100',
              'hover:text-red-500 hover:bg-red-50',
              'focus:outline-none focus:ring-2 focus:ring-red-400 focus:opacity-100',
            )}
            aria-label="Delete this query"
            title="Delete"
          >
            <TrashIcon className="h-3.5 w-3.5" />
          </button>
        </li>
      ))}
    </ul>
  );
};
