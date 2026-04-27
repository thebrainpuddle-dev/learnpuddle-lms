// src/components/chatbot/ChatbotMessage.tsx
//
// Renders a single RAG answer card, replacing [N] tokens with numbered citation
// chips that deep-link via react-router. Uses regex split + fragments — NO
// dangerouslySetInnerHTML. (TASK-061)

import React from 'react';
import { useNavigate } from 'react-router-dom';
import type { AskResponse, ChatbotCitation } from '../../services/chatbotService';
import { cn } from '../../lib/utils';

interface CitationChipProps {
  citation: ChatbotCitation;
  index: number;
  courseId: string;
}

function buildCitationUrl(citation: ChatbotCitation, courseId: string): string {
  const { source_type, source_id } = citation;
  if (source_type === 'content' || source_type === 'transcript') {
    return `/teacher/courses/${courseId}/contents/${source_id}`;
  }
  if (source_type === 'module') {
    return `/teacher/courses/${courseId}?module=${source_id}`;
  }
  if (source_type === 'course') {
    return `/teacher/courses/${source_id}`;
  }
  // Fallback: link to the current course
  return `/teacher/courses/${courseId}`;
}

const KNOWN_SOURCE_TYPES = new Set(['content', 'module', 'course', 'transcript']);

const CitationChip: React.FC<CitationChipProps> = ({ citation, index, courseId }) => {
  const navigate = useNavigate();

  // Unknown source_type — render a non-clickable span instead of a navigable button
  if (!KNOWN_SOURCE_TYPES.has(citation.source_type)) {
    return (
      <span
        title={citation.title || `Citation ${index + 1}`}
        className={cn(
          'inline-flex items-center justify-center',
          'w-5 h-5 rounded-full text-[10px] font-bold',
          'bg-slate-100 text-slate-500',
          'align-middle mx-0.5',
        )}
        aria-label={`Citation ${index + 1}: ${citation.title || citation.source_type}`}
        data-testid={`citation-chip-unknown-${index}`}
      >
        {index + 1}
      </span>
    );
  }

  const url = buildCitationUrl(citation, courseId);

  return (
    <button
      type="button"
      onClick={() => navigate(url)}
      title={citation.title || `Citation ${index + 1}`}
      className={cn(
        'inline-flex items-center justify-center',
        'w-5 h-5 rounded-full text-[10px] font-bold',
        'bg-primary-100 text-primary-700 hover:bg-primary-200',
        'cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1',
        'align-middle mx-0.5',
      )}
      aria-label={`Go to citation ${index + 1}: ${citation.title || citation.source_type}`}
    >
      {index + 1}
    </button>
  );
};

// Replace [N] tokens in answer text with CitationChip components.
function renderAnswerWithCitations(
  answer: string,
  citations: ChatbotCitation[],
  courseId: string,
): React.ReactNode[] {
  // Match patterns like [1], [2], [10]
  const parts = answer.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const match = part.match(/^\[(\d+)\]$/);
    if (match) {
      const citationIndex = parseInt(match[1], 10) - 1; // 1-based in text → 0-based
      const citation = citations[citationIndex];
      if (citation) {
        return (
          <CitationChip
            key={`chip-${i}`}
            citation={citation}
            index={citationIndex}
            courseId={courseId}
          />
        );
      }
      // Citation not found — render as plain text
      return <span key={`text-${i}`}>{part}</span>;
    }
    // Split on newlines to preserve line breaks
    const lines = part.split('\n');
    return lines.map((line, j) => (
      <React.Fragment key={`line-${i}-${j}`}>
        {line}
        {j < lines.length - 1 && <br />}
      </React.Fragment>
    ));
  });
}

interface ChatbotMessageProps {
  answer: AskResponse;
  courseId: string;
}

export const ChatbotMessage: React.FC<ChatbotMessageProps> = ({ answer, courseId }) => {
  const isGrounded = answer.grounded;

  return (
    <div
      className={cn(
        'rounded-xl border p-4 text-sm leading-relaxed',
        isGrounded
          ? 'border-slate-200 bg-white text-slate-800'
          : 'border-amber-200 bg-amber-50 text-amber-900',
      )}
      data-testid="chatbot-answer-card"
    >
      {!isGrounded && (
        <p className="mb-2 text-xs font-semibold text-amber-700 uppercase tracking-wide">
          Low confidence — limited source material found
        </p>
      )}

      <p className="whitespace-pre-wrap">
        {renderAnswerWithCitations(answer.answer, answer.citations, courseId)}
      </p>

      {!isGrounded && (
        <p className="mt-3 text-xs text-amber-600 border-t border-amber-200 pt-2">
          Not enough context — try rephrasing or asking about a different topic.
        </p>
      )}

      {isGrounded && answer.citations.length > 0 && (
        <div className="mt-3 border-t border-slate-100 pt-2">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-400 mb-1.5">
            Sources
          </p>
          <div className="flex flex-wrap gap-1.5">
            {answer.citations.map((citation, idx) => (
              <CitationChip
                key={citation.source_id + idx}
                citation={citation}
                index={idx}
                courseId={courseId}
              />
            ))}
            <span className="text-[11px] text-slate-500 self-center ml-1">
              {answer.citations.length} source{answer.citations.length !== 1 ? 's' : ''}
            </span>
          </div>
        </div>
      )}
    </div>
  );
};
