import React from 'react';

interface CompletionRingProps {
  value: number;
  size?: number;
  stroke?: number;
  label?: string;
  tone?: 'emerald' | 'blue' | 'amber' | 'slate';
}

const toneColor = {
  emerald: '#10b981',
  blue: '#2563eb',
  amber: '#f59e0b',
  slate: '#475569',
};

export const CompletionRing: React.FC<CompletionRingProps> = ({
  value,
  size = 54,
  stroke = 6,
  label,
  tone = 'emerald',
}) => {
  const safe = Math.max(0, Math.min(100, Math.round(value)));
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const dashOffset = circumference - (safe / 100) * circumference;

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="#e2e8f0"
          strokeWidth={stroke}
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={toneColor[tone]}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
        />
      </svg>
      <span className="absolute text-[11px] font-semibold text-slate-700">{label || `${safe}%`}</span>
    </div>
  );
};
