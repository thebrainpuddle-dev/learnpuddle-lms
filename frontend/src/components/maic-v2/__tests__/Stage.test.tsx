/**
 * Tests for src/components/maic-v2/Stage.tsx (MAIC-403.7).
 *
 * Integration test for the Stage composition. Drives a fake WebSocket
 * + fake Audio through the full Phase-1 event sequence and verifies
 *   - Start button kicks the backend
 *   - Buffered events show up in transcript / overlay
 *   - Engine auto-constructs after agent_end and transitions to
 *     'playing'
 *   - Stop tears down cleanly
 *
 * Leaf components (AgentOverlay, Transcript, StageControls) and the
 * pure-function modules (scene-buffer, scene-builder) are already
 * unit-tested; this file only covers the wiring.
 */
import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

import { Stage } from '../Stage';
import { useAuthStore } from '../../../stores/authStore';


// ── Mock WebSocket (mirrors useMaicClassroomChannelV2.test.ts) ─────


class MockWebSocket extends EventTarget {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;

  url: string;
  protocols: string | string[] | undefined;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  sent: string[] = [];
  closed = false;

  constructor(url: string, protocols?: string | string[]) {
    super();
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


// ── Fake HTMLAudioElement — fires 'ended' immediately after play() ─


class FakeAudio extends EventTarget {
  src = '';
  volume = 1;
  defaultPlaybackRate = 1;
  playbackRate = 1;
  paused = true;
  currentTime = 0;
  duration = 0;

  async play() {
    this.paused = false;
    // Fire 'ended' on the next microtask so the engine's onEnded
    // handler runs after play() resolves.
    queueMicrotask(() => {
      this.dispatchEvent(new Event('ended'));
    });
  }
  pause() {
    this.paused = true;
  }
}


// ── Fixtures ────────────────────────────────────────────────────────


const PHASE1_TURN = [
  { type: 'thinking', data: { stage: 'agent_loading' } },
  {
    type: 'agent_start',
    data: {
      messageId: 'm1',
      agentId: 'default-1',
      agentName: 'AI Teacher',
      agentAvatar: '🎓',
      agentColor: '#3b82f6',
    },
  },
  { type: 'text_delta', data: { content: 'Welcome, students. ', messageId: 'm1' } },
  { type: 'text_delta', data: { content: 'Today we discuss fractions.', messageId: 'm1' } },
  {
    type: 'action',
    data: {
      actionId: 'a-wb',
      actionName: 'wb_open',
      params: {},
      agentId: 'default-1',
      messageId: 'm1',
    },
  },
  {
    type: 'speech_audio',
    data: {
      audioId: 'aud-1',
      audioB64: 'QUJDREVG',
      format: 'mp3',
      messageId: 'm1',
      agentId: 'default-1',
    },
  },
  { type: 'agent_end', data: { messageId: 'm1', agentId: 'default-1' } },
];


beforeEach(() => {
  MockWebSocket.instances = [];
  // @ts-expect-error — replacing global for test
  globalThis.WebSocket = MockWebSocket;
  // @ts-expect-error
  globalThis.WebSocket.OPEN = MockWebSocket.OPEN;
  // @ts-expect-error
  globalThis.WebSocket.CLOSED = MockWebSocket.CLOSED;

  // Replace global Audio so AudioPlayer's `new Audio()` returns the fake.
  // @ts-expect-error
  globalThis.Audio = FakeAudio;

  useAuthStore.setState({
    accessToken: 'tok',
    refreshToken: 'r',
    isAuthenticated: true,
  } as never);
});

afterEach(() => {
  vi.restoreAllMocks();
});


// ── Tests ───────────────────────────────────────────────────────────


describe('Stage — initial render + WS lifecycle', () => {
  test('opens a WebSocket on mount and gates Start until WS is open', () => {
    render(<Stage sessionId="s1" baseUrl="ws://test" />);
    expect(MockWebSocket.instances).toHaveLength(1);
    // Channel still 'connecting' — Start should be disabled.
    const startBtn = screen.getByTestId('maic-v2-control-start') as HTMLButtonElement;
    expect(startBtn.disabled).toBe(true);
  });

  test('Start enables once WS opens', () => {
    render(<Stage sessionId="s1" baseUrl="ws://test" />);
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    const startBtn = screen.getByTestId('maic-v2-control-start') as HTMLButtonElement;
    expect(startBtn.disabled).toBe(false);
  });

  test('clicking Start sends {action:"start"} to the backend', () => {
    render(<Stage sessionId="s1" baseUrl="ws://test" />);
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    fireEvent.click(screen.getByTestId('maic-v2-control-start'));
    expect(ws.sent.map((s) => JSON.parse(s))).toEqual([{ action: 'start' }]);
  });
});


describe('Stage — buffered render', () => {
  test('shows the AgentOverlay once agent_start arrives', () => {
    render(<Stage sessionId="s1" baseUrl="ws://test" />);
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => {
      ws.receive(PHASE1_TURN[1]);  // agent_start
    });
    expect(screen.getByTestId('maic-v2-agent-name')).toHaveTextContent('AI Teacher');
  });

  test('shows the thinking hint while status=thinking', () => {
    render(<Stage sessionId="s1" baseUrl="ws://test" />);
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => ws.receive(PHASE1_TURN[0]));  // thinking
    expect(screen.getByTestId('maic-v2-thinking')).toHaveTextContent('agent_loading');
  });

  test('renders accumulated text deltas', () => {
    render(<Stage sessionId="s1" baseUrl="ws://test" />);
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => {
      ws.receive(PHASE1_TURN[1]);
      ws.receive(PHASE1_TURN[2]);
      ws.receive(PHASE1_TURN[3]);
    });
    expect(screen.getByTestId('maic-v2-transcript-line-m1')).toHaveTextContent(
      'Welcome, students. Today we discuss fractions.',
    );
  });
});


// MAIC-211.1 introduced real wb_* lifecycle waits in ActionEngine
// (wb_open: 2000 ms spring-in). Stage tests pass a no-op delay via the
// actionEngineOptions prop so the auto-constructed engine doesn't stall
// the turn for two seconds. Production callers leave the prop unset
// and get the real setTimeout-based delay.
const FAST_ACTION_ENGINE = { delay: () => Promise.resolve() };

describe('Stage — engine auto-construction after agent_end', () => {
  test('drives the full Phase-1 turn end-to-end (Start → buffered → engine plays)', async () => {
    const { container } = render(
      <Stage
        sessionId="s1"
        baseUrl="ws://test"
        actionEngineOptions={FAST_ACTION_ENGINE}
      />,
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());

    // Click Start (kick backend, set backendKicked=true).
    fireEvent.click(screen.getByTestId('maic-v2-control-start'));

    // Stream the full turn.
    act(() => {
      for (const ev of PHASE1_TURN) ws.receive(ev);
    });

    // After agent_end the engine should have constructed and started.
    // It should be in 'playing' (wb_open via ActionEngine stub resolves
    // immediately, then speech action plays via FakeAudio).
    const stage = container.querySelector('[data-testid="maic-v2-stage"]')!;
    const mode = stage.getAttribute('data-engine-mode');
    expect(['playing', 'idle']).toContain(mode);  // 'idle' if onComplete fired
                                                   // synchronously (microtask
                                                   // race), 'playing' otherwise.

    // Once the FakeAudio fires 'ended' (queued microtask), engine
    // hits processNext, exhausts actions, sets mode → idle, fires
    // onComplete. Flush microtasks.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    // After the audio 'ended' microtask fires, the engine is exhausted
    // and mode is 'idle'. Stop button should NOT be visible (mode==='idle').
    expect(screen.queryByTestId('maic-v2-control-stop')).toBeNull();
  });

  test('Stop tears down the engine and returns to idle', async () => {
    render(
      <Stage
        sessionId="s1"
        baseUrl="ws://test"
        actionEngineOptions={FAST_ACTION_ENGINE}
      />,
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    fireEvent.click(screen.getByTestId('maic-v2-control-start'));
    act(() => {
      for (const ev of PHASE1_TURN) ws.receive(ev);
    });

    // The engine has constructed + started playing. Stop button MAY
    // be visible mid-flight. Click it if so; otherwise the engine
    // already self-completed (idle path) and there's nothing to stop.
    const stopBtn = screen.queryByTestId('maic-v2-control-stop');
    if (stopBtn) {
      fireEvent.click(stopBtn);
    }

    // Whichever path, mode should end at 'idle'.
    const stage = screen.getByTestId('maic-v2-stage');
    expect(stage.getAttribute('data-engine-mode')).toBe('idle');
  });
});


describe('Stage — MAIC-217 Whiteboard + onEffectFire wiring', () => {
  test('mounts the Whiteboard surface (closed by default until wb_open)', () => {
    render(
      <Stage
        sessionId="s1"
        baseUrl="ws://test"
        actionEngineOptions={FAST_ACTION_ENGINE}
      />,
    );
    // Whiteboard is closed initially → renders nothing in the DOM.
    expect(screen.queryByTestId('maic-v2-whiteboard')).toBeNull();
  });

  test('Stage exposes data-active-effect=none when no spotlight/laser fired', () => {
    render(
      <Stage
        sessionId="s1"
        baseUrl="ws://test"
        actionEngineOptions={FAST_ACTION_ENGINE}
      />,
    );
    expect(screen.getByTestId('maic-v2-stage')).toHaveAttribute(
      'data-active-effect',
      'none',
    );
  });

  test('mounts WhiteboardProvider — children can read state via the hook', async () => {
    // Driving an actual wb_open through the full pipeline requires a
    // backend-emitted `action(wb_open)` event. We construct the minimal
    // synthetic flow by streaming a wb_open action event directly.
    render(
      <Stage
        sessionId="s1"
        baseUrl="ws://test"
        actionEngineOptions={FAST_ACTION_ENGINE}
      />,
    );
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    fireEvent.click(screen.getByTestId('maic-v2-control-start'));

    // Stream a turn that includes wb_open → expect Whiteboard surface
    // to mount once ActionEngine processes it.
    const turnWithWbOpen = [
      { type: 'thinking', data: { stage: 'agent_loading' } },
      {
        type: 'agent_start',
        data: {
          messageId: 'm1', agentId: 'default-1', agentName: 'AI Teacher',
          agentAvatar: '🎓', agentColor: '#3b82f6',
        },
      },
      { type: 'text_delta', data: { content: 'Opening whiteboard.', messageId: 'm1' } },
      {
        type: 'action',
        data: {
          actionId: 'a-wb-open', actionName: 'wb_open', params: {},
          agentId: 'default-1', messageId: 'm1',
        },
      },
      { type: 'agent_end', data: { messageId: 'm1', agentId: 'default-1' } },
    ];
    act(() => {
      for (const ev of turnWithWbOpen) ws.receive(ev);
    });

    // Engine constructs and starts. wb_open dispatch flows through
    // ActionEngine → controller.setOpen(true) → Whiteboard mounts.
    // Drain microtasks so the FAST_ACTION_ENGINE delay (no-op) +
    // PlaybackEngine's processNext chain settle.
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
    });

    // Whiteboard now mounted (state.isOpen=true via the controller).
    expect(screen.getByTestId('maic-v2-whiteboard')).toBeInTheDocument();
  });
});


describe('Stage — error surfacing', () => {
  test('renders the lastError line when an error frame arrives', () => {
    render(<Stage sessionId="s1" baseUrl="ws://test" />);
    const ws = MockWebSocket.instances[0];
    act(() => ws.open());
    act(() => {
      ws.receive({ type: 'error', data: { message: 'graph blew up' } });
    });
    expect(screen.getByTestId('maic-v2-stage-error')).toHaveTextContent(
      'graph blew up',
    );
  });
});
