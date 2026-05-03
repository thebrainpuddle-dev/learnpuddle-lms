/**
 * Action Engine — synchronous action dispatcher for the playback engine.
 *
 * Source (full version, 716 lines):
 *   https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/action/engine.ts
 *   /Volumes/CrucialX9/OpenMAIC/lib/action/engine.ts (commit 10b1fc83)
 *
 * Phase 1 scope: minimal stub.
 *
 *   Why minimal?  The playback engine awaits ActionEngine.execute()
 *   for all SYNC_ACTIONS so the agent's emission order is preserved.
 *   In Phase 1 we don't yet have a whiteboard renderer (Phase 2,
 *   MAIC-210) or widget iframe (Phase 6, MAIC-606) to hand actions
 *   to.  So Phase 1 resolves wb_* and widget_* actions to a
 *   no-op-immediate-Promise so the playback loop advances cleanly.
 *
 *   Speech is NOT routed through ActionEngine — the playback engine
 *   handles speech actions directly via the AudioPlayer (MAIC-402).
 *
 *   Spotlight/laser are also NOT routed through ActionEngine — the
 *   playback engine emits them through its onEffectFire callback for
 *   fire-and-forget rendering at the Stage level (MAIC-403).
 *
 * What grows in later phases:
 *   Phase 2 — fill wb_open / wb_draw_* / wb_clear / wb_delete / wb_close
 *             with real Canvas/SVG renderer calls
 *   Phase 5 — wire effectTimer + spotlight/laser DOM overlays here
 *             (or keep at Stage level — TBD)
 *   Phase 6 — fill widget_* with postMessage to widget iframe
 *
 * Used by:
 *   - frontend/src/lib/maic-v2/playback-engine.ts (MAIC-401.3)
 */
import type { Action } from './action-types';

/** ActionEngine — Phase 1 stub. */
export class ActionEngine {
  /**
   * Execute one action.  Phase 1 returns a resolved Promise for all
   * sync actions so the playback engine's `await this.actionEngine
   * .execute(action)` advances immediately.  Real renderer calls land
   * in Phase 2 / 5 / 6.
   *
   * Speech actions are NOT routed here — see module docstring.
   */
  async execute(action: Action): Promise<void> {
    // Phase 1: no-op for everything except speech (which never reaches
    // here).  We log at debug so devs can see action flow during
    // probe-page testing, but we do not warn — the no-op resolution is
    // intentional, not an error.
    if (typeof console !== 'undefined' && console.debug) {
      console.debug('[ActionEngine v2 stub]', action.type, action.id);
    }
    return Promise.resolve();
  }

  /**
   * Clear any active fire-and-forget visual effects.  Called on stop()
   * and on scene boundaries by the playback engine.  Phase 1 stub —
   * Stage component (MAIC-403) tracks effects in its own state.
   */
  clearEffects(): void {
    // Phase 1: no-op.  Stage holds effect state and clears it directly.
  }
}
