// src/components/maic/GenerationVisualizer.tsx
//
// Animated step visualizer for classroom generation progress.
// Shows phase-specific animations (outline → content → actions → saving)
// with scene-level progress tracking, elapsed time, and honest ETA.

import React, { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import type { GenerationPhase } from '../../hooks/useMAICGeneration';
import { cn } from '../../lib/utils';

interface GenerationVisualizerProps {
  phase: GenerationPhase;
  currentSceneIdx: number;
  totalScenes: number;
  progress: number;
  topic?: string;
  /** Timestamp (ms) when generation started — drives the elapsed timer. */
  startedAt?: number;
  /** Tab is currently hidden. Pause the ticking timer to avoid drift. */
  isTabHidden?: boolean;
}

function formatElapsed(ms: number): string {
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}m ${s.toString().padStart(2, '0')}s`;
}

// ─── Phase metadata ──────────────────────────────────────────────────────────

const PHASES: {
  key: GenerationPhase;
  label: string;
  description: string;
  icon: React.ReactNode;
}[] = [
  {
    key: 'outline',
    label: 'Building Outline',
    description: 'Structuring scenes, topics, and flow',
    icon: <OutlineIcon />,
  },
  {
    key: 'content',
    label: 'Creating Slides',
    description: 'Generating visuals, text, and scripts',
    icon: <SlidesIcon />,
  },
  {
    key: 'actions',
    label: 'Choreographing Actions',
    description: 'Planning agent speech, spotlights, and transitions',
    icon: <ActionsIcon />,
  },
  {
    key: 'saving',
    label: 'Saving Classroom',
    description: 'Storing everything securely',
    icon: <SaveIcon />,
  },
];

// ─── Main component ──────────────────────────────────────────────────────────

export const GenerationVisualizer: React.FC<GenerationVisualizerProps> = ({
  phase,
  currentSceneIdx,
  totalScenes,
  progress,
  topic,
  startedAt,
  isTabHidden = false,
}) => {
  const currentPhaseIdx = PHASES.findIndex((p) => p.key === phase);
  const activePhase = PHASES[currentPhaseIdx] || PHASES[0];

  // Tick every second for the elapsed timer. Pause when tab is hidden so
  // the clock doesn't drift off-screen; re-sync from `startedAt` on return.
  const [now, setNow] = useState<number>(() => Date.now());
  useEffect(() => {
    if (!startedAt || isTabHidden) return;
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [startedAt, isTabHidden]);
  const elapsedMs = startedAt ? now - startedAt : 0;

  return (
    <div className="space-y-8">
      {/* Phase indicator pills */}
      <div className="flex items-center justify-center gap-1.5">
        {PHASES.map((p, i) => {
          const isComplete = i < currentPhaseIdx;
          const isActive = i === currentPhaseIdx;

          return (
            <React.Fragment key={p.key}>
              <div
                className={cn(
                  'flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all duration-500',
                  isComplete && 'bg-green-100 text-green-700',
                  isActive && 'bg-indigo-100 text-indigo-700 ring-1 ring-indigo-200',
                  !isComplete && !isActive && 'bg-gray-100 text-gray-400',
                )}
              >
                {isComplete ? (
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path
                      fillRule="evenodd"
                      d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                      clipRule="evenodd"
                    />
                  </svg>
                ) : isActive ? (
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500" />
                  </span>
                ) : (
                  <span className="h-2 w-2 rounded-full bg-gray-300" />
                )}
                <span className="hidden sm:inline">{p.label}</span>
              </div>
              {i < PHASES.length - 1 && (
                <div
                  className={cn(
                    'w-4 h-px transition-colors duration-500',
                    isComplete ? 'bg-green-300' : 'bg-gray-200',
                  )}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Central animation area */}
      <div className="relative flex flex-col items-center">
        {/* Animated icon */}
        <div className="relative mb-5">
          <div className="absolute inset-0 rounded-full bg-indigo-100 animate-[pulse-ring_2s_ease-in-out_infinite]" />
          <div className="relative flex items-center justify-center h-20 w-20 rounded-full bg-gradient-to-br from-indigo-50 to-white border border-indigo-100 shadow-sm">
            <div className="text-indigo-500 animate-[float_3s_ease-in-out_infinite]">
              {activePhase.icon}
            </div>
          </div>
        </div>

        {/* Phase label */}
        <h3 className="text-base font-semibold text-gray-900 mb-1">
          {activePhase.label}
        </h3>
        <p className="text-sm text-gray-500 mb-5 text-center max-w-xs">
          {activePhase.description}
        </p>

        {/* Topic badge */}
        {topic && (
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-gray-50 border border-gray-100 text-xs text-gray-600 mb-5 max-w-[280px]">
            <svg className="w-3 h-3 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.042A8.967 8.967 0 0 0 6 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 0 1 6 18c2.331 0 4.472.89 6.074 2.35M12 6.042a8.967 8.967 0 0 1 6-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0 0 18 18a8.967 8.967 0 0 0-6 2.35" />
            </svg>
            <span className="truncate">{topic}</span>
          </div>
        )}
      </div>

      {/* Scene progress (content/actions phases) */}
      {(phase === 'content' || phase === 'actions') && totalScenes > 0 && (
        <div className="max-w-xs mx-auto space-y-3">
          {/* Scene dots */}
          <div className="flex items-center justify-center gap-1">
            {Array.from({ length: totalScenes }).map((_, i) => {
              const isSceneComplete =
                phase === 'actions'
                  ? i < currentSceneIdx
                  : i < currentSceneIdx;
              const isSceneCurrent = i === currentSceneIdx;

              return (
                <div
                  key={i}
                  className={cn(
                    'rounded-full transition-all duration-300',
                    isSceneCurrent
                      ? 'h-2.5 w-2.5 bg-indigo-500 ring-2 ring-indigo-200 ring-offset-1'
                      : isSceneComplete
                        ? 'h-2 w-2 bg-green-400'
                        : 'h-2 w-2 bg-gray-200',
                  )}
                  title={`Scene ${i + 1}`}
                />
              );
            })}
          </div>

          <p className="text-center text-xs text-gray-500">
            Scene {currentSceneIdx + 1} of {totalScenes}
            <span className="text-gray-300 mx-1">&middot;</span>
            {phase === 'content' ? 'Building slides' : 'Adding interactions'}
          </p>
        </div>
      )}

      {/* Overall progress bar */}
      <div className="max-w-xs mx-auto">
        <div className="flex items-center justify-between text-[11px] text-gray-400 mb-1">
          <span>Overall progress</span>
          <span className="tabular-nums font-medium">{progress}%</span>
        </div>
        <div className="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden">
          <div
            className="h-1.5 rounded-full transition-all duration-700 ease-out bg-gradient-to-r from-indigo-500 to-indigo-400"
            style={{ width: `${progress}%` }}
          />
        </div>
        {startedAt && (
          <div className="flex items-center justify-between text-[11px] text-gray-400 mt-2 tabular-nums">
            <span>Elapsed: {formatElapsed(elapsedMs)}</span>
            <span>Typically 5–10 min</span>
          </div>
        )}
      </div>

      {/* Status footer — honest about wait time + safe to leave tab */}
      <div className="text-center space-y-1">
        <p className="text-[11px] text-gray-400 flex items-center justify-center gap-1.5">
          <span className="inline-flex gap-0.5">
            <span className="h-1 w-1 rounded-full bg-indigo-400 animate-[bounce-dot_1.4s_ease-in-out_infinite]" />
            <span className="h-1 w-1 rounded-full bg-indigo-400 animate-[bounce-dot_1.4s_ease-in-out_0.2s_infinite]" />
            <span className="h-1 w-1 rounded-full bg-indigo-400 animate-[bounce-dot_1.4s_ease-in-out_0.4s_infinite]" />
          </span>
          {isTabHidden ? 'Paused display — still working in background' : 'AI agents are working'}
        </p>
        <p className="text-[10px] text-gray-400">
          Safe to leave this tab open. We'll update when ready.
        </p>
      </div>
    </div>
  );
};

// ─── SVG Icons ───────────────────────────────────────────────────────────────

// ─── Per-phase animated icons (Sprint 2 · A.1) ──────────────────────────────
//
// Each icon has a little motion that tells the story of the phase:
//   - OutlineIcon (scribe): the four outline lines write themselves in
//     sequence, like a pen drafting the agenda.
//   - SlidesIcon (painter): a paint stroke sweeps across the front slide
//     while content lines fade in behind it.
//   - ActionsIcon (choreographer): the speech bubble pulses as though
//     the agent is miming through takes.
//   - SaveIcon: the check mark draws itself in.
// Reduced-motion users get the end state with no movement (motion/react
// respects the media query by default for most transitions).

function OutlineIcon() {
  // T5 — "rotated notepad that flattens on hover" with a cyan scan
  // line sweeping top-to-bottom (the PDF laser from OpenMAIC). Parent
  // handles rotation via the `group` hover trick so we can keep the
  // SVG focused on the motion lines.
  const LINES = [
    { x2: 22, opacity: 1, delay: 0 },
    { x2: 18, opacity: 0.6, delay: 0.3 },
    { x2: 20, opacity: 0.4, delay: 0.6 },
    { x2: 16, opacity: 0.25, delay: 0.9 },
  ];
  return (
    <div className="group relative" style={{ perspective: 500 }}>
      <motion.svg
        className="h-8 w-8"
        fill="none"
        viewBox="0 0 32 32"
        strokeWidth={1.5}
        stroke="currentColor"
        initial={{ rotate: -2 }}
        whileHover={{ rotate: 0 }}
        transition={{ duration: 0.35, ease: [0.21, 1, 0.36, 1] }}
      >
        <rect x="6" y="4" width="20" height="24" rx="2" className="stroke-current" />
        {LINES.map((l, i) => (
          <motion.line
            key={i}
            x1={10}
            y1={10 + i * 4}
            x2={l.x2}
            y2={10 + i * 4}
            className="stroke-current"
            strokeLinecap="round"
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: l.opacity }}
            transition={{
              duration: 0.45,
              delay: l.delay,
              repeat: Infinity,
              repeatDelay: 1.2,
              ease: 'easeInOut',
            }}
          />
        ))}
        {/* Cyan laser scan — sweeps the full notepad, leaves a soft
            trailing glow via a 2-unit-tall gradient strip. */}
        <motion.rect
          x="7"
          width="18"
          height="2"
          rx="1"
          fill="#06B6D4"
          initial={{ y: 4, opacity: 0 }}
          animate={{ y: [4, 26, 26], opacity: [0, 0.75, 0] }}
          transition={{
            duration: 2.5,
            times: [0, 0.85, 1],
            repeat: Infinity,
            ease: 'easeInOut',
          }}
          style={{ mixBlendMode: 'multiply' }}
        />
      </motion.svg>
    </div>
  );
}

function SlidesIcon() {
  // T5 — stacked slides with a glint sweep. Third slide wobbles slightly
  // as if the next slide is landing on the stack.
  return (
    <svg className="h-8 w-8" fill="none" viewBox="0 0 32 32" strokeWidth={1.5} stroke="currentColor" overflow="visible">
      <defs>
        <linearGradient id="maic-gen-glint" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="rgba(255,255,255,0)" />
          <stop offset="50%" stopColor="rgba(255,255,255,0.85)" />
          <stop offset="100%" stopColor="rgba(255,255,255,0)" />
        </linearGradient>
        <clipPath id="maic-gen-slide-front">
          <rect x="5" y="9" width="18" height="14" rx="1.5" />
        </clipPath>
      </defs>
      {/* Back stack (dim) */}
      <rect x="11" y="4" width="16" height="12" rx="1.5" className="stroke-current opacity-20" />
      <rect x="8" y="6" width="18" height="14" rx="1.5" className="stroke-current opacity-40" />
      {/* Wobble next-slide lift */}
      <motion.rect
        x="5" y="9" width="18" height="14" rx="1.5"
        className="stroke-current"
        initial={{ y: 9 }}
        animate={{ y: [9, 8.5, 9] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
      />
      {/* Content lines + thumbnail placeholder */}
      <motion.line
        x1="9" x2="15" y1="14" y2="14"
        className="stroke-current opacity-60"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.6, delay: 0.2, repeat: Infinity, repeatDelay: 1 }}
      />
      <motion.line
        x1="9" x2="19" y1="17" y2="17"
        className="stroke-current opacity-40"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.6, delay: 0.5, repeat: Infinity, repeatDelay: 1 }}
      />
      <rect x="16" y="12" width="4" height="3" rx="0.5" className="stroke-current opacity-50" />
      {/* Diagonal glint sweep across the front slide */}
      <g clipPath="url(#maic-gen-slide-front)">
        <motion.rect
          width="8"
          height="28"
          y="6"
          fill="url(#maic-gen-glint)"
          initial={{ x: -10 }}
          animate={{ x: 32 }}
          transition={{
            duration: 2.2,
            repeat: Infinity,
            repeatDelay: 0.6,
            ease: 'easeInOut',
          }}
          style={{ transform: 'skewX(-20deg)', transformOrigin: '0 0' }}
        />
      </g>
    </svg>
  );
}

function ActionsIcon() {
  // T5 — two agents exchanging speech ripples. The ripple rings grow
  // and fade, one from each agent, offset in time so they feel
  // conversational rather than simultaneous.
  return (
    <svg className="h-8 w-8" fill="none" viewBox="0 0 32 32" strokeWidth={1.5} stroke="currentColor">
      {/* Agent A (left) */}
      <circle cx="9" cy="13" r="3" className="stroke-current" />
      <path d="M5 24c0-2.2 1.8-4 4-4s4 1.8 4 4" className="stroke-current" />
      {/* Agent B (right) */}
      <circle cx="23" cy="13" r="3" className="stroke-current opacity-80" />
      <path d="M19 24c0-2.2 1.8-4 4-4s4 1.8 4 4" className="stroke-current opacity-80" />
      {/* Ripple from A */}
      <motion.circle
        cx="9" cy="13" r="3"
        className="stroke-current"
        initial={{ scale: 1, opacity: 0.6 }}
        animate={{ scale: [1, 2.6, 2.6], opacity: [0.6, 0, 0] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: 'easeOut' }}
        style={{ transformOrigin: '9px 13px' }}
      />
      {/* Ripple from B, offset */}
      <motion.circle
        cx="23" cy="13" r="3"
        className="stroke-current"
        initial={{ scale: 1, opacity: 0.6 }}
        animate={{ scale: [1, 2.6, 2.6], opacity: [0.6, 0, 0] }}
        transition={{ duration: 1.8, repeat: Infinity, ease: 'easeOut', delay: 0.9 }}
        style={{ transformOrigin: '23px 13px' }}
      />
      {/* Tiny "spark" in the middle to signal handoff */}
      <motion.circle
        cx="16" cy="13" r="1"
        className="fill-current"
        initial={{ opacity: 0, scale: 0.5 }}
        animate={{ opacity: [0, 0.8, 0], scale: [0.5, 1.4, 0.5] }}
        transition={{ duration: 1.4, repeat: Infinity, ease: 'easeInOut', delay: 0.45 }}
      />
    </svg>
  );
}

function SaveIcon() {
  return (
    <svg className="h-8 w-8" fill="none" viewBox="0 0 32 32" strokeWidth={1.5} stroke="currentColor">
      <path d="M6 8a2 2 0 012-2h12l6 6v12a2 2 0 01-2 2H8a2 2 0 01-2-2V8z" className="stroke-current" />
      <path d="M20 6v6h6" className="stroke-current opacity-60" />
      {/* Self-drawing check mark */}
      <motion.path
        d="M12 18l3 3 5-6"
        className="stroke-current"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.7, repeat: Infinity, repeatDelay: 0.8, ease: 'easeOut' }}
      />
    </svg>
  );
}
