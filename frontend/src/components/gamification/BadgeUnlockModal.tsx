// src/components/gamification/BadgeUnlockModal.tsx

import { useEffect, useState } from 'react';

interface BadgeUnlockModalProps {
  badge: { name: string; description: string; icon: string; color: string; category: string };
  isOpen: boolean;
  onClose: () => void;
}

const CAT_COLORS: Record<string, string> = {
  milestone: 'bg-blue-100 text-blue-800', streak: 'bg-orange-100 text-orange-800',
  completion: 'bg-green-100 text-green-800', skill: 'bg-purple-100 text-purple-800',
  special: 'bg-yellow-100 text-yellow-800',
};

export default function BadgeUnlockModal({ badge, isOpen, onClose }: BadgeUnlockModalProps) {
  const [animate, setAnimate] = useState(false);

  useEffect(() => {
    if (isOpen) requestAnimationFrame(() => setAnimate(true));
    else setAnimate(false);
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center p-4 transition-colors duration-300 ${animate ? 'bg-black/60' : 'bg-black/0'}`}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div className={`bg-white rounded-2xl shadow-2xl max-w-sm w-full p-8 text-center transition-all duration-500 ${animate ? 'scale-100 opacity-100' : 'scale-75 opacity-0'}`}>
        {/* Confetti dots */}
        <div className="relative mb-6">
          <div className="absolute -top-2 left-1/4 h-2 w-2 rounded-full bg-yellow-400 animate-bounce" />
          <div className="absolute -top-3 right-1/3 h-1.5 w-1.5 rounded-full bg-pink-400 animate-bounce" style={{ animationDelay: '200ms' }} />
          <div className="absolute top-0 right-1/4 h-2 w-2 rounded-full bg-blue-400 animate-bounce" style={{ animationDelay: '400ms' }} />
          <div className="absolute -top-1 left-1/3 h-1.5 w-1.5 rounded-full bg-green-400 animate-bounce" style={{ animationDelay: '100ms' }} />
          {/* Badge icon */}
          <div
            className="mx-auto h-24 w-24 rounded-full flex items-center justify-center text-white text-4xl shadow-lg ring-4 ring-offset-2"
            style={{ backgroundColor: badge.color || '#6366f1', '--tw-ring-color': badge.color || '#6366f1' } as React.CSSProperties}
          >
            {badge.icon || (
              <svg className="h-12 w-12" fill="currentColor" viewBox="0 0 24 24">
                <path d="M11.48 3.499a.562.562 0 011.04 0l2.125 5.111a.563.563 0 00.475.345l5.518.442c.499.04.701.663.321.988l-4.204 3.602a.563.563 0 00-.182.557l1.285 5.385a.562.562 0 01-.84.61l-4.725-2.885a.563.563 0 00-.586 0L6.982 20.54a.562.562 0 01-.84-.61l1.285-5.386a.562.562 0 00-.182-.557l-4.204-3.602a.563.563 0 01.321-.988l5.518-.442a.563.563 0 00.475-.345L11.48 3.5z" />
              </svg>
            )}
          </div>
        </div>
        <h2 className="text-2xl font-bold text-gray-900 mb-1">Badge Unlocked!</h2>
        <p className="text-xl font-semibold mt-3" style={{ color: badge.color || '#6366f1' }}>{badge.name}</p>
        {badge.description && <p className="text-sm text-gray-500 mt-2">{badge.description}</p>}
        <div className="mt-3">
          <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium ${CAT_COLORS[badge.category] ?? 'bg-gray-100 text-gray-800'}`}>
            {badge.category}
          </span>
        </div>
        <button
          onClick={onClose}
          className="mt-6 w-full px-6 py-3 bg-indigo-600 text-white text-sm font-semibold rounded-xl hover:bg-indigo-700 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
        >
          Awesome!
        </button>
      </div>
    </div>
  );
}
