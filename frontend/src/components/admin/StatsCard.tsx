// src/components/admin/StatsCard.tsx

import React from 'react';
import { clsx } from 'clsx';

export type StatsCardVariant = 'indigo' | 'emerald' | 'amber' | 'rose' | 'blue' | 'purple';

interface StatsCardProps {
  title: string;
  value: string | number;
  change?: {
    value: number;
    positive: boolean;
  };
  icon: React.ReactNode;
  loading?: boolean;
  variant?: StatsCardVariant;
  description?: string;
}

const VARIANTS: Record<StatsCardVariant, { bg: string; border: string; iconBg: string; iconText: string; text: string }> = {
  indigo: { bg: 'bg-indigo-50', border: 'border-indigo-100', iconBg: 'bg-indigo-100', iconText: 'text-indigo-600', text: 'text-indigo-900' },
  emerald: { bg: 'bg-emerald-50', border: 'border-emerald-100', iconBg: 'bg-emerald-100', iconText: 'text-emerald-600', text: 'text-emerald-900' },
  amber: { bg: 'bg-amber-50', border: 'border-amber-100', iconBg: 'bg-amber-100', iconText: 'text-amber-600', text: 'text-amber-900' },
  rose: { bg: 'bg-rose-50', border: 'border-rose-100', iconBg: 'bg-rose-100', iconText: 'text-rose-600', text: 'text-rose-900' },
  blue: { bg: 'bg-blue-50', border: 'border-blue-100', iconBg: 'bg-blue-100', iconText: 'text-blue-600', text: 'text-blue-900' },
  purple: { bg: 'bg-purple-50', border: 'border-purple-100', iconBg: 'bg-purple-100', iconText: 'text-purple-600', text: 'text-purple-900' },
};

export const StatsCard: React.FC<StatsCardProps> = ({
  title,
  value,
  change,
  icon,
  loading,
  variant = 'indigo',
  description,
}) => {
  const styles = VARIANTS[variant];

  if (loading) {
    return (
      <div className={`rounded-2xl border ${styles.border} ${styles.bg} p-6 h-full`}>
        <div className="animate-pulse space-y-4">
          <div className="h-10 w-10 bg-white/50 rounded-xl"></div>
          <div className="space-y-2">
            <div className="h-4 bg-white/50 rounded w-1/2"></div>
            <div className="h-8 bg-white/50 rounded w-3/4"></div>
          </div>
        </div>
      </div>
    );
  }
  
  return (
    <div className={`group relative overflow-hidden rounded-2xl border ${styles.border} ${styles.bg} p-6 transition-all duration-300 hover:shadow-lg hover:-translate-y-1`}>
      {/* Background decoration */}
      <div className="absolute -right-6 -top-6 h-24 w-24 rounded-full bg-white/20 blur-2xl transition-all group-hover:bg-white/30" />
      <div className="absolute -left-6 -bottom-6 h-20 w-20 rounded-full bg-white/20 blur-xl transition-all group-hover:bg-white/30" />

      <div className="relative flex flex-col h-full justify-between">
        <div className="flex items-start justify-between mb-4">
          <div className={`p-3 rounded-xl bg-white shadow-sm ring-1 ring-black/5 ${styles.iconText}`}>
            {React.cloneElement(icon as React.ReactElement<{ className?: string }>, { className: 'h-6 w-6' })}
          </div>
          {change && (
            <span
              className={clsx(
                'inline-flex items-center rounded-full px-2 py-1 text-xs font-medium bg-white/60 backdrop-blur-sm',
                change.positive ? 'text-green-700' : 'text-rose-700'
              )}
            >
              {change.positive ? '↑' : '↓'} {Math.abs(change.value)}%
            </span>
          )}
        </div>

        <div>
          <p className={`text-sm font-medium ${styles.text} opacity-80`}>{title}</p>
          <div className="flex items-baseline gap-2 mt-1">
            <h3 className={`text-3xl font-bold ${styles.text} tracking-tight`}>{value}</h3>
            {description && <span className={`text-xs ${styles.text} opacity-60`}>{description}</span>}
          </div>
        </div>
      </div>
    </div>
  );
};
