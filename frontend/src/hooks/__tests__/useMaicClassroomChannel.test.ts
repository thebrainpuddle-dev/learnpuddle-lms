// hooks/__tests__/useMaicClassroomChannel.test.ts
//
// F2 (P0) — verifies the WS hook:
//   - opens against the right URL with the auth subprotocol;
//   - dispatches `maic.image.task` events into the store;
//   - ignores malformed / non-matching events;
//   - closes cleanly on unmount.

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useMaicClassroomChannel } from '../useMaicClassroomChannel';
import { useMaicMediaGenerationStore } from '../../stores/maicMediaGenerationStore';
import { useAuthStore } from '../../stores/authStore';

// ─── Mock WebSocket ──────────────────────────────────────────────────────────

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  url: string;
  protocols: string | string[] | undefined;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  closed = false;
  private openListeners: Array<() => void> = [];

  constructor(url: string, protocols?: string | string[]) {
    this.url = url;
    this.protocols = protocols;
    MockWebSocket.instances.push(this);
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
    const listeners = [...this.openListeners];
    this.openListeners = [];
    listeners.forEach((listener) => listener());
  }

  receive(data: unknown) {
    this.onmessage?.({ data: typeof data === 'string' ? data : JSON.stringify(data) });
  }

  close(code = 1000) {
    if (this.closed) return;
    this.closed = true;
    this.readyState = 3;
    this.onclose?.({ code });
  }

  addEventListener(type: string, listener: () => void, options?: { once?: boolean }) {
    if (type !== 'open') return;
    if (options?.once) {
      this.openListeners.push(listener);
    } else {
      this.openListeners.push(listener);
    }
  }
}

beforeEach(() => {
  MockWebSocket.instances = [];
  // @ts-expect-error — overriding the global WebSocket for the test run.
  global.WebSocket = MockWebSocket;

  // Reset stores
  useMaicMediaGenerationStore.getState().resetAll();
  useAuthStore.setState({
    accessToken: 'test-jwt',
    isAuthenticated: true,
    refreshToken: null,
    user: null,
  } as Partial<ReturnType<typeof useAuthStore.getState>> as ReturnType<
    typeof useAuthStore.getState
  >);
});

afterEach(() => {
  vi.useRealTimers();
});

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('useMaicClassroomChannel', () => {
  async function waitForSocket() {
    await waitFor(() => expect(MockWebSocket.instances.length).toBe(1));
    return MockWebSocket.instances[0];
  }

  test('opens a WS to the right URL with the Bearer subprotocol', async () => {
    renderHook(() => useMaicClassroomChannel('classroom-uuid-1'));

    const ws = await waitForSocket();
    expect(ws.url).toMatch(/\/ws\/maic\/classrooms\/classroom-uuid-1\/$/);
    expect(ws.protocols).toEqual(['Bearer.test-jwt']);
  });

  test('does not open a WS when classroomId is null', () => {
    renderHook(() => useMaicClassroomChannel(null));
    expect(MockWebSocket.instances.length).toBe(0);
  });

  test('does not open a WS when not authenticated', () => {
    useAuthStore.setState({
      accessToken: null,
      isAuthenticated: false,
    } as Partial<ReturnType<typeof useAuthStore.getState>> as ReturnType<
      typeof useAuthStore.getState
    >);

    renderHook(() => useMaicClassroomChannel('classroom-uuid-1'));
    expect(MockWebSocket.instances.length).toBe(0);
  });

  test('dispatches maic.image.task events into the store', async () => {
    renderHook(() => useMaicClassroomChannel('classroom-uuid-1'));
    const ws = await waitForSocket();

    act(() => {
      ws.open();
      ws.receive({
        type: 'maic.image.task',
        classroom_id: 'classroom-uuid-1',
        element_key: '0:0:0:el-1',
        status: 'done',
        src: 'https://cdn.example/wired.jpg',
        updated_at: '2026-04-28T12:00:00Z',
      });
    });

    const task = useMaicMediaGenerationStore.getState().getTask('0:0:0:el-1');
    expect(task?.status).toBe('done');
    expect(task?.src).toBe('https://cdn.example/wired.jpg');
  });

  test('ignores malformed JSON', async () => {
    renderHook(() => useMaicClassroomChannel('classroom-uuid-1'));
    const ws = await waitForSocket();

    act(() => {
      ws.open();
      ws.receive('not-json{{');
    });

    // Store still empty.
    expect(Object.keys(useMaicMediaGenerationStore.getState().tasks).length).toBe(
      0,
    );
  });

  test('ignores non-matching event types', async () => {
    renderHook(() => useMaicClassroomChannel('classroom-uuid-1'));
    const ws = await waitForSocket();

    act(() => {
      ws.open();
      ws.receive({
        type: 'maic.unrelated',
        classroom_id: 'classroom-uuid-1',
        element_key: '0:0:0:el-1',
        status: 'done',
      });
    });

    expect(Object.keys(useMaicMediaGenerationStore.getState().tasks).length).toBe(
      0,
    );
  });

  test('closes an open WS cleanly on unmount', async () => {
    const { unmount } = renderHook(() =>
      useMaicClassroomChannel('classroom-uuid-1'),
    );
    const ws = await waitForSocket();

    expect(ws.closed).toBe(false);
    act(() => {
      ws.open();
    });
    unmount();
    expect(ws.closed).toBe(true);
  });

  test('waits for a handshaking WS to open before closing on unmount', async () => {
    const { unmount } = renderHook(() =>
      useMaicClassroomChannel('classroom-uuid-1'),
    );
    const ws = await waitForSocket();

    unmount();
    expect(ws.closed).toBe(false);

    act(() => {
      ws.open();
    });
    expect(ws.closed).toBe(true);
  });

  test('auth rejection (4001) does not trigger reconnect', async () => {
    renderHook(() => useMaicClassroomChannel('classroom-uuid-1'));
    const ws = await waitForSocket();
    const setTimeoutSpy = vi.spyOn(global, 'setTimeout');

    // Drop existing setTimeout calls (if any) so we only inspect those
    // that follow the close — the hook itself doesn't queue any timers
    // before close, but be defensive in case implementation changes.
    setTimeoutSpy.mockClear();

    act(() => {
      ws.close(4001);
    });

    // No reconnect timer must have been scheduled.
    expect(setTimeoutSpy).not.toHaveBeenCalled();
    expect(MockWebSocket.instances.length).toBe(1);

    setTimeoutSpy.mockRestore();
  });
});
