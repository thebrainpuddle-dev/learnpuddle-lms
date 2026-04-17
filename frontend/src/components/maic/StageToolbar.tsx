// src/components/maic/StageToolbar.tsx
//
// Minimal top toolbar for the MAIC stage: speed cycle, settings dropdown,
// fullscreen. That's it.
//
// What used to live here and was removed (intentional):
//   - View-mode toggle (Slides/Whiteboard/Split View) — split view never
//     worked; whiteboard now opens automatically during playback when an
//     agent fires a `wb_open` action. No manual mode switch needed.
//   - Whiteboard drawing tools — see above.
//   - Stop / Play buttons — single canonical control lives in SlideNavigator
//     at the bottom.
//   - Discussion toggle — discussion triggers automatically when a
//     `discussion` action fires during playback; chat panel covers manual Q&A.
//   - Notes toggle — merged into the ChatPanel's "Lecture Notes" tab.

import React, { useState, useCallback } from 'react';
import {
  Settings,
  Maximize,
  Minimize,
  Volume2,
  VolumeX,
  SkipForward,
} from 'lucide-react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useMAICSettingsStore } from '../../stores/maicSettingsStore';
import type { MAICPlayerRole, MAICSlideTransition } from '../../types/maic';
import { cn } from '../../lib/utils';
import { SettingsDialog } from './settings';

interface StageToolbarProps {
  role: MAICPlayerRole;
}

const PLAYBACK_SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

/** Inline speed cycle (click 1x to advance): 1 → 1.25 → 1.5 → 2 → 0.5 → 0.75 → 1 */
const INLINE_SPEED_CYCLE = [1, 1.25, 1.5, 2, 0.5, 0.75] as const;

const SLIDE_TRANSITIONS: { value: MAICSlideTransition; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'fade', label: 'Fade' },
  { value: 'slideLeft', label: 'Left' },
  { value: 'slideRight', label: 'Right' },
];

export const StageToolbar = React.memo<StageToolbarProps>(function StageToolbar({
  role: _role,
}) {
  const isFullscreen = useMAICStageStore((s) => s.isFullscreen);
  const setFullscreen = useMAICStageStore((s) => s.setFullscreen);

  const audioVolume = useMAICSettingsStore((s) => s.audioVolume);
  const setAudioVolume = useMAICSettingsStore((s) => s.setAudioVolume);
  const showChatPanel = useMAICSettingsStore((s) => s.showChatPanel);
  const setShowChatPanel = useMAICSettingsStore((s) => s.setShowChatPanel);
  const playbackSpeed = useMAICSettingsStore((s) => s.playbackSpeed);
  const setPlaybackSpeed = useMAICSettingsStore((s) => s.setPlaybackSpeed);
  const autoPlay = useMAICSettingsStore((s) => s.autoPlay);
  const setAutoPlay = useMAICSettingsStore((s) => s.setAutoPlay);
  const slideTransition = useMAICSettingsStore((s) => s.slideTransition);
  const setSlideTransition = useMAICSettingsStore((s) => s.setSlideTransition);

  const [showSettings, setShowSettings] = useState(false);
  const [showSettingsDialog, setShowSettingsDialog] = useState(false);

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().then(() => setFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setFullscreen(false)).catch(() => {});
    }
  }, [setFullscreen]);

  const handleCycleSpeed = useCallback(() => {
    const currentIdx = INLINE_SPEED_CYCLE.indexOf(playbackSpeed as typeof INLINE_SPEED_CYCLE[number]);
    const nextIdx = currentIdx === -1 ? 0 : (currentIdx + 1) % INLINE_SPEED_CYCLE.length;
    setPlaybackSpeed(INLINE_SPEED_CYCLE[nextIdx]);
  }, [playbackSpeed, setPlaybackSpeed]);

  return (
    <div className="flex items-center justify-end gap-1 px-3 py-2 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
      {/* Inline speed cycle */}
      <button
        type="button"
        onClick={handleCycleSpeed}
        className="text-[10px] px-1.5 py-1 rounded-md bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 tabular-nums font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500"
        title={`Playback speed: ${playbackSpeed}x (click to cycle)`}
        aria-label={`Playback speed ${playbackSpeed}x`}
      >
        {playbackSpeed}x
      </button>

      {/* Divider */}
      <div className="w-px h-5 bg-gray-200 dark:bg-gray-700 mx-1" aria-hidden="true" />

      {/* Settings dropdown */}
      <div className="relative">
        <button
          type="button"
          onClick={() => setShowSettings((v) => !v)}
          className={cn(
            'p-1.5 rounded-md transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-primary-500',
            showSettings
              ? 'bg-gray-200 text-gray-900 dark:bg-gray-700 dark:text-gray-100'
              : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-800',
          )}
          title="Settings"
          aria-label="Settings"
          aria-expanded={showSettings}
        >
          <Settings className="h-4 w-4" />
        </button>

        {showSettings && (
          <div className="absolute top-full right-0 mt-1 w-56 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-20 p-3 space-y-3">
            {/* Volume */}
            <div>
              <label className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
                <span className="flex items-center gap-1">
                  {audioVolume > 0 ? <Volume2 className="h-3 w-3" /> : <VolumeX className="h-3 w-3" />}
                  Volume
                </span>
                <span className="tabular-nums">{Math.round(audioVolume * 100)}%</span>
              </label>
              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={audioVolume}
                onChange={(e) => setAudioVolume(parseFloat(e.target.value))}
                className="w-full h-1.5 bg-gray-200 dark:bg-gray-700 rounded-full appearance-none cursor-pointer accent-primary-600"
                aria-label="Audio volume"
              />
            </div>

            {/* Playback speed */}
            <div>
              <label className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
                <span className="flex items-center gap-1">
                  <SkipForward className="h-3 w-3" />
                  Speed
                </span>
                <span className="tabular-nums">{playbackSpeed}x</span>
              </label>
              <div className="flex items-center gap-1">
                {PLAYBACK_SPEEDS.map((speed) => (
                  <button
                    key={speed}
                    type="button"
                    onClick={() => setPlaybackSpeed(speed)}
                    className={cn(
                      'flex-1 text-[10px] py-1 rounded transition-colors',
                      playbackSpeed === speed
                        ? 'bg-primary-100 text-primary-700 font-medium dark:bg-primary-900 dark:text-primary-300'
                        : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700',
                    )}
                  >
                    {speed}x
                  </button>
                ))}
              </div>
            </div>

            {/* Slide transition */}
            <div>
              <label className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
                <span>Slide Transition</span>
                <span className="tabular-nums capitalize">{slideTransition}</span>
              </label>
              <div className="flex flex-wrap items-center gap-1">
                {SLIDE_TRANSITIONS.map(({ value, label }) => (
                  <button
                    key={value}
                    type="button"
                    onClick={() => setSlideTransition(value)}
                    className={cn(
                      'text-[10px] px-1.5 py-1 rounded transition-colors',
                      slideTransition === value
                        ? 'bg-primary-100 text-primary-700 font-medium dark:bg-primary-900 dark:text-primary-300'
                        : 'text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700',
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {/* Toggles */}
            <div className="space-y-2 border-t border-gray-100 dark:border-gray-700 pt-2">
              <label className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 cursor-pointer">
                <span>Auto-play slides</span>
                <input
                  type="checkbox"
                  checked={autoPlay}
                  onChange={(e) => setAutoPlay(e.target.checked)}
                  className="h-3.5 w-3.5 rounded text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600"
                />
              </label>
              <label className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 cursor-pointer">
                <span>Show chat panel</span>
                <input
                  type="checkbox"
                  checked={showChatPanel}
                  onChange={(e) => setShowChatPanel(e.target.checked)}
                  className="h-3.5 w-3.5 rounded text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600"
                />
              </label>
            </div>

            {/* Keyboard shortcuts */}
            <div className="border-t border-gray-100 dark:border-gray-700 pt-2">
              <p className="text-[10px] text-gray-400 mb-1">Keyboard Shortcuts</p>
              <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px] text-gray-500 dark:text-gray-400">
                <span>Space</span><span>Play/Pause</span>
                <span>Arrow keys</span><span>Navigate</span>
                <span>F11</span><span>Fullscreen</span>
                <span>M</span><span>Mute</span>
              </div>
            </div>

            {/* All settings */}
            <div className="border-t border-gray-100 dark:border-gray-700 pt-2">
              <button
                type="button"
                onClick={() => {
                  setShowSettings(false);
                  setShowSettingsDialog(true);
                }}
                className="w-full text-left text-xs text-primary-600 hover:text-primary-700 font-medium transition-colors"
              >
                All Settings...
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Fullscreen */}
      <button
        type="button"
        onClick={toggleFullscreen}
        className={cn(
          'p-1.5 rounded-md transition-colors',
          'focus:outline-none focus:ring-2 focus:ring-primary-500',
          'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-800',
        )}
        title="Fullscreen (F11)"
        aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
      >
        {isFullscreen ? <Minimize className="h-4 w-4" /> : <Maximize className="h-4 w-4" />}
      </button>

      {/* Settings dialog */}
      <SettingsDialog open={showSettingsDialog} onClose={() => setShowSettingsDialog(false)} />
    </div>
  );
});
