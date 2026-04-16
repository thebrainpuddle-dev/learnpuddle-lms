// src/components/maic/ai-elements/InlineCitation.tsx
//
// Hoverable inline citation with source preview card.
// Compound component pattern for flexible citation rendering.

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react';
import { cn } from '../../../lib/utils';

// ─── Types ────────────────────────────────────────────────────────────────────

interface CitationSource {
  title: string;
  url: string;
  content: string;
}

interface InlineCitationProps {
  sources: CitationSource[];
  className?: string;
  children: React.ReactNode;
}

interface InlineCitationTextProps {
  className?: string;
  children: React.ReactNode;
}

interface InlineCitationBadgeProps {
  index: number;
  className?: string;
}

interface InlineCitationCardProps {
  className?: string;
}

// ─── Context ──────────────────────────────────────────────────────────────────

interface InlineCitationContextValue {
  sources: CitationSource[];
  showCard: boolean;
  setShowCard: (show: boolean) => void;
  currentIndex: number;
  setCurrentIndex: (index: number) => void;
  badgeRef: React.RefObject<HTMLSpanElement | null>;
}

const InlineCitationContext = React.createContext<InlineCitationContextValue | null>(null);

function useCitationContext() {
  const ctx = React.useContext(InlineCitationContext);
  if (!ctx) {
    throw new Error('InlineCitation compound components must be used within <InlineCitation>');
  }
  return ctx;
}

// ─── Root ─────────────────────────────────────────────────────────────────────

export const InlineCitation: React.FC<InlineCitationProps> = ({
  sources,
  className,
  children,
}) => {
  const [showCard, setShowCard] = useState(false);
  const [currentIndex, setCurrentIndex] = useState(0);
  const badgeRef = useRef<HTMLSpanElement | null>(null);

  return (
    <InlineCitationContext.Provider
      value={{ sources, showCard, setShowCard, currentIndex, setCurrentIndex, badgeRef }}
    >
      <span className={cn('group inline', className)}>
        {children}
      </span>
    </InlineCitationContext.Provider>
  );
};

// ─── Citation Text ────────────────────────────────────────────────────────────

export const InlineCitationText: React.FC<InlineCitationTextProps> = ({
  className,
  children,
}) => {
  const { showCard } = useCitationContext();

  return (
    <span
      className={cn(
        'transition-colors duration-150',
        showCard ? 'bg-yellow-100/60 text-gray-900' : 'text-inherit',
        className,
      )}
    >
      {children}
    </span>
  );
};

// ─── Citation Badge ───────────────────────────────────────────────────────────

export const InlineCitationBadge: React.FC<InlineCitationBadgeProps> = ({
  index,
  className,
}) => {
  const { setShowCard, setCurrentIndex, badgeRef } = useCitationContext();
  const hoverTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleMouseEnter = useCallback(() => {
    hoverTimeoutRef.current = setTimeout(() => {
      setCurrentIndex(index - 1);
      setShowCard(true);
    }, 150);
  }, [index, setCurrentIndex, setShowCard]);

  const handleMouseLeave = useCallback(() => {
    if (hoverTimeoutRef.current) {
      clearTimeout(hoverTimeoutRef.current);
      hoverTimeoutRef.current = null;
    }
    setShowCard(false);
  }, [setShowCard]);

  useEffect(() => {
    return () => {
      if (hoverTimeoutRef.current) clearTimeout(hoverTimeoutRef.current);
    };
  }, []);

  return (
    <span
      ref={badgeRef}
      className={cn(
        'inline-flex items-center justify-center text-[10px] font-medium',
        'text-blue-600 cursor-pointer hover:text-blue-800',
        'align-super leading-none ml-0.5',
        className,
      )}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      role="button"
      tabIndex={0}
      aria-label={`Citation ${index}`}
    >
      [{index}]
    </span>
  );
};

// ─── Citation Card ────────────────────────────────────────────────────────────

export const InlineCitationCard: React.FC<InlineCitationCardProps> = ({
  className,
}) => {
  const { sources, showCard, setShowCard, currentIndex, setCurrentIndex } = useCitationContext();

  if (!showCard || sources.length === 0) return null;

  const source = sources[currentIndex] ?? sources[0];
  const hasMultiple = sources.length > 1;

  const handlePrev = () => {
    setCurrentIndex(currentIndex > 0 ? currentIndex - 1 : sources.length - 1);
  };

  const handleNext = () => {
    setCurrentIndex(currentIndex < sources.length - 1 ? currentIndex + 1 : 0);
  };

  /** Truncate URL for display */
  const displayUrl = (() => {
    try {
      const u = new URL(source.url);
      return u.hostname + (u.pathname.length > 30 ? u.pathname.slice(0, 30) + '...' : u.pathname);
    } catch {
      return source.url.slice(0, 40);
    }
  })();

  return (
    <div
      className={cn(
        'absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50',
        'bg-white shadow-lg rounded-lg border border-gray-200 p-3 max-w-sm w-72',
        'text-left',
        className,
      )}
      onMouseEnter={() => setShowCard(true)}
      onMouseLeave={() => setShowCard(false)}
    >
      {/* Arrow */}
      <div className="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-3 h-3 bg-white border-b border-r border-gray-200 rotate-45" />

      {/* Title */}
      <p className="text-sm font-medium text-gray-900 truncate">{source.title}</p>

      {/* URL */}
      <a
        href={source.url}
        target="_blank"
        rel="noopener noreferrer"
        className="flex items-center gap-1 text-xs text-blue-500 hover:text-blue-700 mt-0.5 truncate"
      >
        <ExternalLink className="h-3 w-3 shrink-0" />
        {displayUrl}
      </a>

      {/* Content preview */}
      <p className="text-xs text-gray-600 mt-2 line-clamp-3 leading-relaxed">
        {source.content.length > 200 ? source.content.slice(0, 200) + '...' : source.content}
      </p>

      {/* Navigation arrows for multiple sources */}
      {hasMultiple && (
        <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-100">
          <button
            type="button"
            onClick={handlePrev}
            className="p-0.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Previous source"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
          </button>
          <span className="text-[10px] text-gray-400">
            {currentIndex + 1} / {sources.length}
          </span>
          <button
            type="button"
            onClick={handleNext}
            className="p-0.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
            aria-label="Next source"
          >
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </div>
  );
};
