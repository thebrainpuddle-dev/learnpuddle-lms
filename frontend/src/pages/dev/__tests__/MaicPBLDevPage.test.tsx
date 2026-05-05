/**
 * Tests for MaicPBLDevPage (Phase 7, MAIC-707).
 *
 * Narrow scope, mirroring Phase3MultiAgentDemo.test.tsx pattern:
 *   - Component fetches the session via api.get
 *   - When the GET resolves, PBLRenderer mounts with the upstream
 *     projectConfig shape and shows the project header text
 *   - 404s and missing-id surfaces error UI
 *
 * Real WS round-trip is covered by the runbook in MAIC-708-CERTIFICATION.
 */
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import MaicPBLDevPage from '../MaicPBLDevPage';
import { useAuthStore } from '../../../stores/authStore';
import api from '../../../config/api';
import type { PBLProjectConfig } from '../../../types/pbl';

// Mock WebSocket so PBLRenderer's WS-mode chat hook doesn't open a
// real socket in jsdom. Identical shape to other dev-probe tests.
class MockWebSocket {
  static instances: MockWebSocket[] = [];
  static OPEN = 1;
  static CLOSED = 3;
  url: string;
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  sent: string[] = [];
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  send(data: string) { this.sent.push(data); }
  close() { this.readyState = MockWebSocket.CLOSED; }
}

function _config(): PBLProjectConfig {
  return {
    projectInfo: {
      title: 'Probe Project',
      description: 'A probe-mounted PBL session.',
    },
    agents: [],
    issueboard: { agent_ids: [], issues: [], current_issue_id: null },
    chat: { messages: [] },
    selectedRole: null,
  };
}

beforeEach(() => {
  MockWebSocket.instances = [];
  // @ts-expect-error
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

afterEach(() => {
  vi.restoreAllMocks();
});

function _renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/dev/pbl/:sessionId" element={<MaicPBLDevPage />} />
        <Route path="/dev/pbl" element={<MaicPBLDevPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('MaicPBLDevPage (MAIC-707)', () => {
  test('fetches session and renders PBLRenderer with projectConfig', async () => {
    const getSpy = vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: {
        session_id: 'sess-abc',
        ws_url: 'ws://localhost/ws/maic/pbl/sess-abc/',
        status: 'active',
        topic: 'Fractions',
        language: 'en',
        project_config: _config(),
        chat_messages: [],
      },
    } as never);

    _renderAt('/dev/pbl/sess-abc');

    await waitFor(() => {
      expect(screen.getByText('Probe Project')).toBeInTheDocument();
    });
    expect(getSpy).toHaveBeenCalledWith('/api/maic/v2/pbl/projects/sess-abc/');
    // Header strip surfaces the session id + status
    expect(screen.getByText('sess-abc')).toBeInTheDocument();
    expect(screen.getByText('status: active')).toBeInTheDocument();
  });

  test('shows 404 message when retrieve returns NotFound', async () => {
    vi.spyOn(api, 'get').mockRejectedValueOnce({
      response: { status: 404 },
      message: 'Request failed with status code 404',
    } as never);

    _renderAt('/dev/pbl/missing-id');

    await waitFor(() => {
      expect(screen.getByText("Couldn't load session")).toBeInTheDocument();
    });
    expect(
      screen.getByText('Session not found (or wrong tenant).'),
    ).toBeInTheDocument();
  });

  test('shows generic error message on non-404 failure', async () => {
    vi.spyOn(api, 'get').mockRejectedValueOnce({
      message: 'Network Error',
    } as never);

    _renderAt('/dev/pbl/anything');

    await waitFor(() => {
      expect(screen.getByText("Couldn't load session")).toBeInTheDocument();
    });
    expect(screen.getByText(/Network Error/i)).toBeInTheDocument();
  });

  test('shows guidance when no session id in URL', () => {
    _renderAt('/dev/pbl');
    expect(screen.getByText(/missing session id/i)).toBeInTheDocument();
  });

  test('honors ?model= override in the header strip', async () => {
    vi.spyOn(api, 'get').mockResolvedValueOnce({
      data: {
        session_id: 'sess-z',
        ws_url: 'ws://x/ws/maic/pbl/sess-z/',
        status: 'active',
        topic: 'T',
        language: 'en',
        project_config: _config(),
        chat_messages: [],
      },
    } as never);

    _renderAt('/dev/pbl/sess-z?model=claude-opus');

    await waitFor(() => {
      expect(screen.getByText('model: claude-opus')).toBeInTheDocument();
    });
  });
});
