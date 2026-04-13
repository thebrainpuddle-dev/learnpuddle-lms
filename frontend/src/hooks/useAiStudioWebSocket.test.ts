// src/hooks/useAiStudioWebSocket.test.ts

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAiStudioWebSocket } from './useAiStudioWebSocket';
import type { AiStudioWsMessage } from './useAiStudioWebSocket';

// ─── Mock getAccessToken ───────────────────────────────────────────────────

vi.mock('../utils/authSession', () => ({
  getAccessToken: () => 'test-jwt-token',
}));

// ─── Mock WebSocket ────────────────────────────────────────────────────────

type WsListener = (event: any) => void;

class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: MockWebSocket[] = [];

  url: string;
  protocols: string | string[];
  readyState = MockWebSocket.CONNECTING;
  onopen: WsListener | null = null;
  onclose: WsListener | null = null;
  onmessage: WsListener | null = null;
  onerror: WsListener | null = null;

  sent: string[] = [];

  constructor(url: string, protocols?: string | string[]) {
    this.url = url;
    this.protocols = protocols ?? '';
    MockWebSocket.instances.push(this);
  }

  send(data: string) {
    this.sent.push(data);
  }

  close(code?: number) {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) {
      this.onclose({ code: code ?? 1000 });
    }
  }

  // Test helpers

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN;
    this.onopen?.({});
  }

  simulateMessage(msg: AiStudioWsMessage) {
    this.onmessage?.({ data: JSON.stringify(msg) });
  }

  simulateClose(code = 1006) {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code });
  }

  simulateError() {
    this.onerror?.({});
  }
}

// ─── Setup / teardown ──────────────────────────────────────────────────────

beforeEach(() => {
  MockWebSocket.instances = [];
  (globalThis as any).WebSocket = MockWebSocket;
});

afterEach(() => {
  delete (globalThis as any).WebSocket;
  vi.restoreAllMocks();
});

// ─── Helpers ───────────────────────────────────────────────────────────────

function latestWs(): MockWebSocket {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1];
}

// ─── Tests ─────────────────────────────────────────────────────────────────

describe('useAiStudioWebSocket', () => {
  it('connects when enabled with itemId', () => {
    const { unmount } = renderHook(() =>
      useAiStudioWebSocket({ itemId: 'lesson-1', enabled: true }),
    );

    expect(MockWebSocket.instances).toHaveLength(1);
    expect(latestWs().url).toContain('/ws/ai-studio/lesson-1/');
    expect(latestWs().protocols).toContain('Bearer.test-jwt-token');

    unmount();
  });

  it('does not connect when disabled', () => {
    const { unmount } = renderHook(() =>
      useAiStudioWebSocket({ itemId: 'lesson-1', enabled: false }),
    );

    expect(MockWebSocket.instances).toHaveLength(0);

    unmount();
  });

  it('does not connect when itemId is null', () => {
    const { unmount } = renderHook(() =>
      useAiStudioWebSocket({ itemId: null, enabled: true }),
    );

    expect(MockWebSocket.instances).toHaveLength(0);

    unmount();
  });

  it('sets isConnected to true on open', () => {
    const { result, unmount } = renderHook(() =>
      useAiStudioWebSocket({ itemId: 'lesson-1' }),
    );

    expect(result.current.isConnected).toBe(false);

    act(() => {
      latestWs().simulateOpen();
    });

    expect(result.current.isConnected).toBe(true);

    unmount();
  });

  it('calls onStatus on generation_status message', () => {
    const onStatus = vi.fn();
    const { unmount } = renderHook(() =>
      useAiStudioWebSocket({ itemId: 'lesson-1', onStatus }),
    );

    act(() => {
      latestWs().simulateOpen();
    });

    const msg: AiStudioWsMessage = {
      type: 'generation_status',
      status: 'GENERATING',
      phase: 'scenes',
      progress: { current_scene: 2, total_scenes: 5, percentage: 40 },
    };

    act(() => {
      latestWs().simulateMessage(msg);
    });

    expect(onStatus).toHaveBeenCalledTimes(1);
    expect(onStatus).toHaveBeenCalledWith(msg);

    unmount();
  });

  it('calls onComplete on generation_complete message', () => {
    const onComplete = vi.fn();
    const { unmount } = renderHook(() =>
      useAiStudioWebSocket({ itemId: 'lesson-1', onComplete }),
    );

    act(() => {
      latestWs().simulateOpen();
    });

    const msg: AiStudioWsMessage = {
      type: 'generation_complete',
      lesson_id: 'lesson-1',
      scene_count: 5,
    };

    act(() => {
      latestWs().simulateMessage(msg);
    });

    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete).toHaveBeenCalledWith(msg);

    unmount();
  });

  it('calls onError on generation_error message', () => {
    const onError = vi.fn();
    const { unmount } = renderHook(() =>
      useAiStudioWebSocket({ itemId: 'lesson-1', onError }),
    );

    act(() => {
      latestWs().simulateOpen();
    });

    const msg: AiStudioWsMessage = {
      type: 'generation_error',
      error: 'Something went wrong',
    };

    act(() => {
      latestWs().simulateMessage(msg);
    });

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError).toHaveBeenCalledWith(msg);

    unmount();
  });

  it('updates lastMessage on incoming message', () => {
    const { result, unmount } = renderHook(() =>
      useAiStudioWebSocket({ itemId: 'lesson-1' }),
    );

    act(() => {
      latestWs().simulateOpen();
    });

    expect(result.current.lastMessage).toBeNull();

    const msg: AiStudioWsMessage = {
      type: 'generation_status',
      status: 'GENERATING',
    };

    act(() => {
      latestWs().simulateMessage(msg);
    });

    expect(result.current.lastMessage).toEqual(msg);

    unmount();
  });

  it('disconnects on unmount', () => {
    const { unmount } = renderHook(() =>
      useAiStudioWebSocket({ itemId: 'lesson-1' }),
    );

    const ws = latestWs();
    act(() => {
      ws.simulateOpen();
    });

    unmount();

    // After unmount the close method should have been called
    expect(ws.readyState).toBe(MockWebSocket.CLOSED);
  });

  it('sends ping periodically', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });

    const { unmount } = renderHook(() =>
      useAiStudioWebSocket({ itemId: 'lesson-1' }),
    );

    act(() => {
      latestWs().simulateOpen();
    });

    expect(latestWs().sent).toHaveLength(0);

    // Advance past the 30s ping interval
    act(() => {
      vi.advanceTimersByTime(30_000);
    });

    expect(latestWs().sent).toHaveLength(1);
    expect(JSON.parse(latestWs().sent[0])).toEqual({ type: 'ping' });

    // Advance another 30s
    act(() => {
      vi.advanceTimersByTime(30_000);
    });

    expect(latestWs().sent).toHaveLength(2);

    unmount();
    vi.useRealTimers();
  });

  it('send() function sends JSON data', () => {
    const { result, unmount } = renderHook(() =>
      useAiStudioWebSocket({ itemId: 'lesson-1' }),
    );

    act(() => {
      latestWs().simulateOpen();
    });

    act(() => {
      result.current.send({ type: 'subscribe', channel: 'progress' });
    });

    expect(latestWs().sent).toHaveLength(1);
    expect(JSON.parse(latestWs().sent[0])).toEqual({
      type: 'subscribe',
      channel: 'progress',
    });

    unmount();
  });

  it('attempts reconnection with exponential backoff on unexpected close', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });

    const { unmount } = renderHook(() =>
      useAiStudioWebSocket({ itemId: 'lesson-1' }),
    );

    const firstWs = latestWs();
    act(() => {
      firstWs.simulateOpen();
    });

    // Simulate unexpected close (code 1006)
    act(() => {
      firstWs.simulateClose(1006);
    });

    expect(MockWebSocket.instances).toHaveLength(1); // not reconnected yet

    // Advance past initial reconnect delay (1s)
    act(() => {
      vi.advanceTimersByTime(1_000);
    });

    expect(MockWebSocket.instances).toHaveLength(2); // reconnected

    unmount();
    vi.useRealTimers();
  });

  it('does not reconnect on intentional close (code 1000)', () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'setInterval', 'clearInterval'] });

    const { unmount } = renderHook(() =>
      useAiStudioWebSocket({ itemId: 'lesson-1' }),
    );

    act(() => {
      latestWs().simulateOpen();
    });

    act(() => {
      latestWs().simulateClose(1000);
    });

    act(() => {
      vi.advanceTimersByTime(5_000);
    });

    // Should still be just one instance — no reconnect
    expect(MockWebSocket.instances).toHaveLength(1);

    unmount();
    vi.useRealTimers();
  });
});
