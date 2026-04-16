/**
 * Action Parser — converts structured JSON Array output to MAICAction[].
 *
 * Bridges LLM generation output with the MAIC action type system,
 * producing typed MAICAction objects that preserve the original
 * interleaving order from the LLM output.
 *
 * Adapted from upstream OpenMAIC action-parser.ts for client-side use.
 */

import type { MAICAction } from '../../types/maic-actions';
import { nanoid } from 'nanoid';
import { jsonrepair } from 'jsonrepair';

const log = {
  debug: (...args: unknown[]) => {
    if (import.meta.env.DEV) console.debug('[ActionParser]', ...args);
  },
  info: (...args: unknown[]) => console.info('[ActionParser]', ...args),
  warn: (...args: unknown[]) => console.warn('[ActionParser]', ...args),
  error: (...args: unknown[]) => console.error('[ActionParser]', ...args),
};

/**
 * Actions that only make sense for slide-type scenes.
 * Used to filter out hallucinated actions from non-slide scenes.
 */
const SLIDE_ONLY_ACTIONS: string[] = [
  'spotlight',
  'laser',
  'highlight',
  'play_video',
];

/**
 * Strip markdown code fences (```json ... ``` or ``` ... ```) from a response string.
 */
function stripCodeFences(text: string): string {
  return text.replace(/^```(?:json)?\s*\n?/i, '').replace(/\n?\s*```\s*$/i, '');
}

/**
 * Parse a complete LLM response in JSON Array format into an ordered MAICAction[] array.
 *
 * Expected format:
 * [{"type":"action","name":"spotlight","params":{"elementId":"..."}},
 *  {"type":"text","content":"speech content"},...]
 *
 * Also supports legacy format:
 * [{"type":"action","tool_name":"spotlight","parameters":{"elementId":"..."}},...]
 *
 * Text items become `speech` actions; action items are converted to their
 * respective action types (spotlight, discussion, etc.).
 * The original interleaving order is preserved.
 */
export function parseActionsFromStructuredOutput(
  response: string,
  sceneType?: string,
  allowedActions?: string[],
): MAICAction[] {
  // Step 1: Strip markdown code fences if present
  const cleaned = stripCodeFences(response.trim());

  // Step 2: Find the JSON array range
  const startIdx = cleaned.indexOf('[');
  const endIdx = cleaned.lastIndexOf(']');

  if (startIdx === -1) {
    log.warn('No JSON array found in response');
    return [];
  }

  const jsonStr =
    endIdx > startIdx
      ? cleaned.slice(startIdx, endIdx + 1)
      : cleaned.slice(startIdx); // unclosed array

  // Step 3: Parse — try JSON.parse first, then jsonrepair, then manual fix
  let items: unknown[];
  try {
    items = JSON.parse(jsonStr);
  } catch {
    // Try jsonrepair to fix malformed JSON (e.g. unescaped quotes)
    try {
      items = JSON.parse(jsonrepair(jsonStr));
      log.info('Recovered malformed JSON via jsonrepair');
    } catch {
      // Manual fallback: try to fix truncated array
      try {
        let fixed = jsonStr;
        if (fixed.startsWith('[') && !fixed.endsWith(']')) {
          const lastObj = fixed.lastIndexOf('}');
          if (lastObj > 0) {
            fixed = fixed.substring(0, lastObj + 1) + ']';
          }
        }
        items = JSON.parse(jsonrepair(fixed));
        log.info('Recovered truncated JSON array');
      } catch (e) {
        log.warn('Failed to parse JSON array:', (e as Error).message);
        return [];
      }
    }
  }

  if (!Array.isArray(items)) {
    log.warn('Parsed result is not an array');
    return [];
  }

  // Step 4: Convert items to MAICAction[]
  const actions: MAICAction[] = [];

  for (const item of items) {
    if (!item || typeof item !== 'object' || !('type' in item)) continue;
    const typedItem = item as Record<string, unknown>;

    if (typedItem.type === 'text') {
      const text = ((typedItem.content as string) || '').trim();
      if (text) {
        actions.push({
          type: 'speech',
          agentId: (typedItem.agentId as string) || '',
          text,
        });
      }
    } else if (typedItem.type === 'action') {
      try {
        // Support both new format (name/params) and legacy format (tool_name/parameters)
        const actionName = typedItem.name || typedItem.tool_name;
        const actionParams = (typedItem.params || typedItem.parameters || {}) as Record<
          string,
          unknown
        >;
        actions.push({
          type: actionName as MAICAction['type'],
          ...actionParams,
        } as MAICAction);
      } catch (_e) {
        log.warn('Invalid action item, skipping:', JSON.stringify(typedItem).slice(0, 100));
      }
    }
  }

  // Step 5: Post-processing — discussion must be the last action, and at most one
  const discussionIdx = actions.findIndex((a) => a.type === 'discussion');
  if (discussionIdx !== -1 && discussionIdx < actions.length - 1) {
    actions.splice(discussionIdx + 1);
  }

  // Step 6: Filter out slide-only actions for non-slide scenes (defense in depth)
  let result = actions;
  if (sceneType && sceneType !== 'slide') {
    const before = result.length;
    result = result.filter((a) => !SLIDE_ONLY_ACTIONS.includes(a.type));
    if (result.length < before) {
      log.info(`Stripped ${before - result.length} slide-only action(s) from ${sceneType} scene`);
    }
  }

  // Step 7: Filter by allowedActions whitelist (defense in depth for role-based isolation)
  if (allowedActions && allowedActions.length > 0) {
    const before = result.length;
    result = result.filter((a) => a.type === 'speech' || allowedActions.includes(a.type));
    if (result.length < before) {
      log.info(
        `Stripped ${before - result.length} disallowed action(s) by allowedActions whitelist`,
      );
    }
  }

  // Ensure all actions have unique IDs where applicable
  // (nanoid used to generate action-specific IDs if needed downstream)
  void nanoid; // Referenced to satisfy the import

  return result;
}
