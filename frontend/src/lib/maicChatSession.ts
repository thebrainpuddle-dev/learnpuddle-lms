// src/lib/maicChatSession.ts
//
// Session-scoped chat persistence for the MAIC tutor panel. We store the
// user+assistant conversation keyed by classroomId in sessionStorage so
// that:
//   1. Within a session, refreshing the page preserves the conversation.
//      The AI Tutor was previously wiping chat on every remount, which
//      made the "summarize key concepts" flow useless because the backend
//      never had the prior turns.
//   2. Across sessions (after the user closes the tab), the history is
//      cleared — which is what a per-session tutor should do, since the
//      chat context is specific to that study session.
//
// The IndexedDB chat persistence in `maicDb` is still used as the
// classroom-level authoritative record. This module is a lightweight
// session cache that gives us instant hydrate on remount.

import type { MAICChatMessage } from '../types/maic';

const MAX_PERSISTED = 50;   // cap storage growth — last 50 turns is plenty
const MAX_HISTORY_TO_BACKEND = 12;  // body size budget for SSE request

function keyFor(classroomId: string): string {
  return `maic:chat:${classroomId}`;
}

/** Read the persisted chat for a classroom. Returns [] on first visit or
 *  if sessionStorage is unavailable (SSR / privacy mode). */
export function hydrateChatFromSession(classroomId: string): MAICChatMessage[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.sessionStorage.getItem(keyFor(classroomId));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Defensive shape filter — strip anything missing required fields.
    return parsed.filter((m) =>
      m && typeof m === 'object'
      && typeof m.id === 'string'
      && typeof m.content === 'string'
      && typeof m.role === 'string'
    );
  } catch {
    return [];
  }
}

/** Persist the conversation for a classroom. Caps the stored array at
 *  the last MAX_PERSISTED entries to bound storage growth — sessionStorage
 *  has ~5 MB per origin and long conversations would eat into it. */
export function persistChatToSession(
  classroomId: string,
  messages: readonly MAICChatMessage[],
): void {
  if (typeof window === 'undefined') return;
  try {
    const trimmed = messages.slice(-MAX_PERSISTED);
    window.sessionStorage.setItem(keyFor(classroomId), JSON.stringify(trimmed));
  } catch {
    // QuotaExceededError, SecurityError in privacy mode, etc. Silently
    // skip — hydration just won't work on the next mount.
  }
}

/** Trim + reshape chat history into the compact form the backend accepts
 *  on the /maic/chat/ endpoint. We drop system messages (they're local
 *  error/info chips, not real turns) and normalize agent metadata. */
export function serializeChatHistoryForBackend(
  messages: readonly MAICChatMessage[],
): Array<{ role: 'user' | 'assistant'; content: string; agentId?: string }> {
  const out: Array<{ role: 'user' | 'assistant'; content: string; agentId?: string }> = [];
  for (const m of messages) {
    if (m.role !== 'user' && m.role !== 'assistant') continue;
    if (!m.content) continue;
    const entry: { role: 'user' | 'assistant'; content: string; agentId?: string } = {
      role: m.role,
      content: m.content,
    };
    if (m.role === 'assistant' && m.agentId) entry.agentId = m.agentId;
    out.push(entry);
  }
  return out.slice(-MAX_HISTORY_TO_BACKEND);
}
