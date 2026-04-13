import React from 'react';
import { cn } from '../theme/cn';

const variants = {
  default: 'bg-accent-50 text-accent-700 border-accent-200',
  success: 'bg-success-bg text-success-dark border-success/20',
  warning: 'bg-warning-bg text-warning-dark border-warning/20',
  danger: 'bg-danger-bg text-danger-dark border-danger/20',
  info: 'bg-info-bg text-info-dark border-info/20',
  neutral: 'bg-slate-100 text-slate-700 border-slate-200',
  outline: 'bg-transparent text-content-secondary border-surface-border',
} as const;

const sizes = {
  sm: 'px-1.5 py-0.5 text-[10px]',
  md: 'px-2 py-0.5 text-xs',
  lg: 'px-2.5 py-1 text-xs',
} as const;

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
  dot?: boolean;
}

export function Badge({
  variant = 'default',
  size = 'md',
  dot = false,
  className,
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border font-medium',
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {dot && (
        <span className={cn(
          'h-1.5 w-1.5 rounded-full',
          variant === 'success' && 'bg-success',
          variant === 'warning' && 'bg-warning',
          variant === 'danger' && 'bg-danger',
          variant === 'info' && 'bg-info',
          variant === 'default' && 'bg-accent',
          variant === 'neutral' && 'bg-slate-400',
          variant === 'outline' && 'bg-content-muted',
        )} />
      )}
      {children}
    </span>
  );
}
