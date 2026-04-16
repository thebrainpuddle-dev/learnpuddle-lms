// src/components/maic/ConversationContainer.tsx
//
// Auto-scrolling message container for chat conversations. Tracks user
// scroll position and shows a "scroll to bottom" floating button when
// the user has scrolled up beyond 200px from the bottom.

import React, { useRef, useEffect, useState, useCallback } from 'react';
import { ArrowDown } from 'lucide-react';
import { cn } from '../../lib/utils';

// ─── Props ───────────────────────────────────────────────────────────────────

export interface ConversationContainerProps {
  className?: string;
  children: React.ReactNode;
  autoScroll?: boolean;
  showScrollToBottom?: boolean;
}

// ─── Component ───────────────────────────────────────────────────────────────

export const ConversationContainer = React.memo<ConversationContainerProps>(
  function ConversationContainer({
    className,
    children,
    autoScroll = true,
    showScrollToBottom = true,
  }) {
    const containerRef = useRef<HTMLDivElement>(null);
    const sentinelRef = useRef<HTMLDivElement>(null);
    const [isAtBottom, setIsAtBottom] = useState(true);
    const [newMessageCount, setNewMessageCount] = useState(0);
    const prevChildCountRef = useRef(0);

    // ─── Intersection Observer for sentinel div ──────────────────────────
    useEffect(() => {
      const sentinel = sentinelRef.current;
      if (!sentinel) return;

      const observer = new IntersectionObserver(
        ([entry]) => {
          const atBottom = entry.isIntersecting;
          setIsAtBottom(atBottom);
          if (atBottom) {
            setNewMessageCount(0);
          }
        },
        {
          root: containerRef.current,
          rootMargin: '0px 0px 200px 0px',
          threshold: 0,
        },
      );

      observer.observe(sentinel);
      return () => observer.disconnect();
    }, []);

    // ─── Auto-scroll when new children arrive and user is at bottom ─────
    useEffect(() => {
      if (!autoScroll) return;

      const childCount = React.Children.count(children);
      const diff = childCount - prevChildCountRef.current;
      prevChildCountRef.current = childCount;

      if (diff > 0) {
        if (isAtBottom) {
          // Scroll to bottom smoothly
          sentinelRef.current?.scrollIntoView({ behavior: 'smooth' });
        } else {
          // User is scrolled up — increment unread badge
          setNewMessageCount((c) => c + diff);
        }
      }
    }, [children, autoScroll, isAtBottom]);

    // ─── Manual scroll to bottom ─────────────────────────────────────────
    const scrollToBottom = useCallback(() => {
      sentinelRef.current?.scrollIntoView({ behavior: 'smooth' });
      setNewMessageCount(0);
    }, []);

    const showButton = showScrollToBottom && !isAtBottom;

    return (
      <div className={cn('relative flex-1 min-h-0', className)}>
        {/* Scrollable area */}
        <div
          ref={containerRef}
          className="h-full overflow-y-auto px-4 py-3 space-y-3"
        >
          {children}
          {/* Sentinel div at the bottom for IntersectionObserver */}
          <div ref={sentinelRef} className="h-px w-full" aria-hidden="true" />
        </div>

        {/* Scroll-to-bottom FAB */}
        {showButton && (
          <button
            type="button"
            onClick={scrollToBottom}
            className={cn(
              'absolute bottom-3 left-1/2 -translate-x-1/2 z-10',
              'flex items-center gap-1.5 px-3 py-1.5 rounded-full',
              'bg-white border border-gray-200 shadow-md',
              'text-xs text-gray-600 hover:bg-gray-50',
              'transition-all',
            )}
            aria-label="Scroll to bottom"
          >
            <ArrowDown className="h-3.5 w-3.5" />
            {newMessageCount > 0 && (
              <span className="flex items-center justify-center h-4 min-w-[16px] px-1 rounded-full bg-primary-600 text-white text-[10px] font-medium">
                {newMessageCount > 99 ? '99+' : newMessageCount}
              </span>
            )}
          </button>
        )}
      </div>
    );
  },
);
