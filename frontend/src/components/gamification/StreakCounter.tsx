// src/components/gamification/StreakCounter.tsx

interface StreakCounterProps {
  currentStreak: number;
  longestStreak: number;
  className?: string;
}

export default function StreakCounter({ currentStreak, longestStreak, className = '' }: StreakCounterProps) {
  const getFireStyle = () => {
    if (currentStreak >= 10) return { size: 'h-6 w-6', color: 'text-red-500', glow: 'drop-shadow-[0_0_6px_rgba(239,68,68,0.5)]' };
    if (currentStreak >= 5) return { size: 'h-5 w-5', color: 'text-orange-500', glow: '' };
    if (currentStreak >= 1) return { size: 'h-4 w-4', color: 'text-orange-400', glow: '' };
    return { size: 'h-4 w-4', color: 'text-gray-400', glow: '' };
  };

  const style = getFireStyle();

  return (
    <div className={`inline-flex items-center gap-1.5 ${className}`}>
      <svg
        className={`${style.size} ${style.color} ${style.glow} transition-all`}
        fill={currentStreak > 0 ? 'currentColor' : 'none'}
        stroke={currentStreak === 0 ? 'currentColor' : 'none'}
        strokeWidth={currentStreak === 0 ? 2 : 0}
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M15.362 5.214A8.252 8.252 0 0112 21 8.25 8.25 0 016.038 7.048 8.287 8.287 0 009 9.6a8.983 8.983 0 013.361-6.867 8.21 8.21 0 003 2.48z"
        />
      </svg>
      <span className="text-sm font-medium text-gray-700">
        {currentStreak} day{currentStreak !== 1 ? 's' : ''}
      </span>
      <span className="text-xs text-gray-400" title={`Best: ${longestStreak} days`}>
        (best: {longestStreak})
      </span>
    </div>
  );
}
