/**
 * Stage — single-slide canvas for the AI Classroom.
 *
 * Wires together (Phase 1 + Phase 2 surfaces):
 *
 *   useMaicClassroomChannelV2  →  events[]
 *      ↓
 *   useSceneBuffer(events)     →  SceneBuffer
 *      ↓
 *   buildSceneFromBuffer       →  Scene (PlaybackEngine input)
 *      ↓
 *   PlaybackEngine + AudioPlayer + ActionEngine(WhiteboardController)
 *      ↓
 *   AgentOverlay + Transcript + StageControls + Whiteboard + Effects
 *
 * MAIC-217 (this commit) wraps Stage's body in a WhiteboardProvider so
 * the ActionEngine can mutate whiteboard state via the controller, and
 * the Whiteboard component re-renders from that state. Effects
 * (spotlight, laser) flow through the engine's `onEffectFire`
 * callback into a local activeEffect state; SpotlightOverlay (MAIC-
 * 215) and LaserOverlay (MAIC-216) consume it.
 *
 * Phase deferrals (signposted; do NOT remove until linked tickets):
 *   - 410 — multi-turn dispatch (cue_user → second user input → next
 *     agent turn). Phase 1 is single-turn; Stage tears down on Stop.
 *   - 401.5 — discussion / ProactiveCard surface (engine emits the
 *     onProactiveShow callback already; Stage wires once the card UX
 *     is locked).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ActionEngine, type ActionEngineOptions } from '../../lib/maic-v2/action-engine';
import { AudioPlayer } from '../../lib/maic-v2/audio-player';
import {
  PlaybackEngine,
  type Scene,
} from '../../lib/maic-v2/playback-engine';
import {
  createPlaybackPersistence,
  type PlaybackPersistence,
} from '../../lib/maic-v2/playbackPersistence';
import type {
  EngineMode,
  Effect,
  TriggerEvent,
} from '../../lib/maic-v2/playback-types';
import { buildSceneFromBuffer } from '../../lib/maic-v2/scene-builder';
import { useSceneBuffer } from '../../lib/maic-v2/use-scene-buffer';
import {
  WhiteboardProvider,
  useWhiteboardController,
  type WhiteboardController,
} from '../../lib/maic-v2/whiteboard-state';
import { useMaicClassroomChannelV2 } from '../../hooks/useMaicClassroomChannelV2';

import { AgentOverlay } from './AgentOverlay';
import { LaserOverlay } from './LaserOverlay';
import { ProactiveCardManager } from './ProactiveCardManager';
import { SpotlightOverlay } from './SpotlightOverlay';
import { StageControls } from './StageControls';
import { Transcript } from './Transcript';
import { Whiteboard } from './Whiteboard';


export interface StageProps {
  sessionId: string;
  /** Override the WS base URL (test injection point for MockWebSocket). */
  baseUrl?: string;
  /** Default true; set false to gate WS open behind a parent flag. */
  autoConnect?: boolean;
  /**
   * Test-only injection point for the ActionEngine constructor — most
   * notably `delay`, which Stage tests pass as `() => Promise.resolve()`
   * to skip the 2 s wb_open spring-in. Production callers leave this
   * unset and get the real setTimeout-based delay.
   */
  actionEngineOptions?: ActionEngineOptions;
  /**
   * Test-only override for the PlaybackPersistence backend (MAIC-412).
   * Production callers leave this unset and get the localStorage-backed
   * default scoped by `sessionId`. Tests pass an in-memory stub to
   * assert save/load semantics without touching the real Storage.
   */
  persistence?: PlaybackPersistence;
}


/**
 * Outer Stage — owns the WhiteboardProvider so the inner Stage's
 * ActionEngine can grab a stable controller via the hook. Splitting
 * into outer/inner is the cleanest way to satisfy "Stage mounts the
 * provider AND consumes it": the provider must wrap the consumer.
 */
export function Stage(props: StageProps) {
  return (
    <WhiteboardProvider>
      <StageInner {...props} />
    </WhiteboardProvider>
  );
}


function StageInner({
  sessionId,
  baseUrl,
  autoConnect = true,
  actionEngineOptions,
  persistence: persistenceProp,
}: StageProps) {
  const whiteboardController = useWhiteboardController();

  // MAIC-412: persistence handle scoped by sessionId. Created once per
  // sessionId so two reloads of the same session share storage; tests
  // can override via the `persistence` prop to assert save/load
  // semantics without touching real localStorage.
  const persistence = useMemo<PlaybackPersistence>(
    () => persistenceProp ?? createPlaybackPersistence(sessionId),
    [sessionId, persistenceProp],
  );

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
  // Effect surface for spotlight/laser. PlaybackEngine fires effects
  // through onEffectFire; we capture them here and the overlay
  // components (MAIC-215, 216) consume + auto-clear at 5000 ms.
  const [activeEffect, setActiveEffect] = useState<Effect | null>(null);
  // MAIC-411.2: ProactiveCard trigger surface — controlled by the
  // engine via onProactiveShow / onProactiveHide. ProactiveCardManager
  // dedups against engine.getSnapshot().consumedDiscussions.
  const [proactiveTrigger, setProactiveTrigger] = useState<TriggerEvent | null>(null);
  // Track sceneIds we've already wired into a PlaybackEngine.  Without
  // this, calling Stop sets engineRef.current=null which would cause
  // the auto-construct effect to spin up a fresh engine for the same
  // (still-completed) scene.
  const playedSceneIdsRef = useRef<Set<string>>(new Set());

  // Initialise singleton dependencies once. ActionEngine is built
  // WITH the WhiteboardController so wb_* lifecycle ops mutate the
  // surface state for real (no warn-and-skip path in production).
  useEffect(() => {
    if (!audioPlayerRef.current) audioPlayerRef.current = new AudioPlayer();
    if (!actionEngineRef.current) {
      actionEngineRef.current = new ActionEngine({
        whiteboard: whiteboardController,
        ...(actionEngineOptions ?? {}),
      });
    }
    return () => {
      audioPlayerRef.current?.destroy();
      audioPlayerRef.current = null;
      actionEngineRef.current = null;
      engineRef.current = null;
    };
  // The controller's identity is stable (via useMemo in the provider);
  // including it in deps would be safe but we deliberately keep this
  // a mount-only effect so a hot-reloaded controller doesn't recreate
  // singletons mid-session. eslint-disable-next-line react-hooks/exhaustive-deps
  // eslint-disable-next-line react-hooks/exhaustive-deps
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
        onEffectFire: (effect) => setActiveEffect(effect),
        // MAIC-412: persist progress on every action consume so a
        // reload restores at the same action.
        onProgress: (snapshot) => persistence.save(snapshot),
        // MAIC-411.2: ProactiveCard surface — engine fires
        // onProactiveShow 3s after a `discussion` action enters the
        // stream. Manager dedups against consumedDiscussions.
        onProactiveShow: (t) => setProactiveTrigger(t),
        onProactiveHide: () => setProactiveTrigger(null),
        onComplete: () => {
          // Stage freezes on completion; user can hit Stop to reset.
          // MAIC-412: clear persisted snapshot — completion means
          // there's nothing left to resume.
          persistence.clear();
        },
      },
    );
    engineRef.current = engine;

    // MAIC-412: try to resume from a saved snapshot before starting.
    // restoreFromSnapshot already discards the snapshot on sceneId
    // mismatch (engine.ts:138) so a stale entry from a different scene
    // simply falls through to a fresh start.
    const saved = persistence.load();
    if (saved && saved.sceneId === scene.id) {
      engine.restoreFromSnapshot(saved);
      engine.continuePlayback();
    } else {
      engine.start();
    }
  }, [buffer.status, scene, backendKicked, engineMode, persistence]);

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
    setActiveEffect(null);
    // MAIC-412: explicit Stop discards saved progress — the user has
    // chosen to abandon this run, not pause it.
    persistence.clear();
  }, [persistence]);

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
      data-active-effect={activeEffect?.kind ?? 'none'}
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

      {/* Whiteboard surface — visible only when the agent has emitted
          wb_open. Position relative so SpotlightOverlay (215) and
          LaserOverlay (216) can absolute-mount over it once they ship. */}
      <div className="relative">
        <Whiteboard />
        {activeEffect?.kind === 'spotlight' && (
          <SpotlightOverlay
            key={`spotlight-${activeEffect.targetId}`}
            targetId={activeEffect.targetId}
            dimOpacity={activeEffect.dimOpacity}
            onClear={() => setActiveEffect(null)}
          />
        )}
        {activeEffect?.kind === 'laser' && (
          <LaserOverlay
            key={`laser-${activeEffect.targetId}`}
            targetId={activeEffect.targetId}
            color={activeEffect.color}
            onClear={() => setActiveEffect(null)}
          />
        )}
      </div>

      {/* MAIC-411.2: ProactiveCard surfaces between Whiteboard and
          Transcript when the engine fires onProactiveShow. Manager
          dedups against engine.getSnapshot().consumedDiscussions. */}
      {engineRef.current && (
        <ProactiveCardManager
          engine={engineRef.current}
          trigger={proactiveTrigger}
          onJoin={() => engineRef.current?.confirmDiscussion()}
          onSkip={() => engineRef.current?.skipDiscussion()}
        />
      )}

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


/** Re-exported for the Stage tests + future SpotlightOverlay / LaserOverlay. */
export type { WhiteboardController };
