// src/components/attendance/AttendanceCard.tsx
//
// "Today's Attendance" card — bar chart visualization with on-time/late/absent
// breakdown. Used across admin dashboard, teacher section dashboard, and student page.

import React from 'react';
import { ClipboardList, TrendingUp, TrendingDown } from 'lucide-react';
import { cn } from '../../design-system/theme/cn';

interface AttendanceBar {
  status: string;
}

interface AttendanceSummary {
  total: number;
  present: number;
  late: number;
  absent: number;
  excused: number;
  attendance_rate: number;
  on_time_pct: number;
  late_pct: number;
  absent_pct: number;
}

interface AttendanceCardProps {
  title?: string;
  summary: AttendanceSummary;
  bars: AttendanceBar[];
  trend?: number;
  className?: string;
}

const BAR_COLORS: Record<string, string> = {
  PRESENT: 'bg-blue-500',
  LATE: 'bg-amber-400',
  ABSENT: 'bg-slate-200',
  EXCUSED: 'bg-slate-300',
};

export const AttendanceCard: React.FC<AttendanceCardProps> = ({
  title = "Today's Attendance",
  summary,
  bars,
  trend,
  className,
}) => {
  const hasTrend = trend !== undefined && trend !== null && trend !== 0;
  const trendPositive = (trend ?? 0) > 0;

  return (
    <div className={cn(
      'rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm',
      className,
    )}>
      {/* Header */}
      <div className="flex items-center gap-3 mb-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-100">
          <ClipboardList className="h-4.5 w-4.5 text-slate-500" />
        </div>
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      </div>

      {/* Big number + trend */}
      <div className="flex items-baseline gap-2.5 mb-1">
        <span className="text-4xl font-bold tracking-tight text-slate-900">
          {summary.attendance_rate}%
        </span>
        {hasTrend && (
          <span className={cn(
            'inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-semibold',
            trendPositive
              ? 'bg-emerald-50 text-emerald-600'
              : 'bg-red-50 text-red-500',
          )}>
            {trendPositive ? (
              <TrendingUp className="h-3 w-3" />
            ) : (
              <TrendingDown className="h-3 w-3" />
            )}
            {trendPositive ? '+' : ''}{trend}%
          </span>
        )}
      </div>
      <p className="text-xs text-slate-400 mb-5">Attendance Rate</p>

      {/* Bar chart */}
      {bars.length > 0 && (
        <div className="flex items-end gap-[2px] h-16 mb-5">
          {bars.map((bar, i) => (
            <div
              key={i}
              className={cn(
                'flex-1 rounded-t-sm min-w-[3px] transition-all duration-200',
                BAR_COLORS[bar.status] || 'bg-slate-200',
                bar.status === 'PRESENT' ? 'h-full' : '',
                bar.status === 'LATE' ? 'h-[85%]' : '',
                bar.status === 'ABSENT' ? 'h-[30%]' : '',
                bar.status === 'EXCUSED' ? 'h-[50%]' : '',
              )}
            />
          ))}
        </div>
      )}

      {/* Legend */}
      <div className="flex items-center justify-between pt-4 border-t border-slate-100">
        <LegendItem color="bg-blue-500" label="On-Time" value={`${summary.on_time_pct}%`} />
        <LegendItem color="bg-amber-400" label="Late" value={`${summary.late_pct}%`} />
        <LegendItem color="bg-slate-200" label="Absent" value={`${summary.absent_pct}%`} />
      </div>
    </div>
  );
};

function LegendItem({ color, label, value }: { color: string; label: string; value: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className={cn('h-1.5 w-6 rounded-full', color)} />
      <span className="text-[11px] text-slate-400">{label}</span>
      <span className="text-sm font-bold text-slate-900">{value}</span>
    </div>
  );
}
