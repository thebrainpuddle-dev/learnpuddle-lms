/**
 * PBL chat WS client hook (Phase 7, MAIC-706).
 *
 * Wire format mirrors apps/maic_pbl/consumers.py:PBLChatConsumer.
 * Same JWT-in-subprotocol auth as useMaicClassroomChannelV2 — keeps
 * tokens out of query strings (history/proxy/referrer leak).
 *
 * Distinct from the classroom hook in two ways:
 *   1. WS path: `/ws/maic/pbl/<session_id>/`
 *   2. Text-only — no PlaybackEngine, no AudioPlayer, no widget_event.
 *      Upstream's PBL is text chat by design; TTS is classroom-only.
 *
 * The hook surfaces a per-message accumulator (`messages`) on top of
 * the raw event stream so callers can render assembled assistant
 * replies without re-implementing the text_delta concat themselves.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useAuthStore } from '../stores/authStore';

// ── Wire types — keep in sync with apps/maic_pbl/consumers.py ──────────

export type PBLEvent =
  | {
      type: 'agent_start';
      data: { agentName: string; agentType: 'question' | 'judge' };
    }
  | { type: 'text_delta'; data: { content: string } }
  | {
      type: 'agent_end';
      data: {
        agentName: string;
        complete: boolean;
        /** When Judge said COMPLETE and a next issue activated, the
         *  consumer includes the next issue's title here so the
         *  workspace UI can advance without a refetch. */
        advancedTo: string | null;
      };
    }
  | { type: 'error'; data: { message: string } };

export type PBLChannelStatus =
  | 'idle'
  | 'connecting'
  | 'open'
  | 'closed'
  | 'error';

export type PBLSendMessage =
  | {
      action: 'chat';
      data: {
        message: string;
        userRole?: string;
        languageModelId: string;
      };
    }
  | { action: 'interrupt' };

/** A single chat turn assembled from agent_start + N text_delta + agent_end. */
export interface PBLAssembledMessage {
  agentName: string;
  agentType: 'question' | 'judge';
  /** Cumulative text from text_delta frames. */
  content: string;
  /** True after agent_end has arrived. */
  finished: boolean;
  /** True when Judge replied with COMPLETE — issue advanced. */
  complete: boolean;
  advancedTo: string | null;
}

export interface UseMaicPBLChannelOptions {
  sessionId: string;
  baseUrl?: string;
  autoConnect?: boolean;
}

export interface UseMaicPBLChannelResult {
  status: PBLChannelStatus;
  events: PBLEvent[];
  /** Per-turn assembly derived from events. Index is turn order; the
   *  trailing entry is the in-flight reply during streaming. */
  messages: PBLAssembledMessage[];
  closeCode: number | null;
  send: (msg: PBLSendMessage) => void;
  reset: () => void;
}

// ── URL builder ────────────────────────────────────────────────────────

function deriveWsUrl(sessionId: string, baseUrl?: string): string {
  if (baseUrl) return `${baseUrl}/ws/maic/pbl/${sessionId}/`;
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws/maic/pbl/${sessionId}/`;
}

// ── Per-turn reducer ───────────────────────────────────────────────────

function _foldEvents(events: PBLEvent[]): PBLAssembledMessage[] {
  const out: PBLAssembledMessage[] = [];
  for (const evt of events) {
    if (evt.type === 'agent_start') {
      out.push({
        agentName: evt.data.agentName,
        agentType: evt.data.agentType,
        content: '',
        finished: false,
        complete: false,
        advancedTo: null,
      });
      continue;
    }
    const tail = out[out.length - 1];
    if (!tail || tail.finished) continue;  // stray frame — drop
    if (evt.type === 'text_delta') {
      tail.content += evt.data.content;
    } else if (evt.type === 'agent_end') {
      tail.finished = true;
      tail.complete = evt.data.complete;
      tail.advancedTo = evt.data.advancedTo;
    }
  }
  return out;
}

// ── Hook ───────────────────────────────────────────────────────────────

export function useMaicPBLChannel({
  sessionId,
  baseUrl,
  autoConnect = true,
}: UseMaicPBLChannelOptions): UseMaicPBLChannelResult {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<PBLChannelStatus>('idle');
  const [events, setEvents] = useState<PBLEvent[]>([]);
  const [closeCode, setCloseCode] = useState<number | null>(null);
  const accessToken = useAuthStore((s) => s.accessToken);

  useEffect(() => {
    if (!autoConnect) return;

    setStatus('connecting');
    setCloseCode(null);
    const url = deriveWsUrl(sessionId, baseUrl);

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
      const raw = e.data;
      if (typeof raw !== 'string') return;
      try {
        const evt = JSON.parse(raw) as PBLEvent;
        if (!evt || typeof evt !== 'object' || !('type' in evt)) return;
        setEvents((prev) => [...prev, evt]);
      } catch {
        // Non-JSON frame — drop silently.
      }
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [sessionId, baseUrl, autoConnect, accessToken]);

  const send = useCallback((msg: PBLSendMessage) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify(msg));
  }, []);

  const reset = useCallback(() => setEvents([]), []);

  const messages = useMemo(() => _foldEvents(events), [events]);

  return { status, events, messages, closeCode, send, reset };
}
