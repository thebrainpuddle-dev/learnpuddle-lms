// src/components/courses/ai-generation/helpers.ts
//
// Pure utility functions shared across AI generation components.

// ── ID Generator ─────────────────────────────────────────────────────────────

let idCounter = 0;

/**
 * Generate a unique, monotonically-increasing ID string.
 * Not cryptographically secure -- use only for ephemeral UI keys.
 */
export function genId(): string {
  idCounter += 1;
  return `gen-${Date.now()}-${idCounter}`;
}

// ── Error Extraction ─────────────────────────────────────────────────────────

/**
 * Pull a human-readable error message from an axios-style error, a plain
 * Error, or fall back to `fallback`.
 */
export function extractErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const data = (err as Record<string, unknown> & { response?: { data?: Record<string, unknown> } }).response?.data;
    if (data) {
      if (typeof data.error === 'string') return data.error;
      if (typeof data.detail === 'string') return data.detail;
      if (typeof data.message === 'string') return data.message;
    }
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

// ── File Size Formatting ─────────────────────────────────────────────────────

/**
 * Format a byte count into a compact, human-readable string.
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
