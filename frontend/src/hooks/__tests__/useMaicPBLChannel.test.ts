/**
 * Tests for useMaicPBLChannel (Phase 7, MAIC-706).
 *
 * MockWebSocket pattern matches useMaicClassroomChannelV2.test.ts —
 * replace globalThis.WebSocket with a synchronous fake we can drive
 * via .open() / .receive() / .close() from inside `act()` blocks.
 */
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useMaicPBLChannel } from '../useMaicPBLChannel';
import { useAuthStore } from '../../stores/authStore';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;

  url: string;
  protocols: string | string[] | undefined;
  readyState: number = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;
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
    this.onmessage?.({
      data: typeof data === 'string' ? data : JSON.stringify(data),
    });
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
  // @ts-expect-error
  globalThis.WebSocket.OPEN = MockWebSocket.OPEN;
  // @ts-expect-error
  globalThis.WebSocket.CLOSED = MockWebSocket.CLOSED;

  useAuthStore.setState({
    accessToken: 'tok-xyz',
    refreshToken: 'refresh-xyz',
    isAuthenticated: true,
  } as never);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useMaicPBLChannel', () => {
  test('opens WS to /ws/maic/pbl/<sessionId>/ with Bearer.<token> subprotocol', () => {
    renderHook(() =>
      useMaicPBLChannel({ sessionId: 'pbl-sess-1', baseUrl: 'ws://test.local' }),
    );
    expect(MockWebSocket.instances).toHaveLength(1);
    const ws = MockWebSocket.instances[0];
    expect(ws.url).toBe('ws://test.local/ws/maic/pbl/pbl-sess-1/');
    expect(ws.protocols).toEqual(['Bearer.tok-xyz', 'Bearer']);
  });

  test('skips subprotocol when no access token', () => {
    useAuthStore.setState({ accessToken: null } as never);
    renderHook(() =>
      useMaicPBLChannel({ sessionId: 's', baseUrl: 'ws://x' }),
    );
    const ws = MockWebSocket.instances[0];
    expect(ws.protocols).toBeUndefined();
  });

  test('status flow: connecting → open → closed', () => {
    const { result } = renderHook(() =>
      useMaicPBLChannel({ sessionId: 's', baseUrl: 'ws://x' }),
    );
    expect(result.current.status).toBe('connecting');

    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    expect(result.current.status).toBe('open');

    act(() => ws.close(4003));
    expect(result.current.status).toBe('closed');
    expect(result.current.closeCode).toBe(4003);
  });

  test('error event flips status to error', () => {
    const { result } = renderHook(() =>
      useMaicPBLChannel({ sessionId: 's', baseUrl: 'ws://x' }),
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.onerror?.());
    expect(result.current.status).toBe('error');
  });

  test('appends parsed events in order', () => {
    const { result } = renderHook(() =>
      useMaicPBLChannel({ sessionId: 's', baseUrl: 'ws://x' }),
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() =>
      ws.receive({
        type: 'agent_start',
        data: { agentName: 'Q1', agentType: 'question' },
      }),
    );
    act(() => ws.receive({ type: 'text_delta', data: { content: 'Hi ' } }));
    act(() => ws.receive({ type: 'text_delta', data: { content: 'there.' } }));
    act(() =>
      ws.receive({
        type: 'agent_end',
        data: { agentName: 'Q1', complete: false, advancedTo: null },
      }),
    );

    expect(result.current.events.map((e) => e.type)).toEqual([
      'agent_start',
      'text_delta',
      'text_delta',
      'agent_end',
    ]);
  });

  test('messages reducer assembles a turn from start + deltas + end', () => {
    const { result } = renderHook(() =>
      useMaicPBLChannel({ sessionId: 's', baseUrl: 'ws://x' }),
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() =>
      ws.receive({
        type: 'agent_start',
        data: { agentName: 'Q1', agentType: 'question' },
      }),
    );
    act(() => ws.receive({ type: 'text_delta', data: { content: 'Hello' } }));
    act(() => ws.receive({ type: 'text_delta', data: { content: ', world.' } }));

    // In-flight: not finished yet
    expect(result.current.messages).toHaveLength(1);
    expect(result.current.messages[0]).toMatchObject({
      agentName: 'Q1',
      agentType: 'question',
      content: 'Hello, world.',
      finished: false,
      complete: false,
    });

    act(() =>
      ws.receive({
        type: 'agent_end',
        data: { agentName: 'Q1', complete: false, advancedTo: null },
      }),
    );
    expect(result.current.messages[0].finished).toBe(true);
  });

  test('judge COMPLETE end frame surfaces complete + advancedTo', () => {
    const { result } = renderHook(() =>
      useMaicPBLChannel({ sessionId: 's', baseUrl: 'ws://x' }),
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() =>
      ws.receive({
        type: 'agent_start',
        data: { agentName: 'J1', agentType: 'judge' },
      }),
    );
    act(() => ws.receive({ type: 'text_delta', data: { content: 'COMPLETE.' } }));
    act(() =>
      ws.receive({
        type: 'agent_end',
        data: { agentName: 'J1', complete: true, advancedTo: 'Next Issue' },
      }),
    );

    const msg = result.current.messages[0];
    expect(msg.complete).toBe(true);
    expect(msg.advancedTo).toBe('Next Issue');
    expect(msg.finished).toBe(true);
  });

  test('two consecutive turns produce two assembled messages', () => {
    const { result } = renderHook(() =>
      useMaicPBLChannel({ sessionId: 's', baseUrl: 'ws://x' }),
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    // Turn 1
    act(() =>
      ws.receive({
        type: 'agent_start',
        data: { agentName: 'Q1', agentType: 'question' },
      }),
    );
    act(() => ws.receive({ type: 'text_delta', data: { content: 'a' } }));
    act(() =>
      ws.receive({
        type: 'agent_end',
        data: { agentName: 'Q1', complete: false, advancedTo: null },
      }),
    );
    // Turn 2
    act(() =>
      ws.receive({
        type: 'agent_start',
        data: { agentName: 'J1', agentType: 'judge' },
      }),
    );
    act(() => ws.receive({ type: 'text_delta', data: { content: 'b' } }));
    act(() =>
      ws.receive({
        type: 'agent_end',
        data: { agentName: 'J1', complete: false, advancedTo: null },
      }),
    );

    expect(result.current.messages).toHaveLength(2);
    expect(result.current.messages[0]).toMatchObject({ agentName: 'Q1', content: 'a' });
    expect(result.current.messages[1]).toMatchObject({ agentName: 'J1', content: 'b' });
  });

  test('error frame is captured but does not produce a message', () => {
    const { result } = renderHook(() =>
      useMaicPBLChannel({ sessionId: 's', baseUrl: 'ws://x' }),
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => ws.receive({ type: 'error', data: { message: 'boom' } }));

    expect(result.current.events).toHaveLength(1);
    expect(result.current.events[0].type).toBe('error');
    expect(result.current.messages).toEqual([]);
  });

  test('non-JSON and non-string frames are dropped silently', () => {
    const { result } = renderHook(() =>
      useMaicPBLChannel({ sessionId: 's', baseUrl: 'ws://x' }),
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => ws.onmessage?.({ data: 'not json' }));
    act(() => ws.onmessage?.({ data: new ArrayBuffer(8) }));
    expect(result.current.events).toEqual([]);
    expect(result.current.status).toBe('open');
  });

  test('send before open is dropped (no queueing)', () => {
    const { result } = renderHook(() =>
      useMaicPBLChannel({ sessionId: 's', baseUrl: 'ws://x' }),
    );
    const ws = MockWebSocket.instances[0];
    act(() =>
      result.current.send({
        action: 'chat',
        data: { message: 'hi' },
      }),
    );
    expect(ws.sent).toEqual([]);
  });

  test('send after open serializes the chat payload', () => {
    const { result } = renderHook(() =>
      useMaicPBLChannel({ sessionId: 's', baseUrl: 'ws://x' }),
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() =>
      result.current.send({
        action: 'chat',
        data: {
          message: '@judge ok?',
          userRole: 'Designer',
        },
      }),
    );
    expect(ws.sent).toHaveLength(1);
    expect(JSON.parse(ws.sent[0])).toEqual({
      action: 'chat',
      data: {
        message: '@judge ok?',
        userRole: 'Designer',
      },
    });
  });

  test('send interrupt forwards the bare action', () => {
    const { result } = renderHook(() =>
      useMaicPBLChannel({ sessionId: 's', baseUrl: 'ws://x' }),
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => result.current.send({ action: 'interrupt' }));
    expect(JSON.parse(ws.sent[0])).toEqual({ action: 'interrupt' });
  });

  test('reset clears events and derived messages', () => {
    const { result } = renderHook(() =>
      useMaicPBLChannel({ sessionId: 's', baseUrl: 'ws://x' }),
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() =>
      ws.receive({
        type: 'agent_start',
        data: { agentName: 'Q1', agentType: 'question' },
      }),
    );
    act(() => result.current.reset());
    expect(result.current.events).toEqual([]);
    expect(result.current.messages).toEqual([]);
  });

  test('autoConnect=false skips opening a socket', () => {
    renderHook(() =>
      useMaicPBLChannel({
        sessionId: 's',
        baseUrl: 'ws://x',
        autoConnect: false,
      }),
    );
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  test('default URL derivation uses window.location host', () => {
    Object.defineProperty(window, 'location', {
      value: { protocol: 'https:', host: 'example.com' },
      writable: true,
    });
    renderHook(() => useMaicPBLChannel({ sessionId: 's' }));
    const ws = MockWebSocket.instances[0];
    expect(ws.url).toBe('wss://example.com/ws/maic/pbl/s/');
  });
});
