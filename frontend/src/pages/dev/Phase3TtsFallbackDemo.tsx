/**
 * Phase 3 TTS-Fallback Demo — drives a long-text speech action with
 * NO audioUrl through the REAL PlaybackEngine, forcing the
 * `_dispatchSpeechFallback` branch. When the estimated reading time
 * is ≥ 15s AND `BrowserTTSPlayer.isAvailable()` is true (real
 * browser), the engine routes through `speechSynthesis` via the
 * `BrowserTTSPlayer` shipped in MAIC-413.1.
 *
 * The demo's `data-tts-state` attribute is set from the engine's
 * `onSpeechStart` ('speaking') and `onSpeechEnd` ('ended') callbacks
 * — the headless smoke (MAIC-418.4) asserts on this attribute
 * instead of polling `speechSynthesis.speaking`, avoiding the async-
 * flip race the Plan-agent flagged.
 *
 * Smoke flow against `?scene=phase3-tts-fallback`:
 *   1. Click Start → engine starts → speech action with no audio
 *   2. _estimateReadingMs ≥ 15000ms → BrowserTTSPlayer.speak()
 *   3. data-tts-state flips 'idle' → 'speaking' → 'ended'
 *
 * Validates Phase 3 AC#6 (browser-native TTS chunked playback).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ActionEngine } from '../../lib/maic-v2/action-engine';
import { AudioPlayer } from '../../lib/maic-v2/audio-player';
import {
  PlaybackEngine,
  type Scene,
} from '../../lib/maic-v2/playback-engine';
import type { EngineMode } from '../../lib/maic-v2/playback-types';
import {
  WhiteboardProvider,
  useWhiteboardController,
} from '../../lib/maic-v2/whiteboard-state';


/**
 * ~85-word paragraph chosen so:
 *   - non-CJK heuristic kicks in (CJK chars / total < 0.3)
 *   - 85 words × 240 ms/word ≈ 20.4 s estimated reading time
 *   - clears the 15 s threshold in `playback-engine.ts`
 *
 * This forces the no-audio fallback path to route through
 * BrowserTTSPlayer rather than the silent reading-timer.
 */
const PHASE3_TTS_LONG_TEXT = (
  'Photosynthesis is the biological process by which plants, algae, and '
  + 'certain bacteria convert light energy, usually from the sun, into '
  + 'chemical energy stored in glucose and other organic molecules. The '
  + 'process takes place primarily in the chloroplasts of plant cells, '
  + 'where chlorophyll captures incoming photons and drives a sequence '
  + 'of light-dependent and light-independent reactions. Carbon dioxide '
  + 'and water are consumed, while oxygen is released as a byproduct, '
  + 'making photosynthesis the foundation of nearly all food chains on '
  + 'Earth and a critical part of the global carbon cycle.'
);


type TtsState = 'idle' | 'speaking' | 'ended';


const PHASE3_TTS_SCENE: Scene = {
  id: 'phase3-tts-fallback',
  type: 'whiteboard',
  actions: [
    {
      id: 'a-long-speech',
      type: 'speech',
      text: PHASE3_TTS_LONG_TEXT,
      // No audioUrl → engine's _dispatchSpeech falls back. With
      // ~20s estimated reading time and BrowserTTS available, the
      // engine routes through speechSynthesis.
    },
  ],
};


export default function Phase3TtsFallbackDemo() {
  return (
    <WhiteboardProvider>
      <Phase3TtsFallbackDemoInner />
    </WhiteboardProvider>
  );
}


function Phase3TtsFallbackDemoInner() {
  const whiteboardController = useWhiteboardController();
  const audioPlayerRef = useRef<AudioPlayer | null>(null);
  const actionEngineRef = useRef<ActionEngine | null>(null);
  const engineRef = useRef<PlaybackEngine | null>(null);

  const [mode, setMode] = useState<EngineMode>('idle');
  const [ttsState, setTtsState] = useState<TtsState>('idle');

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
    setTtsState('idle');
    const engine = new PlaybackEngine(
      [PHASE3_TTS_SCENE],
      actionEngineRef.current,
      audioPlayerRef.current,
      {
        onModeChange: (m) => setMode(m),
        onSpeechStart: () => setTtsState('speaking'),
        onSpeechEnd: () => setTtsState('ended'),
      },
    );
    engineRef.current = engine;
    engine.start();
  }, [mode]);

  const onStop = useCallback(() => {
    engineRef.current?.stop();
    engineRef.current = null;
    setMode('idle');
    setTtsState('idle');
  }, []);

  const description = useMemo(
    () => 'Drives a ~85-word speech action with no audioUrl through the engine. '
      + 'When the estimated reading time exceeds 15 s AND speechSynthesis is '
      + 'available, the engine routes through BrowserTTSPlayer (chunked '
      + 'utterances + watchdog). data-tts-state flips idle → speaking → ended '
      + 'as the engine fires onSpeechStart and onSpeechEnd.',
    [],
  );

  return (
    <div
      data-testid="phase3-tts-fallback"
      data-engine-mode={mode}
      data-tts-state={ttsState}
      style={{ fontFamily: 'system-ui, sans-serif', padding: 24, maxWidth: 1100 }}
    >
      <h1 style={{ marginTop: 0 }}>MAIC v2 — Phase 3 TTS-Fallback Demo</h1>
      <p style={{ color: '#666', fontSize: 13, marginBottom: 16 }}>{description}</p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          data-testid="phase3-tts-start"
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
            data-testid="phase3-tts-stop"
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
          mode: <b>{mode}</b> · tts: <b>{ttsState}</b>
        </span>
      </div>

      <pre
        style={{
          background: '#fff',
          border: '1px solid #e5e7eb',
          borderRadius: 6,
          padding: 12,
          marginTop: 16,
          color: '#374151',
          fontSize: 13,
          whiteSpace: 'pre-wrap',
          fontFamily: 'system-ui, sans-serif',
        }}
      >
        {PHASE3_TTS_LONG_TEXT}
      </pre>

      <div style={{ marginTop: 16, color: '#666', fontSize: 12 }}>
        Word count: <b>{PHASE3_TTS_LONG_TEXT.split(/\s+/).filter(Boolean).length}</b>
        {' · '}
        Estimated reading time: <b>
          ~{((PHASE3_TTS_LONG_TEXT.split(/\s+/).filter(Boolean).length * 240) / 1000).toFixed(1)}s
        </b>
      </div>
    </div>
  );
}
