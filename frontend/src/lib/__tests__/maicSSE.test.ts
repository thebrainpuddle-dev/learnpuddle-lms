import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../config/api', () => ({
  refreshAccessTokenForRequests: vi.fn(),
}));

vi.mock('../../utils/authSession', () => ({
  getAccessToken: vi.fn(),
}));

import { refreshAccessTokenForRequests } from '../../config/api';
import { getAccessToken } from '../../utils/authSession';
import { streamMAIC } from '../maicSSE';

function sseResponse(payload: string): Response {
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(payload));
      controller.close();
    },
  });
  return new Response(stream, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

function fetchAuthHeader(callIndex: number): string | undefined {
  const fetchMock = vi.mocked(global.fetch);
  const init = fetchMock.mock.calls[callIndex]?.[1] as RequestInit | undefined;
  const headers = init?.headers as Record<string, string> | undefined;
  return headers?.Authorization;
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getAccessToken).mockReturnValue('stored-token');
  vi.mocked(refreshAccessTokenForRequests).mockResolvedValue('new-sse-token');
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('streamMAIC auth refresh', () => {
  test('uses current stored token for MAIC SSE requests', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse('event: chat_message\ndata: {"content":"ok"}\n\ndata: [DONE]\n\n'),
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    const onEvent = vi.fn();
    const onDone = vi.fn();
    await streamMAIC({
      url: '/v1/teacher/maic/chat/',
      body: { message: 'hello' },
      token: 'constructor-token',
      onEvent,
      onDone,
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchAuthHeader(0)).toBe('Bearer stored-token');
    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({
      type: 'chat_message',
      data: { content: 'ok' },
    }));
    expect(onDone).toHaveBeenCalled();
  });

  test('refreshes and retries once after a 401 before reading the stream', async () => {
    vi.mocked(getAccessToken).mockReturnValue('expired-token');
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'expired' }), { status: 401 }))
      .mockResolvedValueOnce(
        sseResponse('event: chat_message\ndata: {"content":"after refresh"}\n\ndata: [DONE]\n\n'),
      );
    global.fetch = fetchMock as unknown as typeof fetch;

    const onEvent = vi.fn();
    await streamMAIC({
      url: '/v1/teacher/maic/chat/',
      body: { message: 'hello' },
      token: 'expired-constructor-token',
      onEvent,
    });

    expect(refreshAccessTokenForRequests).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchAuthHeader(0)).toBe('Bearer expired-token');
    expect(fetchAuthHeader(1)).toBe('Bearer new-sse-token');
    expect(onEvent).toHaveBeenCalledWith(expect.objectContaining({
      type: 'chat_message',
      data: { content: 'after refresh' },
    }));
  });
});
