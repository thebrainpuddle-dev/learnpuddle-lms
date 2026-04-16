// src/components/maic/ai-elements/ChainOfThought.tsx
//
// Expandable chain-of-thought reasoning display using compound component pattern.
// Shows AI reasoning steps with badges and animated expand/collapse.

import React, { createContext, useContext, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Brain, ChevronRight } from 'lucide-react';
import { cn } from '../../../lib/utils';

// ─── Context ──────────────────────────────────────────────────────────────────

interface ChainOfThoughtContextValue {
  open: boolean;
  toggle: () => void;
}

const ChainOfThoughtContext = createContext<ChainOfThoughtContextValue | null>(null);

function useChainOfThoughtContext() {
  const ctx = useContext(ChainOfThoughtContext);
  if (!ctx) {
    throw new Error('ChainOfThought compound components must be used within <ChainOfThought>');
  }
  return ctx;
}

// ─── Root ─────────────────────────────────────────────────────────────────────

interface ChainOfThoughtProps {
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
  children: React.ReactNode;
}

export const ChainOfThought: React.FC<ChainOfThoughtProps> = ({
  open: controlledOpen,
  defaultOpen = false,
  onOpenChange,
  className,
  children,
}) => {
  const [uncontrolledOpen, setUncontrolledOpen] = useState(defaultOpen);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : uncontrolledOpen;

  const toggle = useCallback(() => {
    const next = !open;
    if (!isControlled) {
      setUncontrolledOpen(next);
    }
    onOpenChange?.(next);
  }, [open, isControlled, onOpenChange]);

  return (
    <ChainOfThoughtContext.Provider value={{ open, toggle }}>
      <div className={cn('rounded-lg border border-gray-200 bg-gray-50/80 overflow-hidden', className)}>
        {children}
      </div>
    </ChainOfThoughtContext.Provider>
  );
};

// ─── Trigger ──────────────────────────────────────────────────────────────────

interface ChainOfThoughtTriggerProps {
  className?: string;
  children?: React.ReactNode;
}

export const ChainOfThoughtTrigger: React.FC<ChainOfThoughtTriggerProps> = ({
  className,
  children,
}) => {
  const { open, toggle } = useChainOfThoughtContext();

  return (
    <button
      type="button"
      onClick={toggle}
      className={cn(
        'flex items-center gap-2 w-full px-3 py-2 text-left',
        'text-xs font-medium text-gray-600 hover:text-gray-800 hover:bg-gray-100/60',
        'transition-colors',
        className,
      )}
      aria-expanded={open}
    >
      <Brain className="h-3.5 w-3.5 shrink-0 text-purple-500" />
      <span className="flex-1">{children ?? 'Chain of Thought'}</span>
      <ChevronRight
        className={cn(
          'h-3.5 w-3.5 shrink-0 transition-transform duration-200 text-gray-400',
          open && 'rotate-90',
        )}
      />
    </button>
  );
};

// ─── Content ──────────────────────────────────────────────────────────────────

interface ChainOfThoughtContentProps {
  className?: string;
  children: React.ReactNode;
}

export const ChainOfThoughtContent: React.FC<ChainOfThoughtContentProps> = ({
  className,
  children,
}) => {
  const { open } = useChainOfThoughtContext();

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
          <div className={cn('border-t border-gray-100 px-3 py-2 space-y-2', className)}>
            {children}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

// ─── Step ─────────────────────────────────────────────────────────────────────

interface ChainOfThoughtStepProps {
  /** Step number (optional, falls back to bullet) */
  number?: number;
  /** Step type badge */
  type?: 'analyzing' | 'planning' | 'executing' | 'completed';
  className?: string;
  children: React.ReactNode;
}

const STEP_TYPE_COLORS: Record<string, { bg: string; text: string }> = {
  analyzing: { bg: 'bg-blue-100', text: 'text-blue-700' },
  planning: { bg: 'bg-amber-100', text: 'text-amber-700' },
  executing: { bg: 'bg-green-100', text: 'text-green-700' },
  completed: { bg: 'bg-gray-100', text: 'text-gray-600' },
};

export const ChainOfThoughtStep: React.FC<ChainOfThoughtStepProps> = ({
  number,
  type,
  className,
  children,
}) => {
  return (
    <div className={cn('flex items-start gap-2 text-xs text-gray-700', className)}>
      {number !== undefined ? (
        <span className="shrink-0 flex items-center justify-center h-5 w-5 rounded-full bg-gray-200 text-gray-600 text-[10px] font-medium mt-0.5">
          {number}
        </span>
      ) : (
        <span className="shrink-0 h-1.5 w-1.5 rounded-full bg-gray-400 mt-1.5 ml-1.5 mr-0.5" />
      )}
      <div className="flex-1 min-w-0">
        {type && <ChainOfThoughtBadge type={type} />}
        <span className="leading-relaxed">{children}</span>
      </div>
    </div>
  );
};

// ─── Badge ────────────────────────────────────────────────────────────────────

interface ChainOfThoughtBadgeProps {
  /** Badge text or type */
  type: string;
  className?: string;
}

export const ChainOfThoughtBadge: React.FC<ChainOfThoughtBadgeProps> = ({
  type,
  className,
}) => {
  const colors = STEP_TYPE_COLORS[type] ?? { bg: 'bg-gray-100', text: 'text-gray-600' };
  const label = type.charAt(0).toUpperCase() + type.slice(1);

  return (
    <span
      className={cn(
        'inline-block text-[10px] font-medium px-1.5 py-0.5 rounded-full mr-1.5 mb-0.5',
        colors.bg,
        colors.text,
        className,
      )}
    >
      {label}
    </span>
  );
};
