// src/components/maic/GenerationVisualizer.tsx
//
// Animated step visualizer for classroom generation progress.
// Shows phase-specific animations (outline → content → actions → saving)
// with scene-level progress tracking.

import React from 'react';
import type { GenerationPhase } from '../../hooks/useMAICGeneration';
import { cn } from '../../lib/utils';

interface GenerationVisualizerProps {
  phase: GenerationPhase;
  currentSceneIdx: number;
  totalScenes: number;
  progress: number;
  topic?: string;
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
}) => {
  const currentPhaseIdx = PHASES.findIndex((p) => p.key === phase);
  const activePhase = PHASES[currentPhaseIdx] || PHASES[0];

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
      </div>

      {/* "AI is working" footer */}
      <p className="text-center text-[11px] text-gray-400 flex items-center justify-center gap-1.5">
        <span className="inline-flex gap-0.5">
          <span className="h-1 w-1 rounded-full bg-indigo-400 animate-[bounce-dot_1.4s_ease-in-out_infinite]" />
          <span className="h-1 w-1 rounded-full bg-indigo-400 animate-[bounce-dot_1.4s_ease-in-out_0.2s_infinite]" />
          <span className="h-1 w-1 rounded-full bg-indigo-400 animate-[bounce-dot_1.4s_ease-in-out_0.4s_infinite]" />
        </span>
        AI agents are working
      </p>
    </div>
  );
};

// ─── SVG Icons ───────────────────────────────────────────────────────────────

function OutlineIcon() {
  return (
    <svg className="h-8 w-8" fill="none" viewBox="0 0 32 32" strokeWidth={1.5} stroke="currentColor">
      <rect x="6" y="4" width="20" height="24" rx="2" className="stroke-current" />
      <line x1="10" y1="10" x2="22" y2="10" className="stroke-current" />
      <line x1="10" y1="14" x2="18" y2="14" className="stroke-current opacity-60" />
      <line x1="10" y1="18" x2="20" y2="18" className="stroke-current opacity-40" />
      <line x1="10" y1="22" x2="16" y2="22" className="stroke-current opacity-20" />
    </svg>
  );
}

function SlidesIcon() {
  return (
    <svg className="h-8 w-8" fill="none" viewBox="0 0 32 32" strokeWidth={1.5} stroke="currentColor">
      {/* Back slide */}
      <rect x="8" y="6" width="18" height="14" rx="1.5" className="stroke-current opacity-30" />
      {/* Front slide */}
      <rect x="5" y="9" width="18" height="14" rx="1.5" className="stroke-current" />
      {/* Content lines */}
      <line x1="9" y1="14" x2="15" y2="14" className="stroke-current opacity-60" />
      <line x1="9" y1="17" x2="19" y2="17" className="stroke-current opacity-40" />
      {/* Image placeholder */}
      <rect x="16" y="12" width="4" height="3" rx="0.5" className="stroke-current opacity-50" />
    </svg>
  );
}

function ActionsIcon() {
  return (
    <svg className="h-8 w-8" fill="none" viewBox="0 0 32 32" strokeWidth={1.5} stroke="currentColor">
      {/* Agent head */}
      <circle cx="16" cy="11" r="4" className="stroke-current" />
      {/* Body */}
      <path d="M10 24c0-3.314 2.686-6 6-6s6 2.686 6 6" className="stroke-current" />
      {/* Speech bubble */}
      <path d="M22 8h6v4h-4l-2 2v-2" className="stroke-current opacity-60" fill="none" />
      {/* Sparkle */}
      <path d="M6 6l1 2 1-2 1 2-1-2-1-2-1 2z" className="stroke-current opacity-40" fill="currentColor" />
    </svg>
  );
}

function SaveIcon() {
  return (
    <svg className="h-8 w-8" fill="none" viewBox="0 0 32 32" strokeWidth={1.5} stroke="currentColor">
      <path d="M6 8a2 2 0 012-2h12l6 6v12a2 2 0 01-2 2H8a2 2 0 01-2-2V8z" className="stroke-current" />
      <path d="M20 6v6h6" className="stroke-current opacity-60" />
      <circle cx="16" cy="18" r="3" className="stroke-current" />
    </svg>
  );
}
