import React from 'react';
import { cn } from '../theme/cn';
import { type LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  action?: React.ReactNode;
  className?: string;
}

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center py-16 px-4 text-center', className)}>
      <div className="h-16 w-16 rounded-2xl bg-accent-50 flex items-center justify-center mb-4">
        <Icon className="h-8 w-8 text-accent" />
      </div>
      <h3 className="text-lg font-semibold text-content mb-1">{title}</h3>
      <p className="text-sm text-content-secondary max-w-sm mb-6">{description}</p>
      {action}
    </div>
  );
}
