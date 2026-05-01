// hooks/__tests__/useMaicClassroomChannel.test.ts
//
// F2 (P0) — verifies the WS hook:
//   - opens against the right URL with the auth subprotocol;
//   - dispatches `maic.image.task` events into the store;
//   - ignores malformed / non-matching events;
//   - closes cleanly on unmount.

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useMaicClassroomChannel } from '../useMaicClassroomChannel';
import { useMaicMediaGenerationStore } from '../../stores/maicMediaGenerationStore';
import { useAuthStore } from '../../stores/authStore';

// ─── Mock WebSocket ──────────────────────────────────────────────────────────

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  protocols: string | string[] | undefined;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  closed = false;

  constructor(url: string, protocols?: string | string[]) {
    this.url = url;
    this.protocols = protocols;
    MockWebSocket.instances.push(this);
  }

  open() {
    this.readyState = 1;
    this.onopen?.();
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
  test('opens a WS to the right URL with the Bearer subprotocol', () => {
    renderHook(() => useMaicClassroomChannel('classroom-uuid-1'));

    expect(MockWebSocket.instances.length).toBe(1);
    const ws = MockWebSocket.instances[0];
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

  test('dispatches maic.image.task events into the store', () => {
    renderHook(() => useMaicClassroomChannel('classroom-uuid-1'));
    const ws = MockWebSocket.instances[0];

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

  test('ignores malformed JSON', () => {
    renderHook(() => useMaicClassroomChannel('classroom-uuid-1'));
    const ws = MockWebSocket.instances[0];

    act(() => {
      ws.open();
      ws.receive('not-json{{');
    });

    // Store still empty.
    expect(Object.keys(useMaicMediaGenerationStore.getState().tasks).length).toBe(
      0,
    );
  });

  test('ignores non-matching event types', () => {
    renderHook(() => useMaicClassroomChannel('classroom-uuid-1'));
    const ws = MockWebSocket.instances[0];

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

  test('closes the WS cleanly on unmount', () => {
    const { unmount } = renderHook(() =>
      useMaicClassroomChannel('classroom-uuid-1'),
    );
    const ws = MockWebSocket.instances[0];

    expect(ws.closed).toBe(false);
    unmount();
    expect(ws.closed).toBe(true);
  });

  test('auth rejection (4001) does not trigger reconnect', () => {
    const setTimeoutSpy = vi.spyOn(global, 'setTimeout');

    renderHook(() => useMaicClassroomChannel('classroom-uuid-1'));
    const ws = MockWebSocket.instances[0];

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
