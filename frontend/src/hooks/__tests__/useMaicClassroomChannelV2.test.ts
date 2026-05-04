/**
 * Tests for useMaicClassroomChannelV2 — WebSocket lifecycle, JWT
 * subprotocol auth, MaicEvent collection, and URL derivation.
 *
 * Pattern mirrors src/hooks/__tests__/useMaicClassroomChannel.test.ts
 * (the V1 hook test) — MockWebSocket replacing global WebSocket so we
 * can drive lifecycle events synchronously.
 */
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useMaicClassroomChannelV2 } from '../useMaicClassroomChannelV2';
import { useAuthStore } from '../../stores/authStore';

// ── Mock WebSocket ─────────────────────────────────────────────────────

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;

  url: string;
  protocols: string | string[] | undefined;
  readyState: number = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  sent: string[] = [];
  closed = false;

  constructor(url: string, protocols?: string | string[]) {
    this.url = url;
    this.protocols = protocols;
    MockWebSocket.instances.push(this);
  }

  open() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.();
  }

  receive(data: unknown) {
    this.onmessage?.({ data: typeof data === 'string' ? data : JSON.stringify(data) });
  }

  send(data: string) {
    this.sent.push(data);
  }

  close(code = 1000) {
    if (this.closed) return;
    this.closed = true;
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code });
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  // @ts-expect-error — replacing global for test
  globalThis.WebSocket = MockWebSocket;
  // (1) and (3) constants live on the constructor in the real WebSocket too
  // @ts-expect-error
  globalThis.WebSocket.OPEN = MockWebSocket.OPEN;
  // @ts-expect-error
  globalThis.WebSocket.CLOSED = MockWebSocket.CLOSED;

  // Reset auth store between tests
  useAuthStore.setState({
    accessToken: 'test-token-abc',
    refreshToken: 'test-refresh',
    isAuthenticated: true,
  } as never);
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ── Tests ──────────────────────────────────────────────────────────────

describe('useMaicClassroomChannelV2', () => {
  test('opens WS to /ws/maic/v2/classroom/<sessionId>/ with Bearer.<token> subprotocol', () => {
    renderHook(() =>
      useMaicClassroomChannelV2({ sessionId: 'sess-1', baseUrl: 'ws://test.local' })
    );
    expect(MockWebSocket.instances).toHaveLength(1);
    const ws = MockWebSocket.instances[0];
    expect(ws.url).toBe('ws://test.local/ws/maic/v2/classroom/sess-1/');
    expect(ws.protocols).toEqual(['Bearer.test-token-abc', 'Bearer']);
  });

  test('status flow: connecting → open → closed', () => {
    const { result } = renderHook(() =>
      useMaicClassroomChannelV2({ sessionId: 's', baseUrl: 'ws://x' })
    );
    expect(result.current.status).toBe('connecting');

    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    expect(result.current.status).toBe('open');

    act(() => ws.close(1001));
    expect(result.current.status).toBe('closed');
    expect(result.current.closeCode).toBe(1001);
  });

  test('appends parsed JSON events in order', () => {
    const { result } = renderHook(() =>
      useMaicClassroomChannelV2({ sessionId: 's', baseUrl: 'ws://x' })
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());

    act(() =>
      ws.receive({
        type: 'agent_start',
        data: {
          messageId: 'm',
          agentId: 'a',
          agentName: 'A',
          agentAvatar: null,
          agentColor: '#000',
        },
      })
    );
    act(() => ws.receive({ type: 'text_delta', data: { content: 'hi', messageId: 'm' } }));
    act(() => ws.receive({ type: 'agent_end', data: { messageId: 'm', agentId: 'a' } }));

    expect(result.current.events.map((e) => e.type)).toEqual([
      'agent_start',
      'text_delta',
      'agent_end',
    ]);
  });

  test('ignores non-JSON and malformed frames without crashing', () => {
    const { result } = renderHook(() =>
      useMaicClassroomChannelV2({ sessionId: 's', baseUrl: 'ws://x' })
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());

    // Non-JSON
    act(() => ws.receive('not json at all'));
    // Parseable JSON but missing 'type'
    act(() => ws.receive(JSON.stringify({ wat: 'no type' })));
    // Valid event after the bad ones — must still land
    act(() => ws.receive({ type: 'thinking', data: { stage: 'x' } }));

    expect(result.current.events).toHaveLength(1);
    expect(result.current.events[0].type).toBe('thinking');
  });

  test('send() writes serialized JSON to the socket when open', () => {
    const { result } = renderHook(() =>
      useMaicClassroomChannelV2({ sessionId: 's', baseUrl: 'ws://x' })
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());

    act(() => result.current.send({ action: 'start', data: { topic: 'x' } }));
    expect(ws.sent).toEqual([JSON.stringify({ action: 'start', data: { topic: 'x' } })]);
  });

  test('send() is a no-op while not open (no queue, no throw)', () => {
    const { result } = renderHook(() =>
      useMaicClassroomChannelV2({ sessionId: 's', baseUrl: 'ws://x' })
    );
    const ws = MockWebSocket.instances[0];
    // Still in connecting state — readyState === 0
    act(() => result.current.send({ action: 'start' }));
    expect(ws.sent).toEqual([]);
  });

  test('send() accepts user_message variant (MAIC-410.2)', () => {
    // Locks the MaicSendMessage union: backend's MAIC-110.5 accepts
    // {action:'user_message', data:{text}}. Without this case in the
    // union, TS rejects the call site at compile time.
    const { result } = renderHook(() =>
      useMaicClassroomChannelV2({ sessionId: 's', baseUrl: 'ws://x' })
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => result.current.send({
      action: 'user_message',
      data: { text: 'what about the edge case?' },
    }));
    expect(ws.sent).toEqual([
      JSON.stringify({
        action: 'user_message',
        data: { text: 'what about the edge case?' },
      }),
    ]);
  });

  test('reset() clears the events buffer', () => {
    const { result } = renderHook(() =>
      useMaicClassroomChannelV2({ sessionId: 's', baseUrl: 'ws://x' })
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => ws.receive({ type: 'thinking', data: { stage: 's' } }));
    expect(result.current.events).toHaveLength(1);

    act(() => result.current.reset());
    expect(result.current.events).toHaveLength(0);
  });

  test('connects without subprotocol when accessToken is null', () => {
    useAuthStore.setState({ accessToken: null, refreshToken: null, isAuthenticated: false } as never);
    renderHook(() =>
      useMaicClassroomChannelV2({ sessionId: 's', baseUrl: 'ws://x' })
    );
    const ws = MockWebSocket.instances[0];
    expect(ws.protocols).toBeUndefined();
  });

  test('autoConnect=false skips socket creation', () => {
    renderHook(() =>
      useMaicClassroomChannelV2({ sessionId: 's', baseUrl: 'ws://x', autoConnect: false })
    );
    expect(MockWebSocket.instances).toHaveLength(0);
  });
});
