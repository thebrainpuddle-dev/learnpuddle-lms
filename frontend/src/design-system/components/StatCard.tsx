import React from 'react';
import { cn } from '../theme/cn';
import { TrendingUp, TrendingDown, type LucideIcon } from 'lucide-react';

const iconGradients = {
  accent: 'from-accent to-purple-500',
  success: 'from-success to-success-light',
  warning: 'from-warning to-warning-light',
  danger: 'from-danger to-danger-light',
  info: 'from-info to-info-light',
} as const;

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  color?: keyof typeof iconGradients;
  trend?: {
    value: number;
    label?: string;
  };
  className?: string;
}

export function StatCard({ label, value, icon: Icon, color = 'accent', trend, className }: StatCardProps) {
  const isPositive = trend && trend.value >= 0;

  return (
    <div className={cn('stat-card', className)}>
      <div className="flex items-start justify-between">
        <div className="space-y-2">
          <p className="text-sm font-medium text-content-secondary">{label}</p>
          <p className="text-3xl font-bold text-content tracking-tight">{value}</p>
          {trend && (
            <div className="flex items-center gap-1">
              {isPositive ? (
                <TrendingUp className="h-3.5 w-3.5 text-success" />
              ) : (
                <TrendingDown className="h-3.5 w-3.5 text-danger" />
              )}
              <span className={cn(
                'text-xs font-medium',
                isPositive ? 'text-success' : 'text-danger',
              )}>
                {isPositive && '+'}{trend.value}%
              </span>
              {trend.label && (
                <span className="text-xs text-content-muted">{trend.label}</span>
              )}
            </div>
          )}
        </div>
        <div className={cn('stat-icon bg-gradient-to-br', iconGradients[color])}>
          <Icon className="h-6 w-6" />
        </div>
      </div>
    </div>
  );
}
