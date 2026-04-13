// src/components/ui/badge.tsx
//
// shadcn/ui-style Badge component for status indicators and labels.

import React from 'react';
import { cn } from '../../lib/utils';

const badgeVariants = {
  default: 'bg-primary-100 text-primary-800 border-primary-200',
  secondary: 'bg-gray-100 text-gray-800 border-gray-200',
  success: 'bg-emerald-100 text-emerald-800 border-emerald-200',
  destructive: 'bg-red-100 text-red-800 border-red-200',
  warning: 'bg-amber-100 text-amber-800 border-amber-200',
  outline: 'bg-transparent text-gray-700 border-gray-300',
} as const;

type BadgeVariant = keyof typeof badgeVariants;

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: BadgeVariant;
}

function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors',
        badgeVariants[variant],
        className,
      )}
      {...props}
    />
  );
}

export { Badge, badgeVariants };
