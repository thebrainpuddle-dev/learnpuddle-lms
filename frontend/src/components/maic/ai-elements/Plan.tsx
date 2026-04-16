// src/components/maic/ai-elements/Plan.tsx
//
// Collapsible planning panel with streaming indicator.
// Uses compound component pattern with context for shared state.

import React, { createContext, useContext, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ChevronsUpDown } from 'lucide-react';
import { cn } from '../../../lib/utils';
import { Shimmer } from './Shimmer';

// ─── Context ──────────────────────────────────────────────────────────────────

interface PlanContextValue {
  isStreaming: boolean;
  open: boolean;
  toggle: () => void;
}

const PlanContext = createContext<PlanContextValue | null>(null);

function usePlanContext() {
  const ctx = useContext(PlanContext);
  if (!ctx) {
    throw new Error('Plan compound components must be used within <Plan>');
  }
  return ctx;
}

// ─── Root ─────────────────────────────────────────────────────────────────────

interface PlanProps {
  isStreaming?: boolean;
  className?: string;
  children: React.ReactNode;
}

export const Plan: React.FC<PlanProps> = ({
  isStreaming = false,
  className,
  children,
}) => {
  const [open, setOpen] = useState(true);

  const toggle = useCallback(() => setOpen((prev) => !prev), []);

  return (
    <PlanContext.Provider value={{ isStreaming, open, toggle }}>
      <div className={cn('rounded-lg border border-gray-200 bg-white overflow-hidden', className)}>
        {children}
      </div>
    </PlanContext.Provider>
  );
};

// ─── Header ───────────────────────────────────────────────────────────────────

interface PlanHeaderProps {
  className?: string;
  children: React.ReactNode;
}

export const PlanHeader: React.FC<PlanHeaderProps> = ({ className, children }) => (
  <div className={cn('flex items-center gap-2 px-3 py-2', className)}>
    {children}
  </div>
);

// ─── Title ────────────────────────────────────────────────────────────────────

interface PlanTitleProps {
  className?: string;
  children: string;
}

export const PlanTitle: React.FC<PlanTitleProps> = ({ className, children }) => {
  const { isStreaming } = usePlanContext();

  return isStreaming ? (
    <Shimmer as="h3" className={cn('text-sm font-semibold text-gray-900', className)}>
      {children}
    </Shimmer>
  ) : (
    <h3 className={cn('text-sm font-semibold text-gray-900', className)}>{children}</h3>
  );
};

// ─── Description ──────────────────────────────────────────────────────────────

interface PlanDescriptionProps {
  className?: string;
  children: string;
}

export const PlanDescription: React.FC<PlanDescriptionProps> = ({ className, children }) => {
  const { isStreaming } = usePlanContext();

  return isStreaming ? (
    <Shimmer as="p" className={cn('text-xs text-gray-500', className)}>
      {children}
    </Shimmer>
  ) : (
    <p className={cn('text-xs text-gray-500', className)}>{children}</p>
  );
};

// ─── Trigger ──────────────────────────────────────────────────────────────────

interface PlanTriggerProps {
  className?: string;
}

export const PlanTrigger: React.FC<PlanTriggerProps> = ({ className }) => {
  const { open, toggle } = usePlanContext();

  return (
    <button
      type="button"
      onClick={toggle}
      className={cn(
        'ml-auto p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors',
        className,
      )}
      aria-expanded={open}
      aria-label={open ? 'Collapse plan' : 'Expand plan'}
    >
      <ChevronsUpDown className="h-4 w-4" />
    </button>
  );
};

// ─── Content ──────────────────────────────────────────────────────────────────

interface PlanContentProps {
  className?: string;
  children: React.ReactNode;
}

export const PlanContent: React.FC<PlanContentProps> = ({ className, children }) => {
  const { open } = usePlanContext();

  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.2, ease: 'easeInOut' }}
          className="overflow-hidden"
        >
          <div className={cn('px-3 py-2 border-t border-gray-100', className)}>
            {children}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

// ─── Footer ───────────────────────────────────────────────────────────────────

interface PlanFooterProps {
  className?: string;
  children: React.ReactNode;
}

export const PlanFooter: React.FC<PlanFooterProps> = ({ className, children }) => (
  <div className={cn('px-3 py-2 border-t border-gray-100 bg-gray-50/50', className)}>
    {children}
  </div>
);
