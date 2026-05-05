/**
 * PBL dev probe page (Phase 7, MAIC-707).
 *
 * Hosts <PBLRenderer /> for end-to-end smoke testing against a real
 * backend (real design loop + real WS chat consumer at
 * /ws/maic/pbl/<id>/). Two entry points:
 *
 *   /dev/pbl/<sessionId>            — load an existing MaicPBLSession
 *   /dev/pbl/<sessionId>?model=...  — override the chat model id
 *
 * To create a fresh session for testing:
 *   curl -X POST -H 'Authorization: Bearer <jwt>' \
 *        -H 'Content-Type: application/json' \
 *        -d '{"topic":"Fractions","languageModelId":"claude-x"}' \
 *        http://localhost:8000/api/maic/v2/pbl/projects/
 * The response payload includes session_id; paste it into the URL.
 *
 * Auth: JWT via auth store, ?token= URL param, or VITE_MAIC_DEV_TOKEN
 * env var — same convenience as MaicV2Probe.
 */
import { useEffect, useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { PBLRenderer } from '../../components/maic/PBLRenderer';
import { useAuthStore } from '../../stores/authStore';
import api from '../../config/api';
import type { MAICPBLContent } from '../../types/maic-scenes';
import type { PBLProjectConfig } from '../../types/pbl';

interface PBLSessionResponse {
  session_id: string;
  ws_url: string;
  status: string;
  topic: string;
  language: string;
  project_config: PBLProjectConfig;
  chat_messages: unknown[];
}

export default function MaicPBLDevPage() {
  const { sessionId = '' } = useParams<{ sessionId: string }>();
  const [searchParams] = useSearchParams();
  const accessToken = useAuthStore((s) => s.accessToken);
  const [tokenReady, setTokenReady] = useState<boolean>(!!accessToken);
  const [data, setData] = useState<PBLSessionResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Same JWT-bootstrap convenience as MaicV2Probe — pull from URL or
  // env var if the auth store is empty so curl-driven sessions work.
  useEffect(() => {
    if (accessToken) {
      setTokenReady(true);
      return;
    }
    const t =
      searchParams.get('token') ||
      (import.meta.env.VITE_MAIC_DEV_TOKEN as string | undefined);
    if (!t) return;
    const refresh = searchParams.get('refresh') || t;
    try {
      sessionStorage.setItem('access_token', t);
      sessionStorage.setItem('refresh_token', refresh);
      sessionStorage.setItem('tenant_subdomain', 'dev');
      localStorage.setItem('access_token', t);
      localStorage.setItem('refresh_token', refresh);
      localStorage.setItem('tenant_subdomain', 'dev');
    } catch { /* storage may be disabled in sandboxes */ }
    useAuthStore.setState({
      accessToken: t,
      refreshToken: refresh,
      isAuthenticated: true,
    } as never);
    setTokenReady(true);
  }, [accessToken, searchParams]);

  useEffect(() => {
    if (!sessionId || !tokenReady) return;
    let cancelled = false;
    setLoadError(null);
    api
      .get<PBLSessionResponse>(`/api/maic/v2/pbl/projects/${sessionId}/`)
      .then((res) => {
        if (cancelled) return;
        setData(res.data);
      })
      .catch((err) => {
        if (cancelled) return;
        const status = err?.response?.status;
        const msg =
          status === 404
            ? 'Session not found (or wrong tenant).'
            : `Load failed: ${err?.message || 'unknown error'}`;
        setLoadError(msg);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, tokenReady]);

  if (!sessionId) {
    return (
      <div className="p-8 text-sm text-gray-700">
        <p className="font-medium text-base">PBL dev probe — missing session id</p>
        <p className="mt-2">
          Open <code className="font-mono">/dev/pbl/&lt;session_id&gt;</code> with a
          real <code>MaicPBLSession.id</code>. Create one with:
        </p>
        <pre className="mt-3 bg-gray-50 border border-gray-200 rounded p-3 text-xs overflow-x-auto">
{`curl -X POST -H 'Authorization: Bearer <jwt>' \\
     -H 'Content-Type: application/json' \\
     -d '{"topic":"Fractions","languageModelId":"claude-x"}' \\
     http://localhost:8000/api/maic/v2/pbl/projects/`}
        </pre>
      </div>
    );
  }

  if (!tokenReady) {
    return (
      <div className="p-8 text-sm text-gray-600">
        Waiting for auth token… set <code>?token=&lt;jwt&gt;</code> in the URL or
        the <code>VITE_MAIC_DEV_TOKEN</code> env var, then reload.
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="p-8 text-sm text-red-700">
        <p className="font-medium">Couldn't load session</p>
        <p className="mt-1 text-red-900">{loadError}</p>
      </div>
    );
  }

  if (!data) {
    return <div className="p-8 text-sm text-gray-600">Loading PBL session…</div>;
  }

  const modelOverride = searchParams.get('model') ?? 'claude-x';

  const pblContent: MAICPBLContent = {
    type: 'pbl',
    projectConfig: data.project_config,
  };

  return (
    <div className="h-screen flex flex-col">
      <div className="shrink-0 px-4 py-2 bg-gray-900 text-gray-100 text-xs flex items-center gap-3">
        <span className="font-mono">PBL session:</span>
        <span className="font-mono text-emerald-400">{data.session_id}</span>
        <span className="text-gray-400">•</span>
        <span>status: {data.status}</span>
        <span className="text-gray-400">•</span>
        <span>language: {data.language}</span>
        <span className="text-gray-400">•</span>
        <span>model: {modelOverride}</span>
      </div>
      <div className="flex-1 min-h-0">
        <PBLRenderer
          content={pblContent}
          sceneId={`pbl-${data.session_id}`}
          pblSessionId={data.session_id}
          languageModelId={modelOverride}
        />
      </div>
    </div>
  );
}
