// src/components/common/LiveAnnouncer.tsx
/**
 * ARIA live region for announcing dynamic content to screen readers.
 * 
 * Uses the aria-live attribute to communicate changes without focus.
 * Includes both polite and assertive announcement regions.
 */

import React, { createContext, useCallback, useContext, useState } from 'react';

interface LiveAnnouncerContextType {
  /** Announce a message politely (waits for idle) */
  announce: (message: string) => void;
  /** Announce a message assertively (interrupts) */
  announceAssertive: (message: string) => void;
}

const LiveAnnouncerContext = createContext<LiveAnnouncerContextType | null>(null);

export const useLiveAnnouncer = (): LiveAnnouncerContextType => {
  const context = useContext(LiveAnnouncerContext);
  if (!context) {
    throw new Error('useLiveAnnouncer must be used within LiveAnnouncerProvider');
  }
  return context;
};

interface LiveAnnouncerProviderProps {
  children: React.ReactNode;
}

export const LiveAnnouncerProvider: React.FC<LiveAnnouncerProviderProps> = ({
  children,
}) => {
  const [politeMessage, setPoliteMessage] = useState('');
  const [assertiveMessage, setAssertiveMessage] = useState('');

  const clearMessage = useCallback((setter: React.Dispatch<React.SetStateAction<string>>) => {
    setTimeout(() => setter(''), 1000);
  }, []);

  const announce = useCallback((message: string) => {
    // Clear and set to trigger re-announcement of same message
    setPoliteMessage('');
    setTimeout(() => {
      setPoliteMessage(message);
      clearMessage(setPoliteMessage);
    }, 50);
  }, [clearMessage]);

  const announceAssertive = useCallback((message: string) => {
    setAssertiveMessage('');
    setTimeout(() => {
      setAssertiveMessage(message);
      clearMessage(setAssertiveMessage);
    }, 50);
  }, [clearMessage]);

  return (
    <LiveAnnouncerContext.Provider value={{ announce, announceAssertive }}>
      {children}
      
      {/* Polite announcements (e.g., status updates) */}
      <div
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="sr-only"
      >
        {politeMessage}
      </div>

      {/* Assertive announcements (e.g., errors, alerts) */}
      <div
        role="alert"
        aria-live="assertive"
        aria-atomic="true"
        className="sr-only"
      >
        {assertiveMessage}
      </div>
    </LiveAnnouncerContext.Provider>
  );
};

export default LiveAnnouncerProvider;
