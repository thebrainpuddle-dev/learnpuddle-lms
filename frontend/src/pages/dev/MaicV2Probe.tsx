/**
 * MAIC v2 dev probe page.
 *
 * Hosts the Stage component (MAIC-403) for end-to-end smoke testing
 * against a running backend (real director_graph + edge_tts).  The
 * lower raw-event panel is preserved so we can debug protocol drift
 * without recompiling.
 *
 * Routed in MAIC-007 behind featureFlags.maicV2Enabled at /dev/maic-v2.
 */
import { useState } from 'react';
import { useMaicClassroomChannelV2 } from '../../hooks/useMaicClassroomChannelV2';
import { Stage } from '../../components/maic-v2/Stage';

export default function MaicV2Probe() {
  const [sessionId] = useState(() => `dev-${Math.random().toString(36).slice(2, 10)}`);

  // Raw event log — second WS connection so the Stage's hook owns its
  // own state.  Cheap (one extra WS, dev-only).
  const { status, events, closeCode } = useMaicClassroomChannelV2({
    sessionId: `${sessionId}-log`,
    autoConnect: false,  // probe panel is observation-only; Stage drives the real session
  });

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: 24, maxWidth: 1024 }}>
      <h1 style={{ marginTop: 0 }}>MAIC v2 Probe</h1>
      <div style={{ marginBottom: 16, color: '#666', fontSize: 13 }}>
        Session: <b>{sessionId}</b> · log channel: <b>{status}</b>
        {closeCode !== null && <span style={{ marginLeft: 8 }}>(close: {closeCode})</span>}
      </div>

      <Stage sessionId={sessionId} />

      <details style={{ marginTop: 24 }}>
        <summary style={{ cursor: 'pointer', fontSize: 13, color: '#666' }}>
          Raw event log (debug)
        </summary>
        <pre
          style={{
            background: '#111',
            color: '#0f0',
            padding: 12,
            borderRadius: 6,
            minHeight: 120,
            marginTop: 8,
            overflow: 'auto',
            fontSize: 11,
            fontFamily: 'monospace',
          }}
        >
          {events.length === 0
            ? '(parallel log channel disabled in this build — events render in the Stage above)'
            : events
                .map((e, i) => `${i.toString().padStart(3, '0')}  ${e.type}  ${JSON.stringify(e.data)}`)
                .join('\n')}
        </pre>
      </details>
    </div>
  );
}
