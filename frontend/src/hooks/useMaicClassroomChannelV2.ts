/**
 * MAIC v2 WebSocket client hook.
 *
 * Wire format mirrors the backend StatelessEvent vocabulary defined in
 * apps/maic/orchestration/director_graph.py (8 types). Keep this union
 * in sync with backend's _VALID_EVENT_TYPES — the JSON Schema codegen
 * lives in Phase 1 (MAIC-201) which will replace these hand-typed unions
 * with generated TS types.
 *
 * Auth: JWT in `Sec-WebSocket-Protocol: Bearer.<accessToken>` subprotocol —
 * matches the V1 hook pattern (useMaicClassroomChannel.ts) and the
 * notifications consumer (apps/notifications/middleware.py).  Tokens
 * MUST NOT be passed via query string (browser-history / proxy-log /
 * referrer leak).
 *
 * Phase 0 scope: open + receive + send. No auto-reconnect (lands in
 * Phase 1's MAIC-101 once we have a real session lifecycle).
 *
 * Backend ticket: MAIC-005 (apps/maic/orchestration/director_graph.py).
 * Replaces: useMaicClassroomChannel.ts (gated behind MAIC_V2_ENABLED).
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuthStore } from '../stores/authStore';

// ── Wire types — keep in sync with backend _VALID_EVENT_TYPES ─────────

export type MaicEvent =
  | {
      type: 'agent_start';
      data: {
        messageId: string;
        agentId: string;
        agentName: string;
        agentAvatar: string | null;
        agentColor: string;
      };
    }
  | { type: 'text_delta'; data: { content: string; messageId: string } }
  | {
      type: 'action';
      data: {
        actionId: string;
        actionName: string;
        params: Record<string, unknown>;
        agentId: string;
        messageId: string;
      };
    }
  | { type: 'agent_end'; data: { messageId: string; agentId: string } }
  | { type: 'thinking'; data: { stage: string; agentId?: string } }
  | { type: 'cue_user'; data: { fromAgentId?: string } }
  | {
      type: 'speech_audio';
      data: { audioId: string; format: string; base64?: string; url?: string };
    }
  | { type: 'error'; data: { message: string } };

export type MaicChannelStatus =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'closed'
  | 'error';

export type MaicSendMessage =
  | { action: 'start'; data?: Record<string, unknown> }
  | { action: 'interrupt' | 'resume' | 'stop'; data?: Record<string, unknown> };

export interface UseMaicChannelV2Options {
  /** Session id — used in the WS path. */
  sessionId: string;
  /** Override the WS base URL (defaults to current page host). */
  baseUrl?: string;
  /** Skip the auto-connect on mount; caller can flip via `enabled`. */
  autoConnect?: boolean;
}

export interface UseMaicChannelV2Result {
  status: MaicChannelStatus;
  events: MaicEvent[];
  /** Last close code, populated when status='closed'. */
  closeCode: number | null;
  send: (msg: MaicSendMessage) => void;
  reset: () => void;
}

// ── URL builder ────────────────────────────────────────────────────────

function deriveWsUrl(sessionId: string, baseUrl?: string): string {
  // Path uses /ws/maic/v2/classroom/ — the v2 segment avoids collision
  // with the V1 /ws/maic/classrooms/<uuid>/ route from
  // apps/courses/routing.py.  See READINESS-AUDIT §Issue-3.
  if (baseUrl) return `${baseUrl}/ws/maic/v2/classroom/${sessionId}/`;
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/maic/v2/classroom/${sessionId}/`;
}

// ── Hook ───────────────────────────────────────────────────────────────

export function useMaicClassroomChannelV2({
  sessionId,
  baseUrl,
  autoConnect = true,
}: UseMaicChannelV2Options): UseMaicChannelV2Result {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<MaicChannelStatus>('idle');
  const [events, setEvents] = useState<MaicEvent[]>([]);
  const [closeCode, setCloseCode] = useState<number | null>(null);
  const accessToken = useAuthStore((s) => s.accessToken);

  useEffect(() => {
    if (!autoConnect) return;

    setStatus('connecting');
    setCloseCode(null);
    const url = deriveWsUrl(sessionId, baseUrl);

    // JWT auth via Sec-WebSocket-Protocol: Bearer.<token> — same pattern
    // the V1 hook + notifications consumer use.  Spec requires an array;
    // including a bare 'Bearer' as fallback satisfies servers that may
    // strip the dotted form (defensive — matches V1 behavior).
    const subprotocols = accessToken
      ? [`Bearer.${accessToken}`, 'Bearer']
      : undefined;

    const ws = subprotocols
      ? new WebSocket(url, subprotocols)
      : new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setStatus('open');
    ws.onclose = (e) => {
      setStatus('closed');
      setCloseCode(e.code ?? null);
    };
    ws.onerror = () => setStatus('error');
    ws.onmessage = (e) => {
      let data = e.data;
      if (typeof data !== 'string') {
        // Phase 5 may switch to binary speech_audio frames — Phase 0
        // ignores non-string frames (forward-compat, no crash).
        return;
      }
      try {
        const evt = JSON.parse(data) as MaicEvent;
        if (!evt || typeof evt !== 'object' || !('type' in evt)) {
          // Malformed but parseable — drop silently to keep the UI alive.
          return;
        }
        setEvents((prev) => [...prev, evt]);
      } catch {
        // Non-JSON frame — ignore.
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
    // accessToken dep included so token rotation triggers a fresh connect
  }, [sessionId, baseUrl, autoConnect, accessToken]);

  const send = useCallback((msg: MaicSendMessage) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      // Caller must wait for status === 'open'; we don't queue.
      return;
    }
    ws.send(JSON.stringify(msg));
  }, []);

  const reset = useCallback(() => setEvents([]), []);

  return { status, events, closeCode, send, reset };
}
