import React from 'react';
import { cn } from '../theme/cn';
import { Loader2 } from 'lucide-react';

const variants = {
  primary:
    'bg-gradient-to-r from-accent to-accent-dark text-white hover:shadow-glow-accent hover:-translate-y-0.5 active:translate-y-0',
  secondary:
    'bg-white border border-surface-border text-content hover:bg-surface-card-hover',
  outline:
    'border-2 border-accent text-accent hover:bg-accent-50',
  ghost:
    'text-content-secondary hover:bg-surface-card-hover hover:text-content',
  danger:
    'bg-gradient-to-r from-danger to-danger-light text-white hover:shadow-lg hover:-translate-y-0.5 active:translate-y-0',
  success:
    'bg-gradient-to-r from-success to-success-light text-white hover:shadow-glow-success hover:-translate-y-0.5 active:translate-y-0',
  link:
    'text-accent underline-offset-4 hover:underline p-0 h-auto',
} as const;

const sizes = {
  sm: 'h-8 px-3 text-xs rounded-lg gap-1.5',
  md: 'h-10 px-4 text-sm rounded-xl gap-2',
  lg: 'h-11 px-6 text-sm rounded-xl gap-2',
  xl: 'h-12 px-8 text-base rounded-xl gap-2.5',
  icon: 'h-10 w-10 rounded-xl p-0',
  'icon-sm': 'h-8 w-8 rounded-lg p-0',
} as const;

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
  loading?: boolean;
  icon?: React.ReactNode;
  iconRight?: React.ReactNode;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', loading, disabled, icon, iconRight, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={cn(
          'inline-flex items-center justify-center font-medium transition-all duration-200',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2',
          'disabled:opacity-50 disabled:pointer-events-none',
          variants[variant],
          sizes[size],
          className,
        )}
        {...props}
      >
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin" />
        ) : icon ? (
          icon
        ) : null}
        {children}
        {iconRight}
      </button>
    );
  },
);

Button.displayName = 'Button';
