// src/components/chatbot/ChatbotLauncher.tsx
//
// Floating bottom-right launcher for the RAG-backed chatbot Q&A widget.
// Mounts on teacher course-detail pages. Opens/closes the ChatbotPanel. (TASK-061)

import React from 'react';
import {
  BookOpenIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import { useRagChatbotStore } from '../../stores/ragChatbotStore';
import { ChatbotPanel } from './ChatbotPanel';
import { cn } from '../../lib/utils';

interface ChatbotLauncherProps {
  courseId: string;
}

export const ChatbotLauncher: React.FC<ChatbotLauncherProps> = ({ courseId }) => {
  const { status, open, close } = useRagChatbotStore();
  const isOpen = status !== 'IDLE';

  const toggle = () => {
    if (isOpen) {
      close();
    } else {
      open();
    }
  };

  return (
    <>
      {/* Floating launcher button
          Positioned at bottom-6 right-[5.5rem] to avoid overlapping the
          existing ChatWidget (which sits at bottom-6 right-6). */}
      <button
        type="button"
        onClick={toggle}
        className={cn(
          'fixed bottom-6 right-[5.5rem] z-40',
          'h-14 w-14 rounded-full shadow-lg',
          isOpen
            ? 'bg-slate-700 text-white hover:bg-slate-800'
            : 'bg-sky-600 text-white hover:bg-sky-700',
          'flex items-center justify-center',
          'transition-all duration-200 hover:scale-105',
          'focus:outline-none focus:ring-2 focus:ring-sky-500 focus:ring-offset-2',
          // Respect reduced-motion preference
          'motion-reduce:hover:scale-100 motion-reduce:transition-none',
        )}
        title={isOpen ? 'Close Q&A Assistant' : 'Open Q&A Assistant'}
        aria-label={isOpen ? 'Close Course Q&A Assistant' : 'Open Course Q&A Assistant'}
        aria-expanded={isOpen}
        aria-controls="chatbot-panel"
        data-testid="chatbot-launcher"
      >
        {isOpen ? (
          <XMarkIcon className="h-6 w-6" />
        ) : (
          <BookOpenIcon className="h-6 w-6" />
        )}
      </button>

      {/* Slide-in panel — rendered only when open */}
      {isOpen && (
        <div id="chatbot-panel">
          <ChatbotPanel courseId={courseId} />
        </div>
      )}
    </>
  );
};
