/**
 * Scene Buffer — pure event-stream → buffered-state accumulator.
 *
 * Used by:
 *   - frontend/src/components/maic-v2/Stage.tsx (MAIC-403.7)
 *
 * This is a PURE-FUNCTION reducer: takes a sequence of MaicEvent and
 * produces the latest buffered state. No React, no DOM, no side
 * effects. The Stage component wraps this in a useMemo over the
 * useMaicClassroomChannelV2 hook's events[] array.
 *
 * Why a separate module?  Buffer correctness is the most error-prone
 * part of the streaming → playback handoff. Keeping the reducer
 * pure-functional + testable in isolation catches edge cases (event
 * arriving out of order, agent_end before audio, multiple agent_start
 * for one turn, etc.) without coupling to React rendering.
 */
import type { Action } from './action-types';
import type { MaicEvent } from '../../hooks/useMaicClassroomChannelV2';


// ── Public types ──────────────────────────────────────────────────


/**
 * Snapshot of an agent that has spoken (or is speaking) in the current
 * stream.  Captured from `agent_start` events and used to render the
 * agent overlay (avatar, name, color).
 */
export interface AgentSnapshot {
  agentId: string;
  agentName: string;
  agentAvatar: string | null;
  agentColor: string;
  /** messageId from the agent_start event — primary key for this turn. */
  messageId: string;
}


/**
 * Audio payload received in a speech_audio frame, ready for playback.
 * `dataUrl` is constructed lazily by the consumer (Stage) from the
 * raw `audioB64` so the buffer stays cheap to recompute on each
 * event-array prefix.
 */
export interface BufferedAudio {
  audioId: string;
  audioB64: string;
  format: string;
  /** messageId of the agent_start this audio belongs to. */
  messageId: string;
  /** agentId that emitted the audio. */
  agentId: string;
}


/**
 * Top-level status of the currently-streaming agent turn.  Maps to UI
 * affordances (loading shimmer, "AI is thinking", etc.).
 *
 *   idle      — no events received yet (initial mount)
 *   thinking  — director emitted `thinking` but no agent_start yet
 *   streaming — agent_start received, text deltas + actions arriving
 *   completed — agent_end received; turn fully buffered
 *   error     — error frame received; lastError populated
 *
 * `cue_user` arrival is reflected in `cueingUser=true` rather than a
 * status change so the agent's prior turn can stay visible.
 */
export type SceneBufferStatus =
  | 'idle'
  | 'thinking'
  | 'streaming'
  | 'completed'
  | 'error';


/**
 * Buffered state derived from a prefix of the MaicEvent stream.
 * The Stage component re-renders when this changes.
 */
export interface SceneBuffer {
  status: SceneBufferStatus;

  /** Latest dispatched agent — last `agent_start` wins. */
  currentAgent: AgentSnapshot | null;

  /**
   * Concatenated text deltas, keyed by messageId.  In Phase 1 there's
   * exactly one messageId per agent turn so this is effectively a
   * single string per turn; the dict shape is forward-compat for
   * Phase 3 multi-agent where each agent has its own messageId.
   */
  textByMessageId: Record<string, string>;

  /**
   * Action events received, in original arrival order.  Used by the
   * scene-builder helper to assemble a synthetic Scene for the
   * PlaybackEngine.
   */
  actions: Action[];

  /**
   * Audio payloads received, indexed by messageId.  Phase 1 ships one
   * speech_audio per agent turn, so this is at most one entry per
   * messageId.
   */
  audioByMessageId: Record<string, BufferedAudio>;

  /**
   * `true` after a `cue_user` event — the engine is waiting for the
   * user to respond.  Stage uses this to enable an input box.
   */
  cueingUser: boolean;

  /** Latest error frame, if any.  null when status !== 'error'. */
  lastError: string | null;

  /**
   * Stage of the latest `thinking` event (e.g. 'agent_loading',
   * 'director', 'ending').  Used for thin-loader UI when status ===
   * 'thinking'.  Phase 1 only emits 'agent_loading' and 'ending'.
   */
  thinkingStage: string | null;
}


/**
 * Empty initial buffer — what the Stage uses on mount before any
 * events have arrived.
 */
export const EMPTY_SCENE_BUFFER: SceneBuffer = {
  status: 'idle',
  currentAgent: null,
  textByMessageId: {},
  actions: [],
  audioByMessageId: {},
  cueingUser: false,
  lastError: null,
  thinkingStage: null,
};


// ── Reducer ──────────────────────────────────────────────────────


/**
 * Apply one event to the buffer; return the new buffer.  Pure: never
 * mutates the input.  Unknown event types are forward-compat: ignored
 * with no state change.
 */
export function applyEvent(buffer: SceneBuffer, event: MaicEvent): SceneBuffer {
  switch (event.type) {
    case 'thinking':
      return {
        ...buffer,
        status: 'thinking',
        thinkingStage: event.data.stage,
      };

    case 'agent_start': {
      const snap: AgentSnapshot = {
        agentId: event.data.agentId,
        agentName: event.data.agentName,
        agentAvatar: event.data.agentAvatar,
        agentColor: event.data.agentColor,
        messageId: event.data.messageId,
      };
      return {
        ...buffer,
        status: 'streaming',
        currentAgent: snap,
        // Initialize an empty text bucket for this messageId so callers
        // can do textByMessageId[messageId] without an undefined check.
        textByMessageId: {
          ...buffer.textByMessageId,
          [snap.messageId]: buffer.textByMessageId[snap.messageId] ?? '',
        },
        thinkingStage: null,
      };
    }

    case 'text_delta': {
      const { messageId, content } = event.data;
      const prior = buffer.textByMessageId[messageId] ?? '';
      return {
        ...buffer,
        textByMessageId: {
          ...buffer.textByMessageId,
          [messageId]: prior + content,
        },
      };
    }

    case 'action': {
      const { actionId, actionName, params } = event.data;
      // Reconstitute the Action shape the PlaybackEngine expects from
      // the wire-format `{actionId, actionName, params}` shape.
      const action = {
        id: actionId,
        type: actionName,
        ...params,
      } as Action;
      return {
        ...buffer,
        actions: [...buffer.actions, action],
      };
    }

    case 'speech_audio': {
      // The wire format upstream uses `audioB64`/`format`; the event
      // type also tolerates an `audioUrl` field for forward-compat
      // with Phase 5 cloud TTS providers that may serve URLs instead.
      // We default audioB64 to '' so missing audio still produces a
      // bookkeeping entry for the messageId.
      const data = event.data as Record<string, unknown>;
      const audioId = String(data.audioId ?? '');
      const audioB64 = String(data.audioB64 ?? data.base64 ?? '');
      const format = String(data.format ?? 'mp3');
      const messageId = String((data.messageId ?? '') || '');
      const agentId = String((data.agentId ?? '') || '');
      if (!audioId) return buffer;  // malformed, ignore
      return {
        ...buffer,
        audioByMessageId: {
          ...buffer.audioByMessageId,
          [messageId]: { audioId, audioB64, format, messageId, agentId },
        },
      };
    }

    case 'agent_end':
      return {
        ...buffer,
        status: 'completed',
      };

    case 'cue_user':
      return {
        ...buffer,
        cueingUser: true,
      };

    case 'error':
      return {
        ...buffer,
        status: 'error',
        lastError: event.data.message,
      };

    default:
      return buffer;  // forward-compat: ignore unknown event types
  }
}


/**
 * Reduce an entire MaicEvent[] (e.g. the prefix from
 * useMaicClassroomChannelV2's `events`) into a single SceneBuffer.
 * Pure; safe to call inside useMemo.
 */
export function reduceEvents(events: MaicEvent[]): SceneBuffer {
  let buffer = EMPTY_SCENE_BUFFER;
  for (const ev of events) {
    buffer = applyEvent(buffer, ev);
  }
  return buffer;
}
