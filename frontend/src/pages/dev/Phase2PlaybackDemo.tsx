/**
 * Phase 2 Playback Demo — drives a hand-crafted Scene through the
 * REAL PlaybackEngine + ActionEngine + WhiteboardProvider.
 *
 * Unlike Phase2StaticDemo (which pre-populates state directly to
 * isolate renderer correctness), this demo exercises the FULL
 * production playback pipeline end-to-end:
 *
 *   Scene → PlaybackEngine.start() → processNext loop
 *     → action dispatch (speech, wb_*, spotlight, laser) →
 *       ActionEngine.execute → WhiteboardController mutation →
 *         Whiteboard re-render → SpotlightOverlay/LaserOverlay
 *
 * The 14 actions cover every wb_* + both fire-and-forget overlays.
 * No backend involvement — this validates the frontend playback +
 * rendering surface in a real browser, not the WS / LangGraph /
 * edge_tts side (those have their own Phase 1 live-smoke).
 *
 * Routed via /dev/maic-v2?scene=phase2-demo. Click Start to drive
 * the scene; visual verification is the point.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { ActionEngine } from '../../lib/maic-v2/action-engine';
import { AudioPlayer } from '../../lib/maic-v2/audio-player';
import {
  PlaybackEngine,
  type Scene,
} from '../../lib/maic-v2/playback-engine';
import type { EngineMode, Effect } from '../../lib/maic-v2/playback-types';
import {
  WhiteboardProvider,
  useWhiteboardController,
} from '../../lib/maic-v2/whiteboard-state';

import { LaserOverlay } from '../../components/maic-v2/LaserOverlay';
import { SpotlightOverlay } from '../../components/maic-v2/SpotlightOverlay';
import { Whiteboard } from '../../components/maic-v2/Whiteboard';


/** 14-action scene covering every renderer + both overlays. */
const PHASE2_DEMO_SCENE: Scene = {
  id: 'phase2-demo',
  type: 'whiteboard',
  actions: [
    { id: 'a-open', type: 'wb_open' },
    {
      id: 'a-text', elementId: 'title', type: 'wb_draw_text',
      content: '<h2 style="margin:0">Phase 2 Playback Demo</h2>',
      x: 20, y: 10, width: 960, height: 50, color: '#1f2937',
    },
    {
      id: 'a-rect', elementId: 'rect-1', type: 'wb_draw_shape', shape: 'rectangle',
      x: 20, y: 70, width: 100, height: 60, fillColor: '#5b9bd5',
    },
    {
      id: 'a-circle', elementId: 'circle-1', type: 'wb_draw_shape', shape: 'circle',
      x: 140, y: 70, width: 60, height: 60, fillColor: '#ed7d31',
    },
    {
      id: 'a-line', elementId: 'line-1', type: 'wb_draw_line',
      startX: 220, startY: 100, endX: 340, endY: 100,
      color: '#333', width: 3, points: ['', 'arrow'],
    },
    {
      id: 'a-latex', elementId: 'latex-1', type: 'wb_draw_latex',
      latex: '\\sum_{i=1}^{n} x_i^2',
      x: 360, y: 70, width: 280, height: 60, color: '#0066cc',
    },
    {
      id: 'a-table', elementId: 'tbl-1', type: 'wb_draw_table',
      x: 20, y: 150, width: 360, height: 130,
      data: [['Quarter', 'Sales'], ['Q1', '120'], ['Q2', '180'], ['Q3', '210']],
      theme: { color: '#1f77b4' },
    },
    {
      id: 'a-chart', elementId: 'chart-1', type: 'wb_draw_chart', chartType: 'bar',
      x: 400, y: 150, width: 380, height: 130,
      data: {
        labels: ['Q1', 'Q2', 'Q3'],
        legends: ['Sales'],
        series: [[120, 180, 210]],
      },
    },
    {
      id: 'a-code', elementId: 'code-1', type: 'wb_draw_code',
      language: 'typescript', fileName: 'demo.ts',
      code: 'function fib(n: number): number {\n  return n < 2 ? n : fib(n-1) + fib(n-2);\n}',
      x: 20, y: 300, width: 360, height: 110,
    },
    {
      id: 'a-edit', type: 'wb_edit_code', elementId: 'code-1',
      operation: 'insert_after', lineId: 'L1',
      content: '  // demonstrates wb_edit_code',
    },
    {
      id: 'a-spot', type: 'spotlight',
      elementId: 'code-1',
      dimOpacity: 0.6,
    },
    {
      id: 'a-laser', type: 'laser',
      elementId: 'title',
      color: '#ff3b30',
    },
    {
      id: 'a-delete', type: 'wb_delete', elementId: 'rect-1',
    },
    {
      id: 'a-close', type: 'wb_close',
    },
  ],
};


export default function Phase2PlaybackDemo() {
  return (
    <WhiteboardProvider>
      <Phase2PlaybackDemoInner />
    </WhiteboardProvider>
  );
}


function Phase2PlaybackDemoInner() {
  const whiteboardController = useWhiteboardController();
  const audioPlayerRef = useRef<AudioPlayer | null>(null);
  const actionEngineRef = useRef<ActionEngine | null>(null);
  const engineRef = useRef<PlaybackEngine | null>(null);

  const [mode, setMode] = useState<EngineMode>('idle');
  const [activeEffect, setActiveEffect] = useState<Effect | null>(null);

  useEffect(() => {
    if (!audioPlayerRef.current) audioPlayerRef.current = new AudioPlayer();
    if (!actionEngineRef.current) {
      actionEngineRef.current = new ActionEngine({ whiteboard: whiteboardController });
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
      [PHASE2_DEMO_SCENE],
      actionEngineRef.current,
      audioPlayerRef.current,
      {
        onModeChange: (m) => setMode(m),
        onEffectFire: (effect) => setActiveEffect(effect),
      },
    );
    engineRef.current = engine;
    engine.start();
  }, [mode]);

  const onStop = useCallback(() => {
    engineRef.current?.stop();
    engineRef.current = null;
    setMode('idle');
    setActiveEffect(null);
  }, []);

  const description = useMemo(
    () => 'Drives the real PlaybackEngine through 14 actions covering every wb_* renderer + spotlight + laser. ' +
      'No backend involvement — this is the frontend playback + rendering surface validated end-to-end.',
    [],
  );

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: 24, maxWidth: 1100 }}>
      <h1 style={{ marginTop: 0 }}>MAIC v2 — Phase 2 Playback Demo</h1>
      <p style={{ color: '#666', fontSize: 13, marginBottom: 16 }}>{description}</p>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
        <button
          data-testid="phase2-demo-start"
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
            data-testid="phase2-demo-stop"
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
          mode: <b data-testid="phase2-demo-mode">{mode}</b> · effect:{' '}
          <b data-testid="phase2-demo-effect">{activeEffect?.kind ?? 'none'}</b>
        </span>
      </div>

      <div style={{ position: 'relative' }}>
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

      <div style={{ marginTop: 16, color: '#666', fontSize: 12 }}>
        Actions in scene: <b>{PHASE2_DEMO_SCENE.actions?.length ?? 0}</b>
      </div>
    </div>
  );
}
