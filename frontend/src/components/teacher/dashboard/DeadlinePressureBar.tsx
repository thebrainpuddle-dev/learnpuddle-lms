import React from 'react';

interface DeadlinePressureBarProps {
  overallProgress: number;
  upcomingDeadlines: number;
  overdueDeadlines: number;
}

function getPressureScore(overallProgress: number, upcomingDeadlines: number, overdueDeadlines: number) {
  const pacePenalty = Math.max(0, 100 - overallProgress);
  const upcomingPenalty = upcomingDeadlines * 6;
  const overduePenalty = overdueDeadlines * 15;
  return Math.max(0, Math.min(100, Math.round(pacePenalty + upcomingPenalty + overduePenalty)));
}

export const DeadlinePressureBar: React.FC<DeadlinePressureBarProps> = ({
  overallProgress,
  upcomingDeadlines,
  overdueDeadlines,
}) => {
  const pressure = getPressureScore(overallProgress, upcomingDeadlines, overdueDeadlines);
  const calm = 100 - pressure;
  const isCritical = pressure >= 66;
  const isWarning = pressure >= 33 && pressure < 66;

  const headline = isCritical
    ? 'Deadline pressure is high'
    : isWarning
      ? 'Deadline pressure is moderate'
      : 'You are on track';

  const hint = isCritical
    ? 'Focus on the nearest items first. Finish one lesson now.'
    : isWarning
      ? 'Complete one module today to move this bar into green.'
      : 'Great pace. Keep your streak alive.';

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-900">{headline}</p>
          <p className="text-xs text-slate-500">{hint}</p>
        </div>
        <span
          className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
            isCritical
              ? 'bg-rose-100 text-rose-700'
              : isWarning
                ? 'bg-amber-100 text-amber-700'
                : 'bg-emerald-100 text-emerald-700'
          }`}
        >
          {calm}% calm
        </span>
      </div>
      <div className="relative h-4 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all duration-700 ${
            isCritical
              ? 'bg-gradient-to-r from-rose-500 to-rose-400'
              : isWarning
                ? 'bg-gradient-to-r from-amber-500 to-amber-400'
                : 'bg-gradient-to-r from-emerald-500 to-emerald-400'
          }`}
          style={{ width: `${calm}%` }}
        />
        <div
          className="pointer-events-none absolute inset-0 opacity-30"
          style={{
            backgroundImage:
              'repeating-linear-gradient(120deg, rgba(255,255,255,0.4) 0 8px, rgba(255,255,255,0.05) 8px 16px)',
            animation: 'lp-pressure-flow 1.6s linear infinite',
          }}
        />
      </div>
      <style>{`
        @keyframes lp-pressure-flow {
          from { transform: translateX(0); }
          to { transform: translateX(24px); }
        }
      `}</style>
    </div>
  );
};
