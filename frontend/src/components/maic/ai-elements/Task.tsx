// src/components/maic/ai-elements/Task.tsx
//
// Collapsible task/todo items with file badges.
// Lightweight compound component for displaying action items.

import React, { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Search, ChevronRight } from 'lucide-react';
import { cn } from '../../../lib/utils';

// ─── Types ────────────────────────────────────────────────────────────────────

interface TaskProps {
  defaultOpen?: boolean;
  className?: string;
  children: React.ReactNode;
}

interface TaskTriggerProps {
  title: string;
  className?: string;
  children?: React.ReactNode;
}

interface TaskContentProps {
  className?: string;
  children: React.ReactNode;
}

interface TaskItemProps {
  className?: string;
  children: React.ReactNode;
}

interface TaskItemFileProps {
  className?: string;
  children: React.ReactNode;
}

// ─── Context ──────────────────────────────────────────────────────────────────

interface TaskContextValue {
  open: boolean;
  toggle: () => void;
}

const TaskContext = React.createContext<TaskContextValue | null>(null);

function useTaskContext() {
  const ctx = React.useContext(TaskContext);
  if (!ctx) {
    throw new Error('Task compound components must be used within <Task>');
  }
  return ctx;
}

// ─── Components ───────────────────────────────────────────────────────────────

export const Task: React.FC<TaskProps> = ({ defaultOpen = false, className, children }) => {
  const [open, setOpen] = useState(defaultOpen);
  const toggle = useCallback(() => setOpen((prev) => !prev), []);

  return (
    <TaskContext.Provider value={{ open, toggle }}>
      <div className={cn('rounded-lg border border-gray-200 bg-white overflow-hidden', className)}>
        {children}
      </div>
    </TaskContext.Provider>
  );
};

export const TaskTrigger: React.FC<TaskTriggerProps> = ({ title, className, children }) => {
  const { open, toggle } = useTaskContext();

  return (
    <button
      type="button"
      onClick={toggle}
      className={cn(
        'flex items-center gap-2 w-full px-3 py-2 text-left',
        'text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors',
        className,
      )}
      aria-expanded={open}
    >
      <Search className="h-3.5 w-3.5 shrink-0 text-gray-400" />
      <span className="flex-1 truncate">{title}</span>
      {children}
      <ChevronRight
        className={cn(
          'h-3.5 w-3.5 shrink-0 text-gray-400 transition-transform duration-200',
          open && 'rotate-90',
        )}
      />
    </button>
  );
};

export const TaskContent: React.FC<TaskContentProps> = ({ className, children }) => {
  const { open } = useTaskContext();

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
          <div className={cn('border-t border-gray-100 border-l-2 border-l-primary-400 ml-3 pl-3 py-2 space-y-1.5', className)}>
            {children}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export const TaskItem: React.FC<TaskItemProps> = ({ className, children }) => (
  <div className={cn('text-xs text-gray-500 leading-relaxed', className)}>
    {children}
  </div>
);

export const TaskItemFile: React.FC<TaskItemFileProps> = ({ className, children }) => (
  <span
    className={cn(
      'inline-flex items-center px-1.5 py-0.5 rounded border border-gray-200 bg-gray-50',
      'font-mono text-[11px] text-gray-600',
      className,
    )}
  >
    {children}
  </span>
);
