/**
 * Scene Builder — pure helper that converts a SceneBuffer into a
 * Scene object the PlaybackEngine can consume.
 *
 * Used by:
 *   - frontend/src/components/maic-v2/Stage.tsx (MAIC-403.7)
 *
 * Why a separate module?  The buffer captures wire-format events; the
 * engine consumes a Scene of Actions.  The bridge is the single
 * non-obvious bit of glue (synthetic SpeechAction generation,
 * messageId → text+audio matching) and is worth isolating + testing
 * apart from React rendering.
 *
 * Phase 1 ordering rule:
 *   Scene.actions = [
 *     ...buffer.actions,            // wb_*, widget_*, etc., in arrival order
 *     ...syntheticSpeechActions,    // one per messageId with audio
 *   ]
 *
 * This works because Phase 1 backend emits all wire-format `action`
 * events BEFORE the terminal `speech_audio` frame for a turn (see the
 * live-smoke recorded sequence in NEXT-SESSION-START.md).  Phase 3
 * multi-agent will revisit this ordering when multiple messageIds
 * interleave.
 */
import type { Action, SpeechAction } from './action-types';
import { dataUrlForBase64Mp3 } from './audio-player';
import type { SceneBuffer } from './scene-buffer';
import type { Scene } from './playback-engine';


/**
 * Build a Scene the engine can play from a buffered prefix of the
 * wire-format event stream.
 *
 * @param buffer    Reduced output of `reduceEvents(events)` (see
 *                  scene-buffer.ts).
 * @param sessionId Active classroom session id; used as the Scene id
 *                  when no agent has spoken yet (so the engine still
 *                  has a stable sceneId for snapshot/restore).
 *
 * The Scene.id is preferred from `buffer.currentAgent.messageId` so
 * each agent turn becomes its own Scene — `restoreFromSnapshot`
 * naturally discards stale snapshots when a new turn starts.  Falls
 * back to `sessionId` when no agent_start has arrived yet.
 *
 * Pure: never mutates the input buffer or its nested objects.
 */
export function buildSceneFromBuffer(
  buffer: SceneBuffer,
  sessionId: string,
): Scene {
  const sceneId = buffer.currentAgent?.messageId ?? sessionId;

  const speechActions: SpeechAction[] = [];
  const audioMessageIds = [
    ...buffer.messageOrder,
    ...Object.keys(buffer.audioByMessageId).filter(
      (messageId) => !buffer.messageOrder.includes(messageId),
    ),
  ];

  for (const messageId of audioMessageIds) {
    const audio = buffer.audioByMessageId[messageId];
    if (!audio) continue;
    // Skip bookkeeping entries that have no actual audio bytes — the
    // engine would otherwise schedule a reading-time timer for empty
    // text, producing a 2 s silent gap. URL-backed TTS frames are a
    // real audio source and should play.
    const audioUrl = audio.audioUrl ?? (
      audio.audioB64 ? dataUrlForBase64Mp3(audio.audioB64) : undefined
    );
    if (!audioUrl) continue;
    speechActions.push({
      id: `speech-${messageId}`,
      type: 'speech',
      text: buffer.textByMessageId[messageId] ?? '',
      audioId: audio.audioId,
      audioUrl,
    });
  }

  return {
    id: sceneId,
    actions: [...buffer.actions, ...speechActions],
  };
}
