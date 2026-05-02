/**
 * MAIC v2 dev probe page.
 *
 * Manual smoke-test page for the WS hook. Click `start` and confirm the
 * 3-frame triplet (agent_start → text_delta → agent_end) lands in the
 * event log.  Useful while iterating on the consumer + graph; not a
 * customer-facing page.
 *
 * Routed in MAIC-007 behind featureFlags.maicV2Enabled at /dev/maic-v2.
 */
import { useState } from 'react';
import { useMaicClassroomChannelV2 } from '../../hooks/useMaicClassroomChannelV2';

export default function MaicV2Probe() {
  const [sessionId] = useState(() => `dev-${Math.random().toString(36).slice(2, 10)}`);
  const { status, events, closeCode, send, reset } = useMaicClassroomChannelV2({
    sessionId,
  });

  return (
    <div style={{ fontFamily: 'monospace', padding: 24, maxWidth: 900 }}>
      <h1 style={{ marginTop: 0 }}>MAIC v2 Probe</h1>
      <div style={{ marginBottom: 8 }}>
        Session: <b>{sessionId}</b>
      </div>
      <div style={{ marginBottom: 8 }}>
        Status: <b>{status}</b>
        {closeCode !== null && <span style={{ marginLeft: 8 }}>(close code: {closeCode})</span>}
      </div>
      <div style={{ marginBottom: 16 }}>
        <button onClick={() => send({ action: 'start' })} disabled={status !== 'open'}>
          start
        </button>
        <button onClick={reset} style={{ marginLeft: 8 }}>
          reset
        </button>
      </div>
      <pre
        style={{
          background: '#111',
          color: '#0f0',
          padding: 12,
          borderRadius: 6,
          minHeight: 200,
          overflow: 'auto',
        }}
      >
        {events.length === 0
          ? '(no events yet — click start)'
          : events
              .map((e, i) => `${i.toString().padStart(3, '0')}  ${e.type}  ${JSON.stringify(e.data)}`)
              .join('\n')}
      </pre>
    </div>
  );
}
