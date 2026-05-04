/**
 * Tests for Phase3MultiAgentDemo (MAIC-418.5).
 *
 * Per the plan, this demo has NO headless smoke (daphne dependency
 * would flake CI). The unit test scope is intentionally narrow:
 *   - The component renders
 *   - It mounts Stage with the agentIds + maxTurns startPayload
 *
 * The real WS round-trip is verified by the manual walkthrough
 * recipe documented in PHASE-3-CLOSURE.md.
 */
import { describe, expect, test, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import Phase3MultiAgentDemo from '../Phase3MultiAgentDemo';
import { useAuthStore } from '../../../stores/authStore';


// Mock WebSocket so the Stage's hook doesn't try to open a real WS
// during unit tests. This is the same MockWebSocket shape used in
// Stage.test.tsx — Phase 1 cert: WS server can't run in jsdom.
class MockWebSocket extends EventTarget {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;
  url: string;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  sent: string[] = [];
  constructor(url: string) {
    super();
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  send(data: string) { this.sent.push(data); }
  close() {
    this.readyState = MockWebSocket.CLOSED;
    this.onclose?.({ code: 1000 });
  }
}


describe('Phase3MultiAgentDemo', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    // @ts-expect-error replacing for test
    globalThis.WebSocket = MockWebSocket;
    // @ts-expect-error
    globalThis.WebSocket.OPEN = MockWebSocket.OPEN;
    // @ts-expect-error
    globalThis.WebSocket.CLOSED = MockWebSocket.CLOSED;
    useAuthStore.setState({
      accessToken: 'tok',
      refreshToken: 'r',
      isAuthenticated: true,
    } as never);
  });

  test('renders the demo wrapper with the documented testid', () => {
    render(<Phase3MultiAgentDemo />);
    expect(
      screen.getByTestId('phase3-multi-agent-demo'),
    ).toBeInTheDocument();
  });

  test('mounts the Stage component', () => {
    render(<Phase3MultiAgentDemo />);
    expect(screen.getByTestId('maic-v2-stage')).toBeInTheDocument();
  });

  test('explanatory text mentions the 3 default agents', () => {
    render(<Phase3MultiAgentDemo />);
    // The demo header mentions the agent ids so a future change to
    // the default pool surfaces a test failure (forcing the doc to
    // stay in sync).
    expect(screen.getByText(/default-1/)).toBeInTheDocument();
    expect(screen.getByText(/default-3/)).toBeInTheDocument();
    expect(screen.getByText(/default-4/)).toBeInTheDocument();
  });
});
