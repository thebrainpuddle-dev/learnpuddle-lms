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
import { useEffect, useState } from 'react';
import { useMaicClassroomChannelV2 } from '../../hooks/useMaicClassroomChannelV2';
import { Stage } from '../../components/maic-v2/Stage';
import { useAuthStore } from '../../stores/authStore';
import Phase2StaticDemo from './Phase2StaticDemo';

export default function MaicV2Probe() {
  // Dev sub-routes via ?scene= query param. phase2-static bypasses
  // the WS round-trip + auth entirely — useful for stress-testing the
  // renderers in a real browser without needing the backend.
  const sceneParam =
    typeof window !== 'undefined'
      ? new URLSearchParams(window.location.search).get('scene')
      : null;
  const isStaticDemo = sceneParam === 'phase2-static';

  const [sessionId] = useState(() => `dev-${Math.random().toString(36).slice(2, 10)}`);
  const accessToken = useAuthStore((s) => s.accessToken);
  const [tokenReady, setTokenReady] = useState<boolean>(!!accessToken);

  // Dev convenience: pull a JWT from (in order) the existing auth store,
  // a `?token=<jwt>` URL param, or the VITE_MAIC_DEV_TOKEN env var.  Any
  // of these three is sufficient.  Production builds never set the env
  // var, so this short-circuit is dev-only by construction.
  useEffect(() => {
    // Static demo bypasses Stage entirely — skip token injection so
    // the App's tenant-config/auth-me side effects never fire and
    // can't 401-cascade us to /login.
    if (isStaticDemo) return;
    if (accessToken) {
      setTokenReady(true);
      return;
    }
    const params = new URLSearchParams(window.location.search);
    const t = params.get('token') || (import.meta.env.VITE_MAIC_DEV_TOKEN as string | undefined);
    if (t) {
      const refresh = params.get('refresh') || t;
      // Axios reads access_token directly from sessionStorage/localStorage
      // via getAccessToken(); without this write the response interceptor
      // would 401 → terminateSession() → /login redirect.
      try {
        sessionStorage.setItem('access_token', t);
        sessionStorage.setItem('refresh_token', refresh);
        sessionStorage.setItem('tenant_subdomain', 'dev');
        localStorage.setItem('access_token', t);
        localStorage.setItem('refresh_token', refresh);
        localStorage.setItem('tenant_subdomain', 'dev');
      } catch { /* storage may be disabled in some sandboxes */ }
      useAuthStore.setState({
        accessToken: t,
        refreshToken: refresh,
        isAuthenticated: true,
      } as never);
      setTokenReady(true);
    }
  }, [accessToken, isStaticDemo]);

  // Raw event log — second WS connection so the Stage's hook owns its
  // own state.  Cheap (one extra WS, dev-only).
  const { status, events, closeCode } = useMaicClassroomChannelV2({
    sessionId: `${sessionId}-log`,
    autoConnect: false,  // probe panel is observation-only; Stage drives the real session
  });

  if (isStaticDemo) {
    return <Phase2StaticDemo />;
  }

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', padding: 24, maxWidth: 1024 }}>
      <h1 style={{ marginTop: 0 }}>MAIC v2 Probe</h1>
      <div style={{ marginBottom: 16, color: '#666', fontSize: 13 }}>
        Session: <b>{sessionId}</b> · log channel: <b>{status}</b>
        {closeCode !== null && <span style={{ marginLeft: 8 }}>(close: {closeCode})</span>}
      </div>

      {tokenReady ? (
        <Stage sessionId={sessionId} />
      ) : (
        <div style={{ padding: 16, border: '1px dashed #999', borderRadius: 8, background: '#fff8e1' }}>
          <b>No auth token.</b> Append <code>?token=&lt;jwt&gt;</code> to the URL or log in via the
          regular flow first. The Stage WebSocket needs a Bearer token in the subprotocol.
        </div>
      )}

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
