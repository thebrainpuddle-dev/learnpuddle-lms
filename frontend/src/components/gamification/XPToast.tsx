// src/components/gamification/XPToast.tsx

import { useEffect, useState } from 'react';

interface XPToastProps {
  xpAmount: number;
  reason: string;
  onClose: () => void;
  duration?: number;
}

const REASON_LABELS: Record<string, string> = {
  content_completion: 'Content Completed',
  course_completion: 'Course Completed',
  assignment_submission: 'Assignment Submitted',
  quiz_submission: 'Quiz Completed',
  streak_day: 'Streak Bonus',
  badge_award: 'Badge Award',
  manual_adjustment: 'Admin Adjustment',
};

export default function XPToast({ xpAmount, reason, onClose, duration = 3000 }: XPToastProps) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // Trigger entrance animation on next frame
    requestAnimationFrame(() => setVisible(true));

    const timer = setTimeout(() => {
      setVisible(false);
      setTimeout(onClose, 300); // Wait for exit animation
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onClose]);

  const label = REASON_LABELS[reason] ?? reason.replace(/_/g, ' ');

  return (
    <div
      className={`fixed bottom-6 right-6 z-50 transition-all duration-300 ease-out ${
        visible ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0'
      }`}
    >
      <div className="flex items-center gap-3 bg-green-600 text-white rounded-xl shadow-lg px-5 py-3 min-w-[240px]">
        {/* Star icon */}
        <div className="flex-shrink-0">
          <svg className="h-6 w-6 text-yellow-300" fill="currentColor" viewBox="0 0 24 24">
            <path d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" />
          </svg>
        </div>

        {/* Content */}
        <div className="flex-1">
          <p className="text-lg font-bold">+{xpAmount} XP</p>
          <p className="text-xs text-green-100">{label}</p>
        </div>

        {/* Close button */}
        <button
          onClick={() => {
            setVisible(false);
            setTimeout(onClose, 300);
          }}
          className="flex-shrink-0 p-1 rounded-lg hover:bg-green-500 transition-colors"
        >
          <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>
    </div>
  );
}
