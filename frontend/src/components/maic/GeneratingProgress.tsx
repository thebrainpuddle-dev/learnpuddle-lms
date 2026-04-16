// src/components/maic/GeneratingProgress.tsx
//
// Generation progress indicator for the classroom creation flow.
// Shows overall progress bar, stage label with animated dots, per-scene
// status icons, and estimated time remaining.

import React, { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { Loader2, CheckCircle, XCircle } from 'lucide-react';
import { cn } from '../../lib/utils';

// ─── Types ───────────────────────────────────────────────────────────────────

export interface SceneProgress {
  title: string;
  status: 'pending' | 'generating' | 'complete' | 'error';
}

export interface GeneratingProgressProps {
  stage: string;
  current: number;
  total: number;
  message: string;
  scenes?: SceneProgress[];
  className?: string;
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getProgressColor(pct: number): string {
  if (pct < 33) return 'bg-indigo-500';
  if (pct < 66) return 'bg-amber-500';
  return 'bg-green-500';
}

function getProgressTrackColor(pct: number): string {
  if (pct < 33) return 'bg-indigo-100';
  if (pct < 66) return 'bg-amber-100';
  return 'bg-green-100';
}

function formatETA(seconds: number): string {
  if (seconds <= 0) return 'Almost done';
  if (seconds < 60) return `~${seconds}s remaining`;
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `~${mins}m ${secs}s remaining`;
}

// ─── Animated Dots ───────────────────────────────────────────────────────────

const AnimatedDots: React.FC = () => {
  const [dotCount, setDotCount] = useState(1);

  useEffect(() => {
    const interval = setInterval(() => {
      setDotCount((c) => (c % 3) + 1);
    }, 500);
    return () => clearInterval(interval);
  }, []);

  return (
    <span className="inline-block w-4 text-left">
      {'.'.repeat(dotCount)}
    </span>
  );
};

// ─── Scene Status Icon ──────────────────────────────────────────────────────

const SceneStatusIcon: React.FC<{ status: SceneProgress['status'] }> = ({ status }) => {
  switch (status) {
    case 'complete':
      return <CheckCircle className="h-4 w-4 text-green-500 shrink-0" />;
    case 'error':
      return <XCircle className="h-4 w-4 text-red-500 shrink-0" />;
    case 'generating':
      return <Loader2 className="h-4 w-4 text-indigo-500 animate-spin shrink-0" />;
    case 'pending':
    default:
      return (
        <span className="flex items-center justify-center h-4 w-4 shrink-0">
          <span className="h-2 w-2 rounded-full bg-gray-300" />
        </span>
      );
  }
};

// ─── Component ───────────────────────────────────────────────────────────────

export const GeneratingProgress = React.memo<GeneratingProgressProps>(
  function GeneratingProgress({ stage, current, total, message, scenes, className }) {
    const pct = total > 0 ? Math.round((current / total) * 100) : 0;
    const etaSeconds = (total - current) * 3;
    const completedScenes = scenes?.filter((s) => s.status === 'complete').length ?? 0;
    const totalScenes = scenes?.length ?? 0;

    return (
      <div className={cn('rounded-xl border border-gray-200 bg-white p-4 shadow-sm', className)}>
        {/* Header: stage + percentage */}
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold text-gray-800 flex items-center">
            {stage}
            <AnimatedDots />
          </h3>
          <span className="text-xs font-medium text-gray-500 tabular-nums">
            {pct}%
          </span>
        </div>

        {/* Progress bar */}
        <div className={cn('h-2 rounded-full overflow-hidden', getProgressTrackColor(pct))}>
          <motion.div
            className={cn('h-full rounded-full', getProgressColor(pct))}
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ type: 'spring', stiffness: 60, damping: 20 }}
          />
        </div>

        {/* Message + ETA */}
        <div className="flex items-center justify-between mt-2">
          <p className="text-xs text-gray-500 truncate mr-2">{message}</p>
          <span className="text-[10px] text-gray-400 whitespace-nowrap tabular-nums">
            {formatETA(etaSeconds)}
          </span>
        </div>

        {/* Scene count badges */}
        {totalScenes > 0 && (
          <div className="flex items-center gap-2 mt-3">
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-indigo-50 text-indigo-600 border border-indigo-100">
              {completedScenes}/{totalScenes} scenes
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-gray-50 text-gray-500 border border-gray-100">
              {current}/{total} slides
            </span>
          </div>
        )}

        {/* Per-scene status list */}
        {scenes && scenes.length > 0 && (
          <div className="mt-3 space-y-1.5 max-h-48 overflow-y-auto">
            {scenes.map((scene, idx) => (
              <div
                key={idx}
                className={cn(
                  'flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs transition-colors',
                  scene.status === 'generating' && 'bg-indigo-50',
                  scene.status === 'complete' && 'bg-green-50/50',
                  scene.status === 'error' && 'bg-red-50/50',
                )}
              >
                <SceneStatusIcon status={scene.status} />
                <span
                  className={cn(
                    'truncate flex-1',
                    scene.status === 'pending' && 'text-gray-400',
                    scene.status === 'generating' && 'text-indigo-700 font-medium',
                    scene.status === 'complete' && 'text-gray-600',
                    scene.status === 'error' && 'text-red-600',
                  )}
                >
                  {scene.title}
                </span>
                <span className="text-[10px] text-gray-300 shrink-0 tabular-nums">
                  {idx + 1}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  },
);
