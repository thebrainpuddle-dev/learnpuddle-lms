/**
 * Stage — single-slide canvas for the AI Classroom (Phase 1).
 *
 * Wires together six previously-shipped pieces:
 *
 *   useMaicClassroomChannelV2  →  events[]
 *      ↓
 *   useSceneBuffer(events)     →  SceneBuffer
 *      ↓
 *   buildSceneFromBuffer       →  Scene (PlaybackEngine input)
 *      ↓
 *   PlaybackEngine + AudioPlayer + ActionEngine
 *      ↓
 *   AgentOverlay + Transcript + StageControls
 *
 * Phase 1 user flow:
 *   1. Stage mounts → WS opens (autoConnect=true).
 *   2. User clicks Start → send {action:'start'} to backend.
 *   3. Backend streams thinking → agent_start → text_delta… → action →
 *      speech_audio → agent_end. Buffer + scene update reactively.
 *   4. When buffer.status==='completed' AND engine is idle, Stage
 *      auto-constructs the engine with the now-ready scene and calls
 *      engine.start() — the user's single click drives the whole turn.
 *   5. Pause / Resume / Stop affordances appear once the engine begins
 *      playing.
 *
 * Phase 1 deferrals (signposted; do NOT remove until linked tickets):
 *   - 410 — multi-turn dispatch (cue_user → second user input → second
 *     agent turn). Phase 1 is single-turn; Stage tears down on Stop.
 *   - 401.5 — discussion / ProactiveCard surface (engine emits the
 *     onProactiveShow callback already; Stage wires once the card UX
 *     is locked).
 *   - Phase 2 — whiteboard rendering for wb_* actions (currently
 *     resolved-immediately stubs in the ActionEngine).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ActionEngine } from '../../lib/maic-v2/action-engine';
import { AudioPlayer } from '../../lib/maic-v2/audio-player';
import {
  PlaybackEngine,
  type Scene,
} from '../../lib/maic-v2/playback-engine';
import type { EngineMode } from '../../lib/maic-v2/playback-types';
import { buildSceneFromBuffer } from '../../lib/maic-v2/scene-builder';
import { useSceneBuffer } from '../../lib/maic-v2/use-scene-buffer';
import { useMaicClassroomChannelV2 } from '../../hooks/useMaicClassroomChannelV2';

import { AgentOverlay } from './AgentOverlay';
import { StageControls } from './StageControls';
import { Transcript } from './Transcript';


export interface StageProps {
  sessionId: string;
  /** Override the WS base URL (test injection point for MockWebSocket). */
  baseUrl?: string;
  /** Default true; set false to gate WS open behind a parent flag. */
  autoConnect?: boolean;
}


export function Stage({ sessionId, baseUrl, autoConnect = true }: StageProps) {
  // ── Channel + buffered state ───────────────────────────────────
  const { status: channelStatus, events, send } = useMaicClassroomChannelV2({
    sessionId,
    baseUrl,
    autoConnect,
  });
  const buffer = useSceneBuffer(events);
  const scene: Scene = useMemo(
    () => buildSceneFromBuffer(buffer, sessionId),
    [buffer, sessionId],
  );

  // ── Engine wiring (created lazily, owned by refs) ──────────────
  const audioPlayerRef = useRef<AudioPlayer | null>(null);
  const actionEngineRef = useRef<ActionEngine | null>(null);
  const engineRef = useRef<PlaybackEngine | null>(null);

  const [engineMode, setEngineMode] = useState<EngineMode>('idle');
  const [backendKicked, setBackendKicked] = useState(false);
  // Track sceneIds we've already wired into a PlaybackEngine.  Without
  // this, calling Stop sets engineRef.current=null which would cause
  // the auto-construct effect to spin up a fresh engine for the same
  // (still-completed) scene.
  const playedSceneIdsRef = useRef<Set<string>>(new Set());

  // Initialise singleton dependencies once.
  useEffect(() => {
    if (!audioPlayerRef.current) audioPlayerRef.current = new AudioPlayer();
    if (!actionEngineRef.current) actionEngineRef.current = new ActionEngine();
    return () => {
      audioPlayerRef.current?.destroy();
      audioPlayerRef.current = null;
      actionEngineRef.current = null;
      engineRef.current = null;
    };
  }, []);

  // Auto-construct + start engine once the turn is fully buffered.
  // Gate on engineMode==='idle' so we don't restart mid-playback when
  // a stray late event re-runs the effect.
  useEffect(() => {
    if (
      buffer.status !== 'completed' ||
      engineMode !== 'idle' ||
      !backendKicked ||
      engineRef.current !== null ||
      !scene.actions ||
      scene.actions.length === 0 ||
      playedSceneIdsRef.current.has(scene.id)
    ) {
      return;
    }
    if (!audioPlayerRef.current || !actionEngineRef.current) return;
    playedSceneIdsRef.current.add(scene.id);
    const engine = new PlaybackEngine(
      [scene],
      actionEngineRef.current,
      audioPlayerRef.current,
      {
        onModeChange: (m) => setEngineMode(m),
        onComplete: () => {
          // Stage freezes on completion; user can hit Stop to reset.
          // Phase 410 will dispatch the next turn here.
        },
      },
    );
    engineRef.current = engine;
    engine.start();
  }, [buffer.status, scene, backendKicked, engineMode]);

  // ── Control callbacks ──────────────────────────────────────────
  const onStart = useCallback(() => {
    if (channelStatus === 'open' && !backendKicked) {
      send({ action: 'start' });
      setBackendKicked(true);
    }
  }, [channelStatus, backendKicked, send]);

  const onPause = useCallback(() => engineRef.current?.pause(), []);
  const onResume = useCallback(() => engineRef.current?.resume(), []);
  const onStop = useCallback(() => {
    engineRef.current?.stop();
    engineRef.current = null;
    setEngineMode('idle');
  }, []);

  // ── Derived render state ───────────────────────────────────────
  const messageOrder = useMemo(
    () => (buffer.currentAgent ? [buffer.currentAgent.messageId] : []),
    [buffer.currentAgent],
  );

  const speaking = engineMode === 'playing' && buffer.status !== 'idle';
  const canStart = channelStatus === 'open' && !backendKicked;

  return (
    <div
      data-testid="maic-v2-stage"
      data-channel-status={channelStatus}
      data-engine-mode={engineMode}
      className="flex flex-col gap-4 w-full max-w-3xl mx-auto p-4 rounded-xl border bg-card"
    >
      <div className="flex items-center justify-between gap-4">
        <AgentOverlay agent={buffer.currentAgent} speaking={speaking} />
        <StageControls
          mode={engineMode}
          canStart={canStart}
          onStart={onStart}
          onPause={onPause}
          onResume={onResume}
          onStop={onStop}
        />
      </div>

      <Transcript
        textByMessageId={buffer.textByMessageId}
        messageOrder={messageOrder}
        status={buffer.status}
        thinkingStage={buffer.thinkingStage}
        cueingUser={buffer.cueingUser}
      />

      {buffer.lastError && (
        <p data-testid="maic-v2-stage-error" className="text-sm text-destructive">
          {buffer.lastError}
        </p>
      )}
    </div>
  );
}
