// src/components/ui/tooltip.tsx
//
// shadcn/ui-style Tooltip using a lightweight CSS-only approach.
// No additional Radix dependency required.

import React, { useState, useRef, useCallback, useId, useEffect } from 'react';
import { cn } from '../../lib/utils';

interface TooltipProps {
  /** The content shown inside the tooltip */
  content: React.ReactNode;
  /** Side where the tooltip appears */
  side?: 'top' | 'bottom' | 'left' | 'right';
  /** Delay before showing (ms) */
  delayDuration?: number;
  children: React.ReactElement;
  className?: string;
}

function Tooltip({
  content,
  side = 'top',
  delayDuration = 200,
  children,
  className,
}: TooltipProps) {
  const [visible, setVisible] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  const tooltipId = useId();

  const show = useCallback(() => {
    timerRef.current = setTimeout(() => setVisible(true), delayDuration);
  }, [delayDuration]);

  const hide = useCallback(() => {
    clearTimeout(timerRef.current);
    setVisible(false);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape' && visible) {
        e.preventDefault();
        hide();
      }
    },
    [visible, hide],
  );

  useEffect(() => {
    return () => clearTimeout(timerRef.current);
  }, []);

  const sideClasses = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2',
  };

  return (
    <span
      className="relative inline-flex"
      onMouseEnter={show}
      onMouseLeave={hide}
      onFocus={show}
      onBlur={hide}
      onKeyDown={handleKeyDown}
      tabIndex={0}
      aria-describedby={visible ? tooltipId : undefined}
    >
      {children}
      {visible && (
        <span
          id={tooltipId}
          role="tooltip"
          className={cn(
            'absolute z-50 max-w-xs rounded-md bg-gray-900 px-3 py-1.5 text-xs text-white shadow-md',
            'pointer-events-none whitespace-nowrap',
            sideClasses[side],
            className,
          )}
        >
          {content}
        </span>
      )}
    </span>
  );
}

export { Tooltip };
