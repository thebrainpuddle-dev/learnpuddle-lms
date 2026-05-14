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
import { TypewriterText } from './TypewriterText';
import { ThinkingDots } from './ThinkingDots';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useSprintFlag, SPRINT1_FLAGS } from '../../lib/sprintFlags';
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
    const typewriterOn = useSprintFlag(SPRINT1_FLAGS.typewriter);
    const bouncySwapOn = useSprintFlag(SPRINT1_FLAGS.bubbleSwap);
    const thinkingDotsOn = useSprintFlag(SPRINT1_FLAGS.thinkingDots);
    const speechFetchLoading = useMAICStageStore((s) => s.speechFetchLoading);
    // T0.2 — live-playback flag used for the voice-wave animation. When
    // false (between speakers) we keep the bubble on-screen with the last
    // line but drop the wave so it doesn't look like the agent is still
    // talking to themselves.
    const isSpeaking = useMAICStageStore((s) => s.isSpeaking);

    // Sprint 1 · B.4 — 200ms bouncy easing on speaker swap. We keep the
    // legacy spring when the flag is off so we can A/B compare.
    const swapTransition = bouncySwapOn
      ? { duration: 0.2, ease: [0.34, 1.56, 0.64, 1] as [number, number, number, number] }
      : { type: 'spring' as const, stiffness: 300, damping: 28, mass: 0.8 };

    const truncated = truncateSpeech(speechText);
    const showThinking =
      thinkingDotsOn && speechFetchLoading && !speechText;

    return (
      <AnimatePresence mode="wait">
        {active && agent && (
          <motion.div
            key={agent.id}
            initial={{ y: bouncySwapOn ? 16 : 40, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: bouncySwapOn ? 12 : 30, opacity: 0 }}
            transition={swapTransition}
            className={cn(
              // Top-left of the reserved stage chrome below the lesson
              // surface. This keeps speaker status visible without covering
              // slide title/body/image content on short viewports.
              'absolute top-1 left-3 z-30',
              'flex items-center gap-2 sm:gap-3',
              'bg-black/70 backdrop-blur-md',
              'rounded-xl border border-white/10',
              'px-2 py-1.5 sm:px-3 sm:py-2',
              'max-w-[220px] sm:max-w-xs',
              'shadow-lg',
            )}
          >
            {/* Agent avatar (medium size) */}
            <div className="shrink-0">
              <AgentAvatar agent={agent} isSpeaking={isSpeaking} size="sm" />
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
                    active={isSpeaking}
                    color={agent.color}
                    barCount={4}
                    size="sm"
                  />
                </div>
                {showThinking ? (
                  <ThinkingDots color={agent.color} />
                ) : speechText ? (
                  typewriterOn ? (
                    <TypewriterText
                      key={truncated}
                      text={truncated}
                      speedMs={30}
                      as="p"
                      className="text-xs text-gray-300 leading-snug truncate"
                    />
                  ) : (
                    <p className="text-xs text-gray-300 leading-snug truncate">
                      {truncated}
                    </p>
                  )
                ) : null}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    );
  },
);
