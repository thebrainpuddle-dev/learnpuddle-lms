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
  /** Secondary live text (e.g., from discussion/roundtable) */
  liveText?: string | null;
  liveAgentName?: string;
  liveAgentColor?: string;
}

export const SpeechSubtitles: React.FC<SpeechSubtitlesProps> = ({
  text,
  agentName,
  agentColor = '#FFFFFF',
  liveText,
  liveAgentName,
  liveAgentColor = '#10B981',
}) => {
  // Prefer live text (discussion) over lecture text when both present
  const activeText = liveText || text;
  const activeName = liveText ? liveAgentName : agentName;
  const activeColor = liveText ? liveAgentColor : agentColor;
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

    if (activeText) {
      // Update content and show
      setDisplayText(activeText);
      setDisplayAgent(activeName);
      setDisplayColor(activeColor);
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
  }, [activeText, activeName, activeColor]);

  if (!displayText && !visible) return null;

  return (
    <div
      className={cn(
        'flex justify-center px-4 pointer-events-none',
        'transition-all duration-300 ease-in-out',
        visible ? 'py-2 opacity-100' : 'py-0 opacity-0 h-0 overflow-hidden',
      )}
      role="status"
      aria-live="polite"
      aria-label="Speech subtitles"
    >
      <div className="bg-gray-900/80 backdrop-blur-sm rounded-xl px-5 py-2.5 shadow-xl max-w-[80%]">
        {displayAgent && (
          <p className="text-[10px] font-semibold mb-0.5" style={{ color: displayColor }}>
            {displayAgent}
          </p>
        )}
        <p className="text-sm text-white leading-relaxed line-clamp-2">{displayText}</p>
      </div>
    </div>
  );
};
