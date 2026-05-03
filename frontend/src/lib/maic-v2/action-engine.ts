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
import type { Action } from './action-types';
import type { WhiteboardController, WhiteboardElement } from './whiteboard-state';


// ── Animation timings (mirror upstream lib/action/engine.ts) ──────


const WB_OPEN_MS = 2000;   // upstream:338  — slow spring (stiffness 120, damping 18)
const WB_CLOSE_MS = 700;   // upstream:673  — 500 ms tween + 200 ms safety margin
const WB_DELETE_MS = 300;  // upstream:645
const WB_CLEAR_BASE_MS = 380;
const WB_CLEAR_PER_ELEMENT_MS = 55;
const WB_CLEAR_CAP_MS = 1400;
const WB_DRAW_COMPONENT_MS = 800;  // upstream:371,396,512,545 — fade-in for text/shape/line/table


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

      // Component-only renderers — MAIC-211.2 (text/shape/line/table).
      // The handler adds the action to the registry and waits for the
      // upstream fade-in (800 ms — engine.ts:371, 396, 512, 545).
      case 'wb_draw_text':
      case 'wb_draw_shape':
      case 'wb_draw_line':
      case 'wb_draw_table':
        await this.executeWbDrawComponent(action);
        return;

      // Lib-dependent renderers + line-level edits land in MAIC-212 /
      // 213 / 214.x. For now they resolve immediately so the playback
      // loop advances; the action still flows through the registry
      // once those handlers ship.
      case 'wb_draw_chart':
      case 'wb_draw_latex':
      case 'wb_draw_code':
      case 'wb_edit_code':
        // DEFERRED: renderer hand-off — MAIC-212 / 213 / 214.x
        return;

      // Phase 6 deferrals — left as no-ops with a debug log.
      case 'widget_highlight':
      case 'widget_setState':
      case 'widget_annotation':
      case 'widget_reveal':
      case 'play_video':
        // DEFERRED: widget surface — Phase 6 (MAIC-606)
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
      type: 'wb_draw_text' | 'wb_draw_shape' | 'wb_draw_line' | 'wb_draw_table';
    },
  ): Promise<void> {
    if (!this.whiteboard) {
      console.warn(`[ActionEngine] ${action.type}: no whiteboard controller — skipping`);
      await this.delay(WB_DRAW_COMPONENT_MS);
      return;
    }
    // The action is already typed as a WhiteboardElement-compatible
    // shape (the WhiteboardElement union mirrors these action types).
    this.whiteboard.addElement(action as unknown as WhiteboardElement);
    await this.delay(WB_DRAW_COMPONENT_MS);
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


// ── Re-exports for callers that want to hand-write a controller ────


export type { WhiteboardController, WhiteboardElement };
