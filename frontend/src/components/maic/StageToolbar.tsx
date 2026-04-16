// src/components/maic/StageToolbar.tsx
//
// Top toolbar for the MAIC stage. Contains view mode toggle, whiteboard
// tool selector (for teachers), playback controls, export, laser pointer,
// discussion mode, settings, and fullscreen controls.

import React, { useState, useCallback } from 'react';
import {
  Presentation,
  PenTool,
  Columns2,
  Highlighter,
  Eraser,
  MousePointer,
  Palette,
  Settings,
  Maximize,
  Minimize,
  Volume2,
  VolumeX,
  SkipForward,
  Play,
  Pause,
  Square,
  MessagesSquare,
} from 'lucide-react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useMAICCanvasStore } from '../../stores/maicCanvasStore';
import { useMAICSettingsStore } from '../../stores/maicSettingsStore';
import type { MAICPlayerRole, MAICSlideTransition, MAICViewMode, WhiteboardToolType } from '../../types/maic';
import { cn } from '../../lib/utils';
import { SettingsDialog } from './settings';

interface StageToolbarProps {
  role: MAICPlayerRole;
  onDiscussionToggle?: () => void;
  discussionActive?: boolean;
  onPlayPause?: () => void;
  onStop?: () => void;
}

const VIEW_MODES: { mode: MAICViewMode; icon: typeof Presentation; label: string }[] = [
  { mode: 'slides', icon: Presentation, label: 'Slides' },
  { mode: 'whiteboard', icon: PenTool, label: 'Whiteboard' },
  { mode: 'split', icon: Columns2, label: 'Split View' },
];

const WHITEBOARD_TOOLS: { tool: WhiteboardToolType; icon: typeof PenTool; label: string }[] = [
  { tool: 'pen', icon: PenTool, label: 'Pen' },
  { tool: 'highlighter', icon: Highlighter, label: 'Highlighter' },
  { tool: 'eraser', icon: Eraser, label: 'Eraser' },
  { tool: 'pointer', icon: MousePointer, label: 'Pointer' },
];

const PRESET_COLORS = [
  '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6', '#EC4899', '#000000', '#FFFFFF',
];

const STROKE_WIDTHS = [1, 2, 4, 6, 8];

const PLAYBACK_SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

/** Ordered cycle for the inline speed button: 1 -> 1.25 -> 1.5 -> 2 -> 0.5 -> 0.75 -> 1 */
const INLINE_SPEED_CYCLE = [1, 1.25, 1.5, 2, 0.5, 0.75] as const;

const SLIDE_TRANSITIONS: { value: MAICSlideTransition; label: string }[] = [
  { value: 'none', label: 'None' },
  { value: 'fade', label: 'Fade' },
  { value: 'slideLeft', label: 'Left' },
  { value: 'slideRight', label: 'Right' },
  { value: 'slideUp', label: 'Up' },
  { value: 'slideDown', label: 'Down' },
  { value: 'zoom', label: 'Zoom' },
  { value: 'flip', label: 'Flip' },
];

/** Notes panel toggle — reads showNotesPanel from the stage store */
function NotesToggleButton() {
  const showNotesPanel = useMAICStageStore((s) => s.showNotesPanel);
  const toggleNotesPanel = useMAICStageStore((s) => s.toggleNotesPanel);

  return (
    <button
      type="button"
      onClick={toggleNotesPanel}
      className={cn(
        'flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors',
        'focus:outline-none focus:ring-2 focus:ring-primary-500',
        showNotesPanel
          ? 'bg-amber-50 text-amber-600'
          : 'text-gray-500 hover:bg-gray-100 hover:text-gray-700',
      )}
      title="Toggle notes (N)"
      aria-label="Toggle notes panel"
      aria-pressed={showNotesPanel}
    >
      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 0 0-9-9Z"
        />
      </svg>
      <span className="hidden sm:inline">Notes</span>
    </button>
  );
}

export const StageToolbar = React.memo<StageToolbarProps>(function StageToolbar({
  role,
  onDiscussionToggle,
  discussionActive = false,
  onPlayPause,
  onStop,
}) {
  const viewMode = useMAICStageStore((s) => s.viewMode);
  const setViewMode = useMAICStageStore((s) => s.setViewMode);
  const isFullscreen = useMAICStageStore((s) => s.isFullscreen);
  const setFullscreen = useMAICStageStore((s) => s.setFullscreen);
  const isPlaying = useMAICStageStore((s) => s.isPlaying);
  const setPlaying = useMAICStageStore((s) => s.setPlaying);

  const activeTool = useMAICCanvasStore((s) => s.activeTool);
  const setTool = useMAICCanvasStore((s) => s.setTool);
  const activeColor = useMAICCanvasStore((s) => s.activeColor);
  const setColor = useMAICCanvasStore((s) => s.setColor);
  const strokeWidth = useMAICCanvasStore((s) => s.strokeWidth);
  const setStrokeWidth = useMAICCanvasStore((s) => s.setStrokeWidth);

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
  const [showColorPicker, setShowColorPicker] = useState(false);

  const showWhiteboardTools = role === 'teacher' && (viewMode === 'whiteboard' || viewMode === 'split');

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().then(() => setFullscreen(true)).catch(() => {});
    } else {
      document.exitFullscreen().then(() => setFullscreen(false)).catch(() => {});
    }
  }, [setFullscreen]);

  const handlePlayPause = useCallback(() => {
    if (onPlayPause) {
      onPlayPause();
    } else {
      setPlaying(!isPlaying);
    }
  }, [isPlaying, setPlaying, onPlayPause]);

  const handleStop = useCallback(() => {
    if (onStop) {
      onStop();
    } else {
      setPlaying(false);
    }
  }, [setPlaying, onStop]);

  const handleCycleSpeed = useCallback(() => {
    const currentIdx = INLINE_SPEED_CYCLE.indexOf(playbackSpeed as typeof INLINE_SPEED_CYCLE[number]);
    const nextIdx = currentIdx === -1 ? 0 : (currentIdx + 1) % INLINE_SPEED_CYCLE.length;
    setPlaybackSpeed(INLINE_SPEED_CYCLE[nextIdx]);
  }, [playbackSpeed, setPlaybackSpeed]);

  return (
    <div className="flex items-center justify-between gap-2 px-3 py-2 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-700">
      {/* Left: View mode toggle */}
      <div className="flex items-center gap-1" role="radiogroup" aria-label="View mode">
        {VIEW_MODES.map(({ mode, icon: Icon, label }) => (
          <button
            key={mode}
            type="button"
            role="radio"
            aria-checked={viewMode === mode}
            onClick={() => setViewMode(mode)}
            className={cn(
              'inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-xs font-medium transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-primary-500',
              viewMode === mode
                ? 'bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-800',
            )}
            title={label}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">{label}</span>
          </button>
        ))}
      </div>

      {/* Center: Whiteboard tools (teacher only) */}
      {showWhiteboardTools && (
        <div className="flex items-center gap-1 border-l border-r border-gray-200 dark:border-gray-700 px-3 mx-1">
          {/* Tool buttons */}
          {WHITEBOARD_TOOLS.map(({ tool, icon: Icon, label }) => (
            <button
              key={tool}
              type="button"
              onClick={() => setTool(tool)}
              className={cn(
                'p-1.5 rounded-md transition-colors',
                'focus:outline-none focus:ring-2 focus:ring-primary-500',
                activeTool === tool
                  ? 'bg-gray-200 text-gray-900 dark:bg-gray-700 dark:text-gray-100'
                  : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-800',
              )}
              title={label}
              aria-label={label}
              aria-pressed={activeTool === tool}
            >
              <Icon className="h-4 w-4" />
            </button>
          ))}

          {/* Divider */}
          <div className="w-px h-5 bg-gray-200 dark:bg-gray-700 mx-1" aria-hidden="true" />

          {/* Color picker */}
          <div className="relative">
            <button
              type="button"
              onClick={() => setShowColorPicker((v) => !v)}
              className={cn(
                'p-1.5 rounded-md transition-colors',
                'focus:outline-none focus:ring-2 focus:ring-primary-500',
                'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-800',
              )}
              title="Color"
              aria-label="Pick drawing color"
              aria-expanded={showColorPicker}
            >
              <Palette className="h-4 w-4" aria-hidden="true" />
              <span
                className="absolute bottom-0.5 right-0.5 h-2 w-2 rounded-full border border-white dark:border-gray-900"
                style={{ backgroundColor: activeColor }}
                aria-hidden="true"
              />
            </button>

            {showColorPicker && (
              <div
                className="absolute top-full left-0 mt-1 p-2 bg-white dark:bg-gray-800 rounded-lg shadow-lg border border-gray-200 dark:border-gray-700 z-20"
                role="listbox"
                aria-label="Color options"
              >
                <div className="grid grid-cols-4 gap-1.5 mb-2">
                  {PRESET_COLORS.map((color) => (
                    <button
                      key={color}
                      type="button"
                      role="option"
                      aria-selected={activeColor === color}
                      onClick={() => {
                        setColor(color);
                        setShowColorPicker(false);
                      }}
                      className={cn(
                        'h-6 w-6 rounded-full border-2 transition-transform hover:scale-110',
                        activeColor === color ? 'border-gray-900 dark:border-gray-100 scale-110' : 'border-gray-200 dark:border-gray-600',
                      )}
                      style={{ backgroundColor: color }}
                      aria-label={color}
                    />
                  ))}
                </div>
                {/* Stroke width */}
                <div className="border-t border-gray-100 dark:border-gray-700 pt-2">
                  <p className="text-[10px] text-gray-400 mb-1">Stroke width</p>
                  <div className="flex items-center gap-1">
                    {STROKE_WIDTHS.map((w) => (
                      <button
                        key={w}
                        type="button"
                        onClick={() => setStrokeWidth(w)}
                        className={cn(
                          'flex items-center justify-center h-6 w-6 rounded transition-colors',
                          strokeWidth === w ? 'bg-gray-200 dark:bg-gray-700' : 'hover:bg-gray-100 dark:hover:bg-gray-700',
                        )}
                        aria-label={`Stroke width ${w}`}
                        aria-pressed={strokeWidth === w}
                      >
                        <span
                          className="rounded-full bg-gray-700 dark:bg-gray-300"
                          style={{ width: w + 2, height: w + 2 }}
                          aria-hidden="true"
                        />
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Center-Right: Playback controls + action buttons */}
      <div className="flex items-center gap-1">
        {/* Play / Pause */}
        <button
          type="button"
          onClick={handlePlayPause}
          className={cn(
            'p-1.5 rounded-md transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-primary-500',
            isPlaying
              ? 'bg-primary-100 text-primary-700 dark:bg-primary-900 dark:text-primary-300'
              : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-800',
          )}
          title={isPlaying ? 'Pause (Space)' : 'Play (Space)'}
          aria-label={isPlaying ? 'Pause playback' : 'Play playback'}
        >
          {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
        </button>

        {/* Stop */}
        <button
          type="button"
          onClick={handleStop}
          className={cn(
            'p-1.5 rounded-md transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-primary-500',
            'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-800',
          )}
          title="Stop"
          aria-label="Stop playback"
        >
          <Square className="h-4 w-4" />
        </button>

        {/* Inline speed selector */}
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

        {/* Discussion mode toggle */}
        {onDiscussionToggle && (
          <button
            type="button"
            onClick={onDiscussionToggle}
            className={cn(
              'p-1.5 rounded-md transition-colors',
              'focus:outline-none focus:ring-2 focus:ring-primary-500',
              discussionActive
                ? 'bg-violet-100 text-violet-600 dark:bg-violet-900 dark:text-violet-300'
                : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-800',
            )}
            title="Discussion Mode (D)"
            aria-label="Toggle discussion mode"
            aria-pressed={discussionActive}
          >
            <MessagesSquare className="h-4 w-4" />
          </button>
        )}

        {/* Notes panel toggle */}
        <NotesToggleButton />

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

              {/* Slide Transition */}
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

              {/* Keyboard shortcuts hint */}
              <div className="border-t border-gray-100 dark:border-gray-700 pt-2">
                <p className="text-[10px] text-gray-400 mb-1">Keyboard Shortcuts</p>
                <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px] text-gray-500 dark:text-gray-400">
                  <span>Space</span><span>Play/Pause</span>
                  <span>Arrow keys</span><span>Navigate</span>
                  <span>F11</span><span>Fullscreen</span>
                  <span>M</span><span>Mute</span>
                  <span>C</span><span>Chat panel</span>
                  <span>S</span><span>Scene sidebar</span>
                  <span>N</span><span>Notes panel</span>
                </div>
              </div>

              {/* Open full settings dialog */}
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
          title={isFullscreen ? 'Exit fullscreen (F11)' : 'Enter fullscreen (F11)'}
          aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
        >
          {isFullscreen ? (
            <Minimize className="h-4 w-4" />
          ) : (
            <Maximize className="h-4 w-4" />
          )}
        </button>
      </div>

      {/* Full settings dialog */}
      <SettingsDialog open={showSettingsDialog} onClose={() => setShowSettingsDialog(false)} />
    </div>
  );
});
