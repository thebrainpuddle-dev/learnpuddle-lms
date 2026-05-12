// lib/maicSSE.ts — SSE streaming client for OpenMAIC endpoints

import { refreshAccessTokenForRequests } from '../config/api';
import { getAccessToken } from '../utils/authSession';
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

  const buildHeaders = (tokenOverride?: string): Record<string, string> => {
    // Build headers — include tenant subdomain for localhost dev.
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${tokenOverride || getAccessToken() || token}`,
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
    return headers;
  };

  const requestBody = JSON.stringify(body);
  const fetchStream = (tokenOverride?: string) => fetch(fullUrl, {
    method: 'POST',
    headers: buildHeaders(tokenOverride),
    body: requestBody,
    signal,
  });

  let response: globalThis.Response;
  try {
    response = await fetchStream();
    if (await shouldRefreshSseResponse(response)) {
      const refreshedToken = await refreshAccessTokenForRequests();
      response = await fetchStream(refreshedToken);
    }
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

async function shouldRefreshSseResponse(response: Response): Promise<boolean> {
  if (response.status === 401) return true;
  if (response.status !== 403) return false;

  try {
    const data = await response.clone().json();
    const detail = String(data?.error || data?.detail || '').toLowerCase();
    const code = String(data?.code || '').toLowerCase();
    const messages = Array.isArray(data?.messages)
      ? data.messages.map((item: any) => String(item?.message || '')).join(' ').toLowerCase()
      : '';
    return (
      code.includes('token_not_valid') ||
      (detail.includes('token') && (detail.includes('expired') || detail.includes('invalid'))) ||
      messages.includes('token')
    );
  } catch {
    try {
      const text = (await response.clone().text()).toLowerCase();
      return text.includes('token') && (text.includes('expired') || text.includes('invalid'));
    } catch {
      return false;
    }
  }
}
