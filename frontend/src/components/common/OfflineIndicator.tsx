// components/common/OfflineIndicator.tsx
/**
 * Offline indicator component.
 *
 * Shows a banner when the user is offline.
 */

import React from 'react';
import { useEffect, useState } from 'react';

interface OfflineIndicatorProps {
  className?: string;
}

export const OfflineIndicator: React.FC<OfflineIndicatorProps> = ({ className = '' }) => {
  const [isOnline, setIsOnline] = useState(navigator.onLine);

  useEffect(() => {
    const onOnline = () => setIsOnline(true);
    const onOffline = () => setIsOnline(false);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  if (isOnline) {
    return null;
  }

  return (
    <div
      className={`fixed top-0 left-0 right-0 bg-yellow-500 text-yellow-900 py-2 px-4 text-center text-sm font-medium z-50 ${className}`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center justify-center gap-2">
        <svg
          className="w-4 h-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3"
          />
        </svg>
        <span>You&apos;re offline. Some features may be unavailable.</span>
      </div>
    </div>
  );
};

export default OfflineIndicator;
