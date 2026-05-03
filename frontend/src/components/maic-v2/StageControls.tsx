/**
 * StageControls — start/pause/resume/stop button strip.
 *
 * Used by:
 *   - frontend/src/components/maic-v2/Stage.tsx (MAIC-403.7)
 *
 * Pure presentational + callback fan-out. The `mode` prop comes from
 * PlaybackEngine.getMode() (mirrored into Stage state via the
 * onModeChange callback). The component decides which buttons are
 * enabled/visible based on the mode; behavior of each click is owned
 * by the parent (the engine instance is constructed in Stage and the
 * callbacks call into engine.start() / pause() / resume() / stop()).
 *
 * Mode → controls mapping:
 *   idle       → Start (only useful affordance)
 *   playing    → Pause, Stop
 *   paused     → Resume, Stop
 *   live       → Stop only (Phase 3 will add discussion-end controls)
 *
 * Why a separate `canStart` prop: SceneBuffer may not yet have an
 * agent_start by the time Stage mounts (e.g., the WS opened but the
 * orchestrator is still spinning up). Stage owns the gate ("scene
 * has actions to play"); StageControls only renders the button.
 */
import type { EngineMode } from '../../lib/maic-v2/playback-types';


export interface StageControlsProps {
  mode: EngineMode;
  /**
   * True when the parent has computed a non-empty Scene from the
   * buffer; gates the Start button while we're still buffering the
   * first action.
   */
  canStart: boolean;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
}


export function StageControls({
  mode,
  canStart,
  onStart,
  onPause,
  onResume,
  onStop,
}: StageControlsProps) {
  return (
    <div
      data-testid="maic-v2-stage-controls"
      className="flex items-center gap-2"
    >
      {mode === 'idle' && (
        <button
          type="button"
          data-testid="maic-v2-control-start"
          className="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground disabled:opacity-50 disabled:cursor-not-allowed"
          disabled={!canStart}
          onClick={onStart}
        >
          Start
        </button>
      )}

      {mode === 'playing' && (
        <button
          type="button"
          data-testid="maic-v2-control-pause"
          className="px-3 py-1.5 rounded-md text-sm font-medium border"
          onClick={onPause}
        >
          Pause
        </button>
      )}

      {mode === 'paused' && (
        <button
          type="button"
          data-testid="maic-v2-control-resume"
          className="px-3 py-1.5 rounded-md text-sm font-medium bg-primary text-primary-foreground"
          onClick={onResume}
        >
          Resume
        </button>
      )}

      {mode !== 'idle' && (
        <button
          type="button"
          data-testid="maic-v2-control-stop"
          className="px-3 py-1.5 rounded-md text-sm font-medium border border-destructive text-destructive"
          onClick={onStop}
        >
          Stop
        </button>
      )}
    </div>
  );
}
