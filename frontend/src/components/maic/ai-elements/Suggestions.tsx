// src/components/maic/ai-elements/Suggestions.tsx
//
// Horizontal scrollable suggestion pills for quick chat prompts.

import React from 'react';
import { cn } from '../../../lib/utils';

interface SuggestionsProps {
  className?: string;
  children: React.ReactNode;
}

interface SuggestionProps {
  suggestion: string;
  onClick?: (suggestion: string) => void;
  className?: string;
  children?: React.ReactNode;
}

export const Suggestions: React.FC<SuggestionsProps> = ({ className, children }) => (
  <div
    className={cn(
      'flex gap-2 overflow-x-auto whitespace-nowrap py-1 px-0.5',
      className,
    )}
    style={{
      scrollbarWidth: 'none',
      msOverflowStyle: 'none',
    }}
  >
    <style>{`.suggestions-scroll::-webkit-scrollbar { display: none; }`}</style>
    <div className="suggestions-scroll flex gap-2">
      {children}
    </div>
  </div>
);

export const Suggestion: React.FC<SuggestionProps> = ({
  suggestion,
  onClick,
  className,
  children,
}) => (
  <button
    type="button"
    onClick={() => onClick?.(suggestion)}
    className={cn(
      'rounded-full px-4 py-1.5 text-sm border border-gray-200',
      'hover:bg-gray-100 transition-colors cursor-pointer',
      'whitespace-nowrap shrink-0 text-gray-700',
      className,
    )}
  >
    {children ?? suggestion}
  </button>
);
