/**
 * Tests for useGenerateVideo (Phase 9, MAIC-916).
 *
 * Same shape as useGenerateImage.test.tsx — IO-boundary fake at the
 * axios layer; real react-query lifecycle.
 */
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useGenerateVideo } from '../useGenerateVideo';
import api from '../../config/api';

function _makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useGenerateVideo', () => {
  test('POSTs to /api/maic/v2/media/generate-video/ with the request body', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: {
        media_id: 'v-1',
        url: 'https://storage.example/maic/t-1/video/v-1.mp4',
        provider: 'veo',
        model: 'veo-3.0-generate-preview',
        duration_seconds: 5,
        latency_ms: 45000,
        cost_usd_estimate: null,
      },
    } as never);

    const { result } = renderHook(() => useGenerateVideo(), { wrapper: _makeWrapper() });

    let returned: { media_id: string; duration_seconds: number } | undefined;
    await act(async () => {
      returned = await result.current.mutateAsync({
        prompt: 'a river flowing',
        duration_seconds: 5,
        aspect_ratio: '16:9',
      });
    });

    expect(post).toHaveBeenCalledWith(
      '/api/maic/v2/media/generate-video/',
      expect.objectContaining({ prompt: 'a river flowing', duration_seconds: 5 }),
    );
    // mutateAsync's resolved value is the direct truth source
    expect(returned?.media_id).toBe('v-1');
    expect(returned?.duration_seconds).toBe(5);
    await waitFor(() => expect(result.current.data?.media_id).toBe('v-1'));
  });

  test('surfaces 502 via isError', async () => {
    vi.spyOn(api, 'post').mockRejectedValueOnce({
      response: { status: 502 },
      message: 'Bad gateway',
    });

    const { result } = renderHook(() => useGenerateVideo(), { wrapper: _makeWrapper() });

    await act(async () => {
      try {
        await result.current.mutateAsync({ prompt: 'x' });
      } catch { /* swallow */ }
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  test('does not client-retry (orchestrator already retries)', async () => {
    const post = vi.spyOn(api, 'post').mockRejectedValueOnce(new Error('boom') as never);

    const { result } = renderHook(() => useGenerateVideo(), { wrapper: _makeWrapper() });

    await act(async () => {
      try {
        await result.current.mutateAsync({ prompt: 'x' });
      } catch { /* swallow */ }
    });

    expect(post).toHaveBeenCalledTimes(1);
  });
});
