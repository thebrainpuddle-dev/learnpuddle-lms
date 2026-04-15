// lib/maicSSE.ts — SSE streaming client for OpenMAIC endpoints

import type { MAICSSEEvent } from '../types/maic';

interface SSEOptions {
  url: string;
  body: Record<string, unknown>;
  token: string;
  onEvent: (event: MAICSSEEvent) => void;
  onError?: (error: Error) => void;
  onDone?: () => void;
  signal?: AbortSignal;
}

/**
 * Stream SSE events from a MAIC proxy endpoint.
 *
 * Uses fetch (not EventSource) so we can send POST with JWT auth headers.
 * Parses the SSE text protocol: "event: type\ndata: json\n\n"
 */
export async function streamMAIC({
  url,
  body,
  token,
  onEvent,
  onError,
  onDone,
  signal,
}: SSEOptions): Promise<void> {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || '';
  const fullUrl = `${baseUrl}${url}`;

  // Build headers — include tenant subdomain for localhost dev
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    Authorization: `Bearer ${token}`,
  };

  const hostname = window.location.hostname;
  if (hostname === 'localhost' || hostname === '127.0.0.1' || hostname.endsWith('.localhost')) {
    // Extract subdomain from URL (e.g., keystone.localhost) or fall back to storage
    const urlSubdomain = hostname.endsWith('.localhost')
      ? hostname.replace('.localhost', '')
      : null;
    const subdomain =
      urlSubdomain ||
      sessionStorage.getItem('tenant_subdomain') ||
      localStorage.getItem('tenant_subdomain');
    if (subdomain) {
      headers['X-Tenant-Subdomain'] = subdomain;
    }
  }

  let response: globalThis.Response;
  try {
    response = await fetch(fullUrl, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    onError?.(err instanceof Error ? err : new Error('Network error'));
    return;
  }

  if (!response.ok) {
    const text = await response.text();
    let message: string;
    try {
      message = JSON.parse(text).error || text;
    } catch {
      message = text;
    }
    onError?.(new Error(message));
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    onError?.(new Error('No response stream'));
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let currentEventType = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('event:')) {
          currentEventType = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          const dataStr = line.slice(5).trim();
          if (dataStr === '[DONE]') {
            onDone?.();
            return;
          }
          try {
            const data = JSON.parse(dataStr);
            const eventType = currentEventType || data.type || 'chat_message';
            onEvent({
              type: eventType as MAICSSEEvent['type'],
              data,
              sceneId: data.sceneId,
              agentId: data.agentId,
            });
          } catch {
            // Non-JSON data line, skip
          }
          currentEventType = '';
        }
      }
    }
  } catch (err) {
    if (signal?.aborted) return;
    onError?.(err instanceof Error ? err : new Error('Stream error'));
  } finally {
    reader.releaseLock();
    onDone?.();
  }
}
