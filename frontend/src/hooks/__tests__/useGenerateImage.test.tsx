/**
 * Tests for useGenerateImage (Phase 9, MAIC-916).
 *
 * Discipline: IO-boundary fake at the axios layer
 * (vi.spyOn(api, 'post')) — same pattern as
 * pages/dev/__tests__/MaicPBLDevPage.test.tsx. Real react-query, real
 * mutation lifecycle.
 */
import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { useGenerateImage } from '../useGenerateImage';
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

describe('useGenerateImage', () => {
  test('idle by default', () => {
    const { result } = renderHook(() => useGenerateImage(), { wrapper: _makeWrapper() });
    expect(result.current.isPending).toBe(false);
    expect(result.current.data).toBeUndefined();
  });

  test('POSTs to /api/maic/v2/media/generate-image/ with the request body', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: {
        media_id: 'm-1',
        url: 'https://storage.example/maic/t-1/image/m-1.png',
        provider: 'openai',
        model: 'dall-e-3',
        latency_ms: 1234,
        cost_usd_estimate: 0.04,
      },
    } as never);

    const { result } = renderHook(() => useGenerateImage(), { wrapper: _makeWrapper() });

    let returned: { media_id: string; url: string } | undefined;
    await act(async () => {
      returned = await result.current.mutateAsync({
        prompt: 'a fractions diagram',
        width: 1024,
        height: 1024,
        scene_id: 's-1',
      });
    });

    expect(post).toHaveBeenCalledWith(
      '/api/maic/v2/media/generate-image/',
      expect.objectContaining({ prompt: 'a fractions diagram', scene_id: 's-1' }),
    );
    // mutateAsync's resolved value is the direct truth source
    expect(returned?.media_id).toBe('m-1');
    expect(returned?.url).toContain('m-1.png');
    // react-query state catches up after a flush
    await waitFor(() => expect(result.current.data?.media_id).toBe('m-1'));
  });

  test('surfaces a 502 backend error via isError', async () => {
    vi.spyOn(api, 'post').mockRejectedValueOnce({
      response: { status: 502, data: { error: 'provider failed after retries' } },
      message: 'Request failed with status code 502',
    });

    const { result } = renderHook(() => useGenerateImage(), { wrapper: _makeWrapper() });

    await act(async () => {
      try {
        await result.current.mutateAsync({ prompt: 'x' });
      } catch {
        // mutateAsync re-throws; ignored — assertion is on react-query state
      }
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  test('does not retry on the client side (one POST per mutation)', async () => {
    const post = vi.spyOn(api, 'post').mockRejectedValueOnce(
      new Error('boom') as never,
    );

    const { result } = renderHook(() => useGenerateImage(), { wrapper: _makeWrapper() });

    await act(async () => {
      try {
        await result.current.mutateAsync({ prompt: 'x' });
      } catch { /* swallow */ }
    });

    // QueryClient retry: false + no internal retry in the hook → exactly 1 POST.
    // The backend orchestrator handles retry; the browser must NOT compound it.
    expect(post).toHaveBeenCalledTimes(1);
  });
});
