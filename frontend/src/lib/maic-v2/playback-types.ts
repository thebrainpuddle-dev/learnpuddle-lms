/**
 * Playback Types — types for the AI Classroom playback engine.
 *
 * Direct port of upstream `lib/playback/types.ts` (62 lines) +
 * `lib/utils/playback-storage.ts` PlaybackSnapshot interface.
 *
 * Source:
 *   https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/playback/types.ts
 *   https://github.com/THU-MAIC/OpenMAIC/blob/main/lib/utils/playback-storage.ts
 *   /Volumes/CrucialX9/OpenMAIC/lib/playback/types.ts (commit 10b1fc83)
 *
 * Used by:
 *   - frontend/src/lib/maic-v2/playback-engine.ts (MAIC-401.3)
 *   - frontend/src/lib/maic-v2/action-engine.ts   (MAIC-401.2)
 *   - frontend/src/components/maic-v2/Stage.tsx   (MAIC-403)
 *
 * Pure data file — no logic, no React, no DOM. Tests for shape
 * conformance live in __tests__/playback-types.test.ts.
 */

// ── PlaybackSnapshot — persisted progress for resumption across reloads ──


/**
 * Snapshot of where playback is in the current scene's action list.
 *
 * Persisted per session so the user can reload and resume. The
 * `sceneId` field guards against scene-content edits — if the
 * persisted snapshot was for a now-different scene, restore must
 * discard it rather than seeking into stale indices.
 */
export interface PlaybackSnapshot {
  sceneIndex: number;
  actionIndex: number;
  consumedDiscussions: string[];
  /** Scene this snapshot belongs to; restore discards on mismatch. */
  sceneId?: string;
}


// ── Visual effects — fired through onEffectFire callback ────────────


/**
 * Fire-and-forget visual effects (spotlight, laser pointer).
 * Matches the protocol's FIRE_AND_FORGET_ACTIONS subset (see
 * apps/maic/protocol/actions.py).
 */
export type Effect =
  | { kind: 'spotlight'; targetId: string; dimOpacity?: number }
  | { kind: 'laser'; targetId: string; color?: string };


// ── State-machine modes ─────────────────────────────────────────────


/**
 * Engine mode — top-level state of the playback FSM.
 *
 *   idle      — not playing; ready to start or paused indefinitely.
 *   playing   — autonomous playback through the scene's actions.
 *   paused    — playback halted mid-action; resume() picks up where
 *               we left off (audio resumed, timers rescheduled with
 *               remaining time).
 *   live      — user has interrupted or joined a discussion; agent
 *               responses stream in real-time and the UI takes input.
 */
export type EngineMode = 'idle' | 'playing' | 'paused' | 'live';


/**
 * Discussion topic state — tracked separately from EngineMode because
 * a discussion can outlive a single playing↔live transition.
 *
 *   active   — discussion currently happening; user can interrupt.
 *   pending  — discussion was paused mid-stream; resume() re-enters
 *              live mode for the same topic.
 *   closed   — discussion ended naturally or via handleEndDiscussion.
 */
export type TopicState = 'active' | 'pending' | 'closed';


// ── Trigger — proactive discussion card ─────────────────────────────


/**
 * The data a `discussion` action emits to drive the ProactiveCard UI.
 * Mirror of the wire-format `DiscussionAction` payload — see
 * apps/maic/protocol/actions.py DiscussionAction.
 */
export interface TriggerEvent {
  id: string;
  question: string;
  prompt?: string;
  agentId?: string;
}


// ── Callbacks — the engine's outward interface ──────────────────────


/**
 * Callbacks the embedding component (Stage, MAIC-403) installs on the
 * playback engine. All callbacks are optional; the engine never throws
 * if a callback is unset.
 *
 * Naming convention mirrors upstream: on<Event> for one-shot events,
 * is<Predicate> for synchronous queries.
 */
export interface PlaybackEngineCallbacks {
  // ── State machine ──
  onModeChange?: (mode: EngineMode) => void;

  // ── Scene + speaker lifecycle ──
  onSceneChange?: (sceneId: string) => void;
  onSpeakerChange?: (role: string) => void;

  // ── Speech (per `speech` action) ──
  /** Fired when a speech action starts; `text` is the content. */
  onSpeechStart?: (text: string) => void;
  /** Fired when audio (or browser TTS) completes for the current speech. */
  onSpeechEnd?: () => void;
  /**
   * Fired for `text_delta` events streamed from the WS — used for
   * progressive rendering separate from speech (text may stream
   * faster than audio synthesizes).
   */
  onTextDelta?: (content: string) => void;

  // ── Visual effects (spotlight, laser) ──
  onEffectFire?: (effect: Effect) => void;

  // ── Proactive discussion card ──
  onProactiveShow?: (trigger: TriggerEvent) => void;
  onProactiveHide?: () => void;

  // ── Discussion lifecycle ──
  onDiscussionConfirmed?: (topic: string, prompt?: string, agentId?: string) => void;
  onDiscussionEnd?: () => void;
  onUserInterrupt?: (text: string) => void;
  /**
   * Fired when the user types and sends a message during `live` mode
   * (MAIC-410.2). Stage forwards the text to the WS via
   * `send({action:'user_message', data:{text}})`. Distinct from
   * `onUserInterrupt`: interrupt enters live mode mid-lecture; this
   * fires for every subsequent message inside live mode.
   */
  onLiveUserMessage?: (text: string) => void;

  // ── Topic / transcript (for cross-classroom history view) ──
  onTopicStart?: (type: 'lecture' | 'discussion', title: string) => void;
  onTopicAppend?: (role: string, text: string) => void;
  onTopicEnd?: () => void;

  // ── Persistence ──
  /** Fire on every action consumed so the host can persist progress. */
  onProgress?: (snapshot: PlaybackSnapshot) => void;

  // ── Synchronous queries ──
  /** Used to skip a `discussion` action whose target agent isn't selected. */
  isAgentSelected?: (agentId: string) => boolean;
  /** Playback speed multiplier (1.0, 1.5, 2.0). Used for reading-time
   *  estimation when no audio is available. */
  getPlaybackSpeed?: () => number;

  // ── Terminal ──
  onComplete?: () => void;
}
