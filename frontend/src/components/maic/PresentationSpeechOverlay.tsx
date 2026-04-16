// src/components/maic/PresentationSpeechOverlay.tsx
//
// Visual overlay showing the speaking agent with animated speech visualization
// during playback. Enhances the presentation feel by displaying agent identity,
// role, speech wave bars, and a sentence preview at the bottom-left of the viewport.

import React from 'react';
import { motion, AnimatePresence } from 'motion/react';
import type { MAICAgent } from '../../types/maic';
import { AgentAvatar } from './AgentAvatar';
import { VoiceWaveIndicator } from './VoiceWaveIndicator';
import { cn } from '../../lib/utils';

interface PresentationSpeechOverlayProps {
  /** The currently speaking agent */
  agent: MAICAgent | null;
  /** The current speech text */
  speechText: string | null;
  /** Whether speech is active */
  active: boolean;
}

/** Role display labels */
const ROLE_LABELS: Record<string, string> = {
  professor: 'Professor',
  student: 'Student',
  assistant: 'Assistant',
  moderator: 'Moderator',
  teaching_assistant: 'TA',
  student_rep: 'Student Rep',
};

/** Truncate text to roughly 80 characters with ellipsis */
function truncateSpeech(text: string | null, maxLen = 80): string {
  if (!text) return '';
  if (text.length <= maxLen) return text;
  // Try to break at a word boundary
  const truncated = text.slice(0, maxLen);
  const lastSpace = truncated.lastIndexOf(' ');
  return (lastSpace > maxLen * 0.6 ? truncated.slice(0, lastSpace) : truncated) + '\u2026';
}

export const PresentationSpeechOverlay = React.memo<PresentationSpeechOverlayProps>(
  function PresentationSpeechOverlay({ agent, speechText, active }) {
    return (
      <AnimatePresence mode="wait">
        {active && agent && (
          <motion.div
            key={agent.id}
            initial={{ y: 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 30, opacity: 0 }}
            transition={{
              type: 'spring',
              stiffness: 300,
              damping: 28,
              mass: 0.8,
            }}
            className={cn(
              'absolute bottom-6 left-6 z-20',
              'flex items-center gap-3',
              'bg-black/70 backdrop-blur-md',
              'rounded-2xl border border-white/10',
              'px-4 py-3',
              'max-w-sm',
            )}
          >
            {/* Agent avatar (medium size) */}
            <div className="shrink-0">
              <AgentAvatar agent={agent} isSpeaking size="md" />
            </div>

            {/* Agent info + speech preview */}
            <div className="flex flex-col gap-1 min-w-0">
              {/* Name + role row */}
              <div className="flex items-center gap-2">
                <span
                  className="text-sm font-bold leading-tight truncate"
                  style={{ color: agent.color }}
                >
                  {agent.name}
                </span>
                <span className="shrink-0 text-[10px] font-medium text-gray-400 bg-white/10 rounded px-1.5 py-0.5 leading-tight">
                  {ROLE_LABELS[agent.role] || agent.role}
                </span>
              </div>

              {/* Speech wave + text preview row */}
              <div className="flex items-center gap-2">
                <div className="shrink-0">
                  <VoiceWaveIndicator
                    active
                    color={agent.color}
                    barCount={4}
                    size="sm"
                  />
                </div>
                {speechText && (
                  <p className="text-xs text-gray-300 leading-snug truncate">
                    {truncateSpeech(speechText)}
                  </p>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    );
  },
);
