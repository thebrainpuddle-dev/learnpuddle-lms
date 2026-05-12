import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../config/api', () => ({
  refreshAccessTokenForRequests: vi.fn(),
}));

vi.mock('../../utils/authSession', () => ({
  getAccessToken: vi.fn(),
}));

import { MAICActionEngine } from '../maicActionEngine';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { refreshAccessTokenForRequests } from '../../config/api';
import { getAccessToken } from '../../utils/authSession';

interface MockAudioInstance {
  src: string;
  volume: number;
  playbackRate: number;
  paused: boolean;
  onplaying: (() => void) | null;
  onended: (() => void) | null;
  onerror: (() => void) | null;
  play: ReturnType<typeof vi.fn>;
  pause: ReturnType<typeof vi.fn>;
  endNow: () => void;
}

const mockAudios: MockAudioInstance[] = [];

class MockAudio implements MockAudioInstance {
  src = '';
  volume = 1;
  playbackRate = 1;
  paused = false;
  onplaying: (() => void) | null = null;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  play = vi.fn().mockImplementation(() => {
    setTimeout(() => {
      if (!this.paused) this.onplaying?.();
    }, 0);
    return Promise.resolve();
  });
  pause = vi.fn().mockImplementation(() => {
    this.paused = true;
  });
  constructor() {
    mockAudios.push(this);
  }
  endNow() {
    this.onended?.();
  }
}

function mp3Response(status = 200): Response {
  if (status !== 200) {
    return new Response(null, { status });
  }
  return new Response(
    new Blob([new Uint8Array([0xff, 0xfb, 0x90, 0x00])], { type: 'audio/mpeg' }),
    { status: 200 },
  );
}

function authHeaderAt(callIndex: number): string | undefined {
  const fetchMock = vi.mocked(global.fetch);
  const init = fetchMock.mock.calls[callIndex]?.[1] as RequestInit | undefined;
  const headers = init?.headers as Record<string, string> | undefined;
  return headers?.Authorization;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAudios.length = 0;
  vi.mocked(getAccessToken).mockReturnValue('fresh-token');
  vi.mocked(refreshAccessTokenForRequests).mockResolvedValue('refreshed-token');
  global.Audio = MockAudio as unknown as typeof Audio;
  global.URL.createObjectURL = vi.fn(() => 'blob:tts-auth-retry');
  global.URL.revokeObjectURL = vi.fn();
  useMAICStageStore.setState({
    agents: [
      {
        id: 'a1',
        name: 'Professor Sharma',
        role: 'professor',
        voiceId: 'en-IN-PrabhatNeural',
      } as any,
    ],
    speakingAgentId: null,
    speechText: null,
    spotlightElementId: null,
    scenes: [],
    currentSceneIndex: 0,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('MAICActionEngine TTS auth refresh', () => {
  test('prefetch uses the current stored access token instead of the constructor token', async () => {
    const fetchMock = vi.fn().mockResolvedValue(mp3Response());
    global.fetch = fetchMock as unknown as typeof fetch;

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 'stale-constructor-token' });
    engine.prefetchSpeech({ type: 'speech', agentId: 'a1', text: 'current token please' } as any);

    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(authHeaderAt(0)).toBe('Bearer fresh-token');

    engine.dispose();
  });

  test('retries a live speech TTS request once after refreshing on 401', async () => {
    vi.mocked(getAccessToken).mockReturnValue('expired-token');
    vi.mocked(refreshAccessTokenForRequests).mockResolvedValue('new-live-token');
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(mp3Response(401))
      .mockResolvedValueOnce(mp3Response());
    global.fetch = fetchMock as unknown as typeof fetch;

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 'expired-constructor-token' });
    const playPromise = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'recover after token refresh',
    } as any);

    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(refreshAccessTokenForRequests).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(authHeaderAt(0)).toBe('Bearer expired-token');
    expect(authHeaderAt(1)).toBe('Bearer new-live-token');
    expect(mockAudios).toHaveLength(1);
    expect(mockAudios[0].play).toHaveBeenCalled();

    mockAudios[0].endNow();
    await playPromise;
    engine.dispose();
  });

  test('retries a live speech TTS request after token-related 403', async () => {
    vi.mocked(getAccessToken).mockReturnValue('expired-token');
    vi.mocked(refreshAccessTokenForRequests).mockResolvedValue('new-live-token');
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(
        JSON.stringify({ code: 'token_not_valid', detail: 'Token is invalid or expired' }),
        { status: 403, headers: { 'Content-Type': 'application/json' } },
      ))
      .mockResolvedValueOnce(mp3Response());
    global.fetch = fetchMock as unknown as typeof fetch;

    const engine = new MAICActionEngine({ ttsEndpoint: '/tts', token: 'expired-constructor-token' });
    const playPromise = engine.execute({
      type: 'speech',
      agentId: 'a1',
      text: 'recover after token-related forbidden',
    } as any);

    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(refreshAccessTokenForRequests).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(authHeaderAt(1)).toBe('Bearer new-live-token');
    mockAudios[0].endNow();
    await playPromise;
    engine.dispose();
  });
});
