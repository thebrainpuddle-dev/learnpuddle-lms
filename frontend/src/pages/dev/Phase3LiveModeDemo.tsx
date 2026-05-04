/**
 * Phase 3 Live-Mode Demo — drives a hand-crafted Scene with a
 * `discussion` action through the REAL PlaybackEngine + the Phase 3
 * live-mode UI components (ProactiveCardManager + LiveInput).
 *
 * Mirrors the Phase 2 demo pattern: mounts engine + components
 * directly (NOT Stage), so no `useMaicClassroomChannelV2` is involved
 * — there's no real WS to a backend. The "would-be" outgoing WS
 * frames (user_message on Send, resume on End Discussion) are
 * recorded onto the demo root's `data-last-sent-action` attribute
 * via a real local handler — not a mock — so the headless smoke
 * (MAIC-418.3) can read the wire-format JSON via DOM and verify
 * shape correctness without daphne running.
 *
 * Smoke flow against `?scene=phase3-live-mode`:
 *   1. Click Start → engine plays → discussion action → 3s delay
 *   2. ProactiveCard appears → click Join → mode='live'
 *   3. Type into LiveInput → Send → data-last-sent-action set
 *   4. Click End Discussion → mode exits 'live'
 *
 * Validates Phase 3 ACs:
 *   #3  ProactiveCard 3s delay
 *   #4  Join → live → user_message frame shape
 *   #5  End Discussion → restore + continuePlayback → idle
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ActionEngine } from '../../lib/maic-v2/action-engine';
import { AudioPlayer } from '../../lib/maic-v2/audio-player';
import {
  PlaybackEngine,
  type Scene,
} from '../../lib/maic-v2/playback-engine';
import type {
  EngineMode,
  TriggerEvent,
} from '../../lib/maic-v2/playback-types';
import {
  WhiteboardProvider,
  useWhiteboardController,
} from '../../lib/maic-v2/whiteboard-state';

import { LiveInput } from '../../components/maic-v2/LiveInput';
import { ProactiveCardManager } from '../../components/maic-v2/ProactiveCardManager';


/**
 * Minimal scene with a single `discussion` action. After confirm
 * + handleEndDiscussion + continuePlayback, the engine exhausts
 * actions and returns to 'idle'.
 */
const PHASE3_LIVE_MODE_SCENE: Scene = {
  id: 'phase3-live-mode',
  type: 'whiteboard',
  actions: [
    {
      id: 'd-fractions',
      type: 'discussion',
      topic: 'Are fractions intuitive?',
      prompt: 'Discuss whether fractions feel intuitive at first encounter.',
    },
  ],
};


/** Type of frame recorded onto data-last-sent-action. */
type LastSentAction =
  | { action: 'user_message'; data: { text: string } }
  | { action: 'resume' }
  | null;


export default function Phase3LiveModeDemo() {
  return (
    <WhiteboardProvider>
      <Phase3LiveModeDemoInner />
    </WhiteboardProvider>
  );
}


function Phase3LiveModeDemoInner() {
  const whiteboardController = useWhiteboardController();
  const audioPlayerRef = useRef<AudioPlayer | null>(null);
  const actionEngineRef = useRef<ActionEngine | null>(null);
  const engineRef = useRef<PlaybackEngine | null>(null);

  const [mode, setMode] = useState<EngineMode>('idle');
  const [trigger, setTrigger] = useState<TriggerEvent | null>(null);
  const [lastSentAction, setLastSentAction] = useState<LastSentAction>(null);

  useEffect(() => {
    if (!audioPlayerRef.current) audioPlayerRef.current = new AudioPlayer();
    if (!actionEngineRef.current) {
      actionEngineRef.current = new ActionEngine({
        whiteboard: whiteboardController,
      });
    }
    return () => {
      audioPlayerRef.current?.destroy();
      audioPlayerRef.current = null;
      actionEngineRef.current = null;
      engineRef.current = null;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onStart = useCallback(() => {
    if (mode !== 'idle' || !actionEngineRef.current || !audioPlayerRef.current) return;
    const engine = new PlaybackEngine(
      [PHASE3_LIVE_MODE_SCENE],
      actionEngineRef.current,
      audioPlayerRef.current,
      {
        onModeChange: (m) => setMode(m),
        onProactiveShow: (t) => setTrigger(t),
        onProactiveHide: () => setTrigger(null),
      },
    );
    engineRef.current = engine;
    engine.start();
  }, [mode]);

  const onStop = useCallback(() => {
    engineRef.current?.stop();
    engineRef.current = null;
    setMode('idle');
    setTrigger(null);
    setLastSentAction(null);
  }, []);

  const onJoin = useCallback(() => {
    engineRef.current?.confirmDiscussion();
  }, []);

  const onSkip = useCallback(() => {
    engineRef.current?.skipDiscussion();
  }, []);

  const onLiveSend = useCallback((text: string) => {
    // Real local handler — not a mock. Records the would-be WS frame
    // for the headless smoke to read via DOM. In production, Stage's
    // equivalent handler dispatches `send({action:'user_message',
    // data:{text}})` over the real channel hook.
    engineRef.current?.sendUserMessage(text);
    setLastSentAction({ action: 'user_message', data: { text } });
  }, []);

  const onLiveEnd = useCallback(() => {
    engineRef.current?.handleEndDiscussion();
    engineRef.current?.continuePlayback();
    // Same real-handler reasoning: record the would-be `resume` frame
    // so the smoke can verify the full Send→End sequence.
    setLastSentAction({ action: 'resume' });
  }, []);

  const description = useMemo(
    () => 'Drives the live-mode flow end-to-end: Start → discussion action → 3s ProactiveCard → '
      + 'Join → live mode → LiveInput → Send → End Discussion → continuePlayback. '
      + 'No backend involvement — the would-be WS frames are recorded on '
      + 'data-last-sent-action for the headless smoke to read via DOM.',
    [],
  );

  return (
    <div
      data-testid="phase3-live-mode"
      data-engine-mode={mode}
      data-last-sent-action={lastSentAction ? JSON.stringify(lastSentAction) : ''}
      style={{ fontFamily: 'system-ui, sans-serif', padding: 24, maxWidth: 1100 }}
    >
      <h1 style={{ marginTop: 0 }}>MAIC v2 — Phase 3 Live-Mode Demo</h1>
      <p style={{ color: '#666', fontSize: 13, marginBottom: 16 }}>{description}</p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          data-testid="phase3-live-mode-start"
          onClick={onStart}
          disabled={mode !== 'idle'}
          style={{
            padding: '6px 14px',
            borderRadius: 6,
            border: '1px solid #1f2937',
            background: mode === 'idle' ? '#1f2937' : '#9ca3af',
            color: '#fff',
            cursor: mode === 'idle' ? 'pointer' : 'not-allowed',
            fontSize: 13,
          }}
        >
          Start
        </button>
        {mode !== 'idle' && (
          <button
            data-testid="phase3-live-mode-stop"
            onClick={onStop}
            style={{
              padding: '6px 14px',
              borderRadius: 6,
              border: '1px solid #b91c1c',
              background: '#fff',
              color: '#b91c1c',
              cursor: 'pointer',
              fontSize: 13,
            }}
          >
            Stop
          </button>
        )}
        <span style={{ alignSelf: 'center', color: '#666', fontSize: 12 }}>
          mode: <b data-testid="phase3-live-mode-mode">{mode}</b>
        </span>
      </div>

      {/* ProactiveCardManager — same component Stage mounts in production. */}
      {engineRef.current && (
        <div style={{ marginBottom: 16 }}>
          <ProactiveCardManager
            engine={engineRef.current}
            trigger={trigger}
            onJoin={onJoin}
            onSkip={onSkip}
          />
        </div>
      )}

      {/* LiveInput — only visible when engine is in `live` mode. */}
      {mode === 'live' && (
        <LiveInput onSend={onLiveSend} onEnd={onLiveEnd} />
      )}

      <div style={{ marginTop: 16, color: '#666', fontSize: 12 }}>
        Actions in scene: <b>{PHASE3_LIVE_MODE_SCENE.actions?.length ?? 0}</b>
      </div>
    </div>
  );
}
