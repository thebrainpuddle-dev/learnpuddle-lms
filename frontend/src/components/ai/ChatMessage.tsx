// src/components/ai/ChatMessage.tsx
//
// Individual chat message bubble. User messages appear on the right,
// AI assistant messages on the left with optional source citations.

import React, { useState } from 'react';
import DOMPurify from 'dompurify';
import { ChevronDownIcon, ChevronRightIcon, DocumentTextIcon } from '@heroicons/react/24/outline';
import type { ChatMessage as ChatMessageType, ChatSource } from '../../services/aiService';
import { cn } from '../../lib/utils';

interface ChatMessageProps {
  message: ChatMessageType;
}

// ─── Simple markdown-to-HTML converter ──────────────────────────────────────
function renderMarkdown(text: string): string {
  let html = text
    // Code blocks (triple backtick)
    .replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="bg-gray-100 rounded-md p-3 my-2 overflow-x-auto text-sm"><code>$2</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code class="bg-gray-100 px-1 py-0.5 rounded text-sm font-mono">$1</code>')
    // Bold
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    // Italic
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    // Unordered lists
    .replace(/^- (.+)$/gm, '<li class="ml-4 list-disc">$1</li>')
    // Ordered lists
    .replace(/^\d+\. (.+)$/gm, '<li class="ml-4 list-decimal">$1</li>')
    // Headings
    .replace(/^### (.+)$/gm, '<h4 class="font-semibold text-sm mt-2 mb-1">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="font-semibold text-base mt-2 mb-1">$1</h3>')
    .replace(/^# (.+)$/gm, '<h2 class="font-bold text-lg mt-2 mb-1">$1</h2>')
    // Paragraphs (double newline)
    .replace(/\n\n/g, '</p><p class="mb-2">');

  // Wrap in paragraph tag
  html = `<p class="mb-2">${html}</p>`;

  // Wrap adjacent <li> tags in <ul>
  html = html.replace(
    /(<li class="ml-4 list-disc">[\s\S]*?<\/li>)+/g,
    '<ul class="my-1">$&</ul>'
  );
  html = html.replace(
    /(<li class="ml-4 list-decimal">[\s\S]*?<\/li>)+/g,
    '<ol class="my-1">$&</ol>'
  );

  return DOMPurify.sanitize(html);
}

// ─── Source citation component ──────────────────────────────────────────────
const SourceCitations: React.FC<{ sources: ChatSource[] }> = ({ sources }) => {
  const [expanded, setExpanded] = useState(false);

  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-2 border-t border-gray-200 pt-2">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 transition-colors"
      >
        {expanded ? (
          <ChevronDownIcon className="h-3 w-3" />
        ) : (
          <ChevronRightIcon className="h-3 w-3" />
        )}
        <DocumentTextIcon className="h-3 w-3" />
        {sources.length} source{sources.length !== 1 ? 's' : ''}
      </button>
      {expanded && (
        <ul className="mt-1.5 space-y-1">
          {sources.map((source, idx) => (
            <li
              key={idx}
              className="flex items-start gap-2 text-xs text-gray-600 bg-gray-50 rounded px-2 py-1.5"
            >
              <span className="shrink-0 w-4 h-4 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-[10px] font-bold mt-0.5">
                {idx + 1}
              </span>
              <div className="min-w-0">
                <p className="font-medium text-gray-700 truncate">{source.source_type}</p>
                <p className="text-gray-400 truncate">{source.excerpt}</p>
              </div>
              <span className="shrink-0 ml-auto text-[10px] text-gray-400">
                {Math.round(source.score * 100)}%
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};

// ─── Main component ─────────────────────────────────────────────────────────
export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const isUser = message.role === 'user';

  return (
    <div
      className={cn(
        'flex w-full mb-4',
        isUser ? 'justify-end' : 'justify-start',
      )}
    >
      <div
        className={cn(
          'max-w-[85%] rounded-2xl px-4 py-3',
          isUser
            ? 'bg-primary-600 text-white rounded-br-md'
            : 'bg-gray-100 text-gray-900 rounded-bl-md',
        )}
      >
        {isUser ? (
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        ) : (
          <>
            <div
              className="text-sm prose-sm [&_p]:mb-2 [&_p:last-child]:mb-0 [&_code]:text-gray-800 [&_pre]:bg-white/60"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }}
            />
            {message.sources && <SourceCitations sources={message.sources} />}
          </>
        )}

        <p
          className={cn(
            'text-[10px] mt-1.5',
            isUser ? 'text-primary-200' : 'text-gray-400',
          )}
        >
          {new Date(message.created_at).toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </p>
      </div>
    </div>
  );
};
