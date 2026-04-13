// src/components/maic/SpeechSubtitles.tsx
//
// Bottom-center overlay bar showing the current speech text (like subtitles).
// Displays agent name prefix in agent color with fade in/out animation.

import React, { useEffect, useState, useRef } from 'react';
import { cn } from '../../lib/utils';

interface SpeechSubtitlesProps {
  text: string | null;
  agentName?: string;
  agentColor?: string;
}

export const SpeechSubtitles: React.FC<SpeechSubtitlesProps> = ({
  text,
  agentName,
  agentColor = '#FFFFFF',
}) => {
  const [visible, setVisible] = useState(false);
  const [displayText, setDisplayText] = useState<string | null>(null);
  const [displayAgent, setDisplayAgent] = useState<string | undefined>(undefined);
  const [displayColor, setDisplayColor] = useState<string>('#FFFFFF');
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }

    if (text) {
      // Update content and show
      setDisplayText(text);
      setDisplayAgent(agentName);
      setDisplayColor(agentColor);
      setVisible(true);
    } else {
      // Fade out, then clear content
      setVisible(false);
      timeoutRef.current = setTimeout(() => {
        setDisplayText(null);
        setDisplayAgent(undefined);
      }, 300); // Match transition duration
    }

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, [text, agentName, agentColor]);

  if (!displayText && !visible) return null;

  return (
    <div
      className={cn(
        'absolute bottom-6 left-1/2 -translate-x-1/2 z-40',
        'max-w-[80%] w-auto',
        'pointer-events-none',
        'transition-opacity duration-300 ease-in-out',
        visible ? 'opacity-100' : 'opacity-0',
      )}
      role="status"
      aria-live="polite"
      aria-label="Speech subtitles"
    >
      <div
        className={cn(
          'rounded-lg px-5 py-3',
          'bg-black/75 backdrop-blur-sm',
          'text-white text-base leading-relaxed',
          'line-clamp-2',
        )}
      >
        {displayAgent && (
          <span
            className="font-semibold mr-2"
            style={{ color: displayColor }}
          >
            {displayAgent}:
          </span>
        )}
        <span>{displayText}</span>
      </div>
    </div>
  );
};
