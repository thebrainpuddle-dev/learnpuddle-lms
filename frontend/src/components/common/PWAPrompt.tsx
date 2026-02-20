// components/common/PWAPrompt.tsx
/**
 * PWA Install Prompt component.
 *
 * Shows a prompt to install the app when installable.
 * Also shows update notification when a new version is available.
 */

import React, { useState, useEffect } from 'react';
import { usePWA } from '../../hooks/usePWA';

interface PWAPromptProps {
  className?: string;
}

export const PWAPrompt: React.FC<PWAPromptProps> = ({ className = '' }) => {
  const { isInstallable, isUpdateAvailable, installApp, updateApp } = usePWA();
  const [dismissed, setDismissed] = useState(false);
  const [showUpdate, setShowUpdate] = useState(false);

  // Show update notification after a delay
  useEffect(() => {
    if (isUpdateAvailable) {
      const timer = setTimeout(() => setShowUpdate(true), 2000);
      return () => clearTimeout(timer);
    }
  }, [isUpdateAvailable]);

  // Check if user previously dismissed install prompt
  useEffect(() => {
    const dismissedTime = localStorage.getItem('pwa-prompt-dismissed');
    if (dismissedTime) {
      const hoursSince = (Date.now() - parseInt(dismissedTime)) / (1000 * 60 * 60);
      // Show again after 24 hours
      if (hoursSince < 24) {
        setDismissed(true);
      }
    }
  }, []);

  const handleInstall = async () => {
    const installed = await installApp();
    if (!installed) {
      handleDismiss();
    }
  };

  const handleDismiss = () => {
    setDismissed(true);
    localStorage.setItem('pwa-prompt-dismissed', Date.now().toString());
  };

  const handleUpdate = () => {
    updateApp();
  };

  // Install prompt
  if (isInstallable && !dismissed) {
    return (
      <div
        className={`fixed bottom-4 left-4 right-4 sm:left-auto sm:right-4 sm:w-96 bg-white rounded-lg shadow-xl border border-gray-200 p-4 z-50 ${className}`}
        role="alert"
      >
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 w-10 h-10 bg-blue-100 rounded-lg flex items-center justify-center">
            <svg
              className="w-6 h-6 text-blue-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-gray-900">Install LearnPuddle</h3>
            <p className="text-sm text-gray-600 mt-1">
              Install our app for a better experience with offline access.
            </p>
            <div className="flex gap-2 mt-3">
              <button
                onClick={handleInstall}
                className="px-3 py-1.5 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                Install
              </button>
              <button
                onClick={handleDismiss}
                className="px-3 py-1.5 text-sm font-medium text-gray-700 bg-gray-100 rounded-md hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-500"
              >
                Not now
              </button>
            </div>
          </div>
          <button
            onClick={handleDismiss}
            className="flex-shrink-0 text-gray-400 hover:text-gray-600"
            aria-label="Dismiss"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>
      </div>
    );
  }

  // Update notification
  if (showUpdate) {
    return (
      <div
        className={`fixed bottom-4 left-4 right-4 sm:left-auto sm:right-4 sm:w-96 bg-green-50 rounded-lg shadow-xl border border-green-200 p-4 z-50 ${className}`}
        role="alert"
      >
        <div className="flex items-start gap-3">
          <div className="flex-shrink-0 w-10 h-10 bg-green-100 rounded-lg flex items-center justify-center">
            <svg
              className="w-6 h-6 text-green-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
          </div>
          <div className="flex-1">
            <h3 className="text-sm font-semibold text-green-800">Update Available</h3>
            <p className="text-sm text-green-700 mt-1">
              A new version of the app is ready. Refresh to update.
            </p>
            <div className="flex gap-2 mt-3">
              <button
                onClick={handleUpdate}
                className="px-3 py-1.5 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500"
              >
                Update Now
              </button>
              <button
                onClick={() => setShowUpdate(false)}
                className="px-3 py-1.5 text-sm font-medium text-green-700 bg-green-100 rounded-md hover:bg-green-200 focus:outline-none focus:ring-2 focus:ring-green-500"
              >
                Later
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return null;
};

export default PWAPrompt;
