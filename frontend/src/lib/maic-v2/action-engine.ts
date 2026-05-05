/**
 * Action Engine — synchronous action dispatcher for the playback engine.
 *
 * Source: THU-MAIC/OpenMAIC main lib/action/engine.ts (716 lines)
 *
 * Phase 2 scope (this file):
 *   ✓ wb_open    — set whiteboard.isOpen=true, wait for spring-in
 *   ✓ wb_close   — set whiteboard.isOpen=false, wait for spring-out
 *   ✓ wb_clear   — cascade-fade elements out, then empty array
 *   ✓ wb_delete  — remove element by elementId, wait for fade-out
 *
 * Phase 2 still-to-fill (later sub-chunks of 211/212/213/214 add):
 *   - wb_draw_*  — element renderers (211.2, 212, 213, 214.1)
 *   - wb_edit_code — line-level splice (214.2)
 *
 * Phase deferrals (NOT to be filled in Phase 2):
 *   - widget_*   — Phase 6 (postMessage to widget iframe)
 *   - play_video — Phase 6 (cross-cuts widget surface)
 *   - discussion — already routed via PlaybackEngine._dispatchDiscussion;
 *                  reaches us only as a defensive resolve
 *   - history snapshots in wb_clear (`useWhiteboardHistoryStore`)  → Phase 8+
 *   - `ensureWhiteboardOpen` auto-open before any wb_draw_* — protocol
 *     requires explicit wb_open; we just log+continue if not.
 *
 * Constructor takes an OPTIONAL controller + delay:
 *   - No controller → lifecycle ops log a warning and skip state mutation
 *     but still resolve. This keeps PlaybackEngine unit tests fast (they
 *     never wire a whiteboard).
 *   - Custom delay → tests pass `() => Promise.resolve()` to skip the
 *     2 s spring-in. Production uses the real setTimeout-based delay.
 *
 * Used by:
 *   - frontend/src/lib/maic-v2/playback-engine.ts — awaits execute() for
 *     every SYNC_ACTION so emission order is preserved.
 *   - frontend/src/components/maic-v2/Stage.tsx — constructs us with a
 *     controller from WhiteboardProvider (MAIC-217 wires this).
 */
import type {
  Action,
  WidgetAnnotationAction,
  WidgetHighlightAction,
  WidgetRevealAction,
  WidgetSetStateAction,
} from './action-types';
import type {
  CodeLine,
  WhiteboardCodeElement,
  WhiteboardController,
  WhiteboardElement,
} from './whiteboard-state';
import { useWidgetIframeStore } from './widget-iframe-store';


// ── Animation timings (mirror upstream lib/action/engine.ts) ──────


const WB_OPEN_MS = 2000;   // upstream:338  — slow spring (stiffness 120, damping 18)
const WB_CLOSE_MS = 700;   // upstream:673  — 500 ms tween + 200 ms safety margin
const WB_DELETE_MS = 300;  // upstream:645
const WB_CLEAR_BASE_MS = 380;
const WB_CLEAR_PER_ELEMENT_MS = 55;
const WB_CLEAR_CAP_MS = 1400;
const WB_DRAW_COMPONENT_MS = 800;  // upstream:371,396,512,545 — fade-in for text/shape/line/table
const WB_EDIT_CODE_MS = 600;       // upstream:638 — line-edit transition
const WIDGET_ACTION_MS = 300;      // upstream:693,700,708,714 — quick post-dispatch settle


// ── Options ────────────────────────────────────────────────────────


export interface ActionEngineOptions {
  /**
   * Whiteboard mutator. Optional — when absent, wb_* lifecycle ops
   * log a warning (the action engine was constructed without a
   * Stage-provided controller) and skip the state mutation. They
   * still resolve so the playback loop continues.
   */
  whiteboard?: WhiteboardController;

  /**
   * Delay function for animation waits. Defaults to a real
   * setTimeout-based delay; tests pass `() => Promise.resolve()` to
   * skip the 2 s spring-in without juggling vitest fake timers.
   */
  delay?: (ms: number) => Promise<void>;
}


function defaultDelay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}


// ── ActionEngine ───────────────────────────────────────────────────


export class ActionEngine {
  private readonly whiteboard: WhiteboardController | undefined;
  private readonly delay: (ms: number) => Promise<void>;

  constructor(options: ActionEngineOptions = {}) {
    this.whiteboard = options.whiteboard;
    this.delay = options.delay ?? defaultDelay;
  }

  /**
   * Execute one action. PlaybackEngine awaits this so emission order
   * is preserved. Action-type routing branches here; sub-handlers do
   * the work + run the wait.
   */
  async execute(action: Action): Promise<void> {
    if (typeof console !== 'undefined' && console.debug) {
      console.debug('[ActionEngine v2]', action.type, action.id);
    }

    switch (action.type) {
      case 'wb_open':
        await this.executeWbOpen();
        return;
      case 'wb_close':
        await this.executeWbClose();
        return;
      case 'wb_clear':
        await this.executeWbClear();
        return;
      case 'wb_delete':
        await this.executeWbDelete(action.elementId);
        return;

      // Component-only renderers — MAIC-211.2 (text/shape/line/table),
      // MAIC-212 (latex), MAIC-213 (chart), MAIC-214.1 (code). All
      // share the same 800 ms fade-in (engine.ts:371, 396, 420, 456,
      // 512, 545, 575).
      case 'wb_draw_text':
      case 'wb_draw_shape':
      case 'wb_draw_line':
      case 'wb_draw_table':
      case 'wb_draw_latex':
      case 'wb_draw_chart':
      case 'wb_draw_code':
        await this.executeWbDrawComponent(action);
        return;

      case 'wb_edit_code':
        await this.executeWbEditCode(action);
        return;

      // MAIC-606: widget interaction surface. Each action dispatches
      // a postMessage to the active interactive iframe via the
      // widget-iframe-store, then waits a short settle window
      // matching upstream lib/action/engine.ts:693,700,708,714.
      case 'widget_highlight':
        await this.executeWidgetHighlight(action);
        return;
      case 'widget_setState':
        await this.executeWidgetSetState(action);
        return;
      case 'widget_annotation':
        await this.executeWidgetAnnotation(action);
        return;
      case 'widget_reveal':
        await this.executeWidgetReveal(action);
        return;

      case 'play_video':
        // DEFERRED: video playback surface — Phase 6+ (cross-cuts widget)
        return;

      // Defensive: never reaches here under Phase-1 routing, but the
      // playback engine is allowed to forward unknown sync actions
      // through us; resolve so the loop doesn't deadlock.
      default:
        return;
    }
  }

  /**
   * Clear any active fire-and-forget visual effects. Called on stop()
   * and on scene boundaries by the playback engine. Phase 2 keeps this
   * a no-op — Stage holds spotlight/laser state via onEffectFire and
   * clears it directly when the engine signals.  Revisit if Phase 5
   * moves effect ownership here.
   */
  clearEffects(): void {
    // Intentional no-op.
  }

  // ── wb_* lifecycle handlers ──────────────────────────────────────

  private async executeWbOpen(): Promise<void> {
    if (!this.whiteboard) {
      console.warn('[ActionEngine] wb_open: no whiteboard controller — skipping');
      await this.delay(WB_OPEN_MS);
      return;
    }
    this.whiteboard.setOpen(true);
    await this.delay(WB_OPEN_MS);
  }

  private async executeWbClose(): Promise<void> {
    if (!this.whiteboard) {
      console.warn('[ActionEngine] wb_close: no whiteboard controller — skipping');
      await this.delay(WB_CLOSE_MS);
      return;
    }
    this.whiteboard.setOpen(false);
    await this.delay(WB_CLOSE_MS);
  }

  private async executeWbDelete(elementId: string): Promise<void> {
    if (!this.whiteboard) {
      console.warn('[ActionEngine] wb_delete: no whiteboard controller — skipping');
      await this.delay(WB_DELETE_MS);
      return;
    }
    this.whiteboard.deleteElement(elementId);
    await this.delay(WB_DELETE_MS);
  }

  /**
   * Add a component-only element (text / shape / line / table) to the
   * registry and wait for the upstream fade-in. Mirrors upstream
   * engine.ts:341-371 (text), 373-397 (shape), 459-513 (table),
   * 515-546 (line) — all share the same 800 ms post-add wait.
   *
   * The action itself is the "element" stored in the registry; the
   * Whiteboard's switch on element.type routes to the right renderer.
   */
  private async executeWbDrawComponent(
    action: Action & {
      type:
        | 'wb_draw_text'
        | 'wb_draw_shape'
        | 'wb_draw_line'
        | 'wb_draw_table'
        | 'wb_draw_latex'
        | 'wb_draw_chart'
        | 'wb_draw_code';
    },
  ): Promise<void> {
    if (!this.whiteboard) {
      console.warn(`[ActionEngine] ${action.type}: no whiteboard controller — skipping`);
      await this.delay(WB_DRAW_COMPONENT_MS);
      return;
    }

    if (action.type === 'wb_draw_code') {
      // wb_draw_code arrives with `code: string`. We split into stable
      // per-line records here so wb_edit_code (below) can target lines
      // by id without re-deriving them. Initial IDs are L1..Ln per
      // index; new lines from edits get UUID-based IDs to avoid
      // collisions after splices.
      const lines: CodeLine[] = (action.code ?? '').split('\n').map((content, i) => ({
        id: `L${i + 1}`,
        content,
      }));
      const augmented: WhiteboardCodeElement = { ...action, lines };
      this.whiteboard.addElement(augmented);
    } else {
      this.whiteboard.addElement(action as unknown as WhiteboardElement);
    }

    await this.delay(WB_DRAW_COMPONENT_MS);
  }

  /**
   * wb_edit_code — apply a line-level splice to a previously-drawn
   * code element. Mirrors upstream lib/action/engine.ts:578-638. Four
   * operations:
   *
   *   insert_after  — insert content (split on '\n') after lineId
   *   insert_before — insert content before lineId
   *   delete_lines  — remove every line whose id is in lineIds
   *   replace_lines — remove lineIds AND insert content at the
   *                   first removed-line's position
   *
   * Missing `lineId`/`lineIds` or unknown ids = no-op (logged at
   * warn). All line IDs that survive an edit retain their original
   * id; only inserted lines get fresh ids via crypto.randomUUID.
   */
  private async executeWbEditCode(
    action: Action & { type: 'wb_edit_code' },
  ): Promise<void> {
    if (!this.whiteboard) {
      console.warn('[ActionEngine] wb_edit_code: no whiteboard controller — skipping');
      await this.delay(WB_EDIT_CODE_MS);
      return;
    }

    const elementId = action.elementId;
    if (!elementId) {
      console.warn('[ActionEngine] wb_edit_code: missing elementId — skipping');
      await this.delay(WB_EDIT_CODE_MS);
      return;
    }

    // Resolve the target element by reading the current state. We
    // lazily access state via a getter the controller-side caller
    // (Stage) wires up via the WhiteboardProvider.  For action-engine
    // unit tests, the controller is a stub that records calls; tests
    // pre-seed `lines` via a helper.
    const target = this.whiteboard.getElement?.(elementId);
    if (!target || target.type !== 'wb_draw_code') {
      console.warn(
        `[ActionEngine] wb_edit_code: element ${JSON.stringify(elementId)} not found or not a code element — skipping`,
      );
      await this.delay(WB_EDIT_CODE_MS);
      return;
    }
    const codeElement = target as WhiteboardCodeElement;
    const currentLines: CodeLine[] = codeElement.lines ?? [];

    const newLines = applyEditOperation(action, currentLines);
    if (newLines === currentLines) {
      // applyEditOperation returns the same reference on no-op (e.g.
      // missing lineId). Nothing to update; still wait so the playback
      // loop's pacing is consistent across success and no-op edits.
      await this.delay(WB_EDIT_CODE_MS);
      return;
    }

    this.whiteboard.updateElement(elementId, {
      lines: newLines,
    } as Partial<WhiteboardElement>);
    await this.delay(WB_EDIT_CODE_MS);
  }

  // ── widget_* dispatch (MAIC-606) ─────────────────────────────────
  // Routes through useWidgetIframeStore.getSendMessage() so the
  // postMessage hits the active interactive iframe even when scenes
  // overlap. Wire format mirrors upstream lib/action/engine.ts:679-715
  // exactly (HIGHLIGHT_ELEMENT / SET_WIDGET_STATE / ANNOTATE_ELEMENT /
  // REVEAL_ELEMENT) so generated widget HTML works without changes.
  // No callback registered → log a warning + still resolve so the
  // playback loop's pacing stays consistent across active and
  // non-interactive scenes.

  private async executeWidgetHighlight(
    action: WidgetHighlightAction,
  ): Promise<void> {
    this.dispatchToWidget('HIGHLIGHT_ELEMENT', { target: action.target });
    await this.delay(WIDGET_ACTION_MS);
  }

  private async executeWidgetSetState(
    action: WidgetSetStateAction,
  ): Promise<void> {
    this.dispatchToWidget('SET_WIDGET_STATE', { state: action.state });
    await this.delay(WIDGET_ACTION_MS);
  }

  private async executeWidgetAnnotation(
    action: WidgetAnnotationAction,
  ): Promise<void> {
    this.dispatchToWidget('ANNOTATE_ELEMENT', { target: action.target });
    await this.delay(WIDGET_ACTION_MS);
  }

  private async executeWidgetReveal(
    action: WidgetRevealAction,
  ): Promise<void> {
    this.dispatchToWidget('REVEAL_ELEMENT', { target: action.target });
    await this.delay(WIDGET_ACTION_MS);
  }

  /** Resolve the active iframe's sendMessage callback and post.
   * Warn-but-continue when no callback is registered so a misordered
   * (widget action before scene mounted) playback doesn't deadlock. */
  private dispatchToWidget(
    type: string,
    payload: Record<string, unknown>,
  ): void {
    const send = useWidgetIframeStore.getState().getSendMessage();
    if (send) {
      send(type, payload);
    } else {
      console.warn(
        `[ActionEngine] ${type}: no widget-iframe callback registered — skipping`,
      );
    }
  }

  /**
   * Cascade-clear: flag isClearing=true so the surface fades each
   * element out (per-element delay handled by CSS keyframe + index),
   * wait for the cascade to finish, then empty the elements array
   * and reset the flag.
   *
   * Animation budget mirrors upstream: 380 ms base + 55 ms per
   * element, capped at 1400 ms (engine.ts:662). Empty whiteboard is a
   * no-op fast-path (engine.ts:653).
   */
  private async executeWbClear(): Promise<void> {
    if (!this.whiteboard) {
      console.warn('[ActionEngine] wb_clear: no whiteboard controller — skipping');
      await this.delay(WB_CLEAR_BASE_MS);
      return;
    }
    // Snapshot count BEFORE the controller's setClearing (which is
    // sync). We do not have access to the live element count here; the
    // caller already mutated the registry. We rely on the upstream cap
    // sizing (1400 ms) — knowing the exact count is a Phase 8+ concern.
    // DEFERRED: history snapshot — Phase 8+ (upstream pushSnapshot at
    //           lib/action/engine.ts:656).
    this.whiteboard.setClearing(true);
    await this.delay(WB_CLEAR_CAP_MS);
    this.whiteboard.clear();
    this.whiteboard.setClearing(false);
  }
}


// ── Helpers ────────────────────────────────────────────────────────


/**
 * Apply one wb_edit_code operation to a CodeLine[] and return the
 * resulting array. Returns the SAME reference if no change was made
 * (missing lineId, empty lineIds, etc.) so the caller can detect a
 * no-op via reference equality.
 *
 * Inserted lines get fresh IDs via crypto.randomUUID().slice(0, 8) —
 * 8 lowercase hex chars is plenty for collision avoidance within a
 * single code element. Surviving lines retain their original ids.
 *
 * Mirrors upstream lib/action/engine.ts:578-638.
 */
export function applyEditOperation(
  action: Action & { type: 'wb_edit_code' },
  currentLines: CodeLine[],
): CodeLine[] {
  switch (action.operation) {
    case 'insert_after': {
      if (!action.lineId) return currentLines;
      const idx = currentLines.findIndex((l) => l.id === action.lineId);
      if (idx < 0) return currentLines;
      const inserted = splitToCodeLines(action.content ?? '');
      return [
        ...currentLines.slice(0, idx + 1),
        ...inserted,
        ...currentLines.slice(idx + 1),
      ];
    }
    case 'insert_before': {
      if (!action.lineId) return currentLines;
      const idx = currentLines.findIndex((l) => l.id === action.lineId);
      if (idx < 0) return currentLines;
      const inserted = splitToCodeLines(action.content ?? '');
      return [
        ...currentLines.slice(0, idx),
        ...inserted,
        ...currentLines.slice(idx),
      ];
    }
    case 'delete_lines': {
      const ids = new Set(action.lineIds ?? []);
      if (ids.size === 0) return currentLines;
      const next = currentLines.filter((l) => !ids.has(l.id));
      return next.length === currentLines.length ? currentLines : next;
    }
    case 'replace_lines': {
      const ids = new Set(action.lineIds ?? []);
      if (ids.size === 0) return currentLines;
      // Insertion point: the first index of any line whose id is in
      // `ids`. After filtering out the removed ids, the new lines go
      // at the corresponding position in the filtered array — that's
      // the count of NOT-ids before the first match.
      let firstMatchIdx = -1;
      let insertIdxAfterFilter = 0;
      for (let i = 0; i < currentLines.length; i++) {
        if (ids.has(currentLines[i].id)) {
          firstMatchIdx = i;
          break;
        }
        insertIdxAfterFilter++;
      }
      if (firstMatchIdx < 0) return currentLines;
      const filtered = currentLines.filter((l) => !ids.has(l.id));
      const inserted = splitToCodeLines(action.content ?? '');
      return [
        ...filtered.slice(0, insertIdxAfterFilter),
        ...inserted,
        ...filtered.slice(insertIdxAfterFilter),
      ];
    }
    default:
      return currentLines;
  }
}


function splitToCodeLines(content: string): CodeLine[] {
  return content.split('\n').map((c) => ({
    id: makeLineId(),
    content: c,
  }));
}


/**
 * Generate a fresh line id. crypto.randomUUID is available in
 * jsdom/happy-dom + every browser we ship to. 8 hex chars is plenty
 * for collision-avoidance within a single code element (a few hundred
 * lines max in practice).
 */
function makeLineId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID().slice(0, 8);
  }
  // Defensive fallback for environments that don't expose crypto
  // (shouldn't happen on the targets we ship to, but it's cheap).
  return 'L' + Math.random().toString(36).slice(2, 10);
}


// ── Re-exports for callers that want to hand-write a controller ────


export type { CodeLine, WhiteboardCodeElement, WhiteboardController, WhiteboardElement };
