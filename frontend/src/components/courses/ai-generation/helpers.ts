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
 * Pull a human-readable error message from an axios-style API error, a plain
 * Error, or fall back to `fallback`.
 *
 * Canonical backend error shape (both DRF exceptions and manual error_response):
 *
 *   { "error": "<string>", "details": [...], "code": "optional" }
 *
 * - `error` is always a plain string.
 * - `details` is an optional list: [{ field: string|null, message: string }].
 * - Legacy `detail` key (pre-standardisation) is also handled for safety.
 */
export function extractErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const data = (err as Record<string, unknown> & { response?: { data?: Record<string, unknown> } }).response?.data;
    if (data) {
      // Canonical shape: error is always a plain string
      if (typeof data.error === 'string') return data.error;
      // Legacy DRF detail key (kept for safety during any transition)
      if (typeof data.detail === 'string') return data.detail;
      // Rare fallback: top-level message key
      if (typeof data.message === 'string') return data.message;
    }
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

/**
 * Extract per-field validation details from the canonical error shape.
 *
 * Returns an array of `{ field: string | null, message: string }` objects
 * from `response.data.details`, or an empty array if absent.
 *
 * Usage:
 *   const details = extractErrorDetails(err);
 *   details.forEach(({ field, message }) => setFieldError(field ?? '_form', message));
 */
export function extractErrorDetails(
  err: unknown,
): Array<{ field: string | null; message: string }> {
  if (err && typeof err === 'object' && 'response' in err) {
    const data = (
      err as Record<string, unknown> & {
        response?: { data?: Record<string, unknown> };
      }
    ).response?.data;
    if (data && Array.isArray(data.details)) {
      return (data.details as Array<Record<string, unknown>>)
        .filter((d) => typeof d.message === 'string')
        .map((d) => ({
          field: typeof d.field === 'string' ? d.field : null,
          message: d.message as string,
        }));
    }
  }
  return [];
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
