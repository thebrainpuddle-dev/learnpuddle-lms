/**
 * Tests for src/lib/maic-v2/scene-builder.ts (MAIC-403.2).
 *
 * Pure-function helper tests — no React, no DOM, no async.
 */
import { describe, test, expect } from 'vitest';

import { buildSceneFromBuffer } from '../scene-builder';
import { EMPTY_SCENE_BUFFER, reduceEvents } from '../scene-buffer';
import type { SceneBuffer } from '../scene-buffer';
import type { MaicEvent } from '../../../hooks/useMaicClassroomChannelV2';
import type { SpeechAction, WbOpenAction } from '../action-types';


const SESSION_ID = 'sess-abc123';


// ── Helpers (full-shape MaicEvents — distinct from scene-buffer.test.ts
//             helpers, those omit messageId on speech_audio for forward-
//             compat coverage; here we want realistic Phase-1 wire shape) ─


function thinking(stage = 'agent_loading'): MaicEvent {
  return { type: 'thinking', data: { stage } };
}

function agentStart(messageId = 'm1', agentId = 'default-1'): MaicEvent {
  return {
    type: 'agent_start',
    data: {
      messageId,
      agentId,
      agentName: 'AI teacher',
      agentAvatar: null,
      agentColor: '#3b82f6',
    },
  };
}

function textDelta(content: string, messageId = 'm1'): MaicEvent {
  return { type: 'text_delta', data: { content, messageId } };
}

function actionEvent(
  actionId: string,
  actionName: string,
  params: Record<string, unknown> = {},
  messageId = 'm1',
): MaicEvent {
  return {
    type: 'action',
    data: { actionId, actionName, params, agentId: 'default-1', messageId },
  };
}

function speechAudio(
  audioId: string,
  audioB64: string,
  messageId = 'm1',
): MaicEvent {
  return {
    type: 'speech_audio',
    data: { audioId, audioB64, format: 'mp3', messageId, agentId: 'default-1' },
  };
}

function agentEnd(messageId = 'm1'): MaicEvent {
  return { type: 'agent_end', data: { messageId, agentId: 'default-1' } };
}


// ── Empty / pre-stream buffers ──────────────────────────────────────


describe('buildSceneFromBuffer — empty buffer', () => {
  test('uses sessionId as scene id when no agent has started', () => {
    const scene = buildSceneFromBuffer(EMPTY_SCENE_BUFFER, SESSION_ID);
    expect(scene.id).toBe(SESSION_ID);
    expect(scene.actions).toEqual([]);
  });

  test('does not mutate the input buffer', () => {
    const before = JSON.stringify(EMPTY_SCENE_BUFFER);
    buildSceneFromBuffer(EMPTY_SCENE_BUFFER, SESSION_ID);
    expect(JSON.stringify(EMPTY_SCENE_BUFFER)).toBe(before);
  });
});


// ── Scene id selection ──────────────────────────────────────────────


describe('buildSceneFromBuffer — scene id selection', () => {
  test('prefers currentAgent.messageId once agent_start has arrived', () => {
    const buffer = reduceEvents([thinking(), agentStart('msg-42')]);
    const scene = buildSceneFromBuffer(buffer, SESSION_ID);
    expect(scene.id).toBe('msg-42');
  });

  test('falls back to sessionId when only thinking has arrived', () => {
    const buffer = reduceEvents([thinking()]);
    const scene = buildSceneFromBuffer(buffer, SESSION_ID);
    expect(scene.id).toBe(SESSION_ID);
  });
});


// ── Action ordering (Phase 1 rule: arrival order, then synthetic speech) ──


describe('buildSceneFromBuffer — action assembly', () => {
  test('preserves wire-format actions in arrival order', () => {
    const buffer = reduceEvents([
      agentStart(),
      actionEvent('a-wb', 'wb_open'),
      actionEvent('a-laser', 'laser', { elementId: 'topic-1' }),
    ]);
    const scene = buildSceneFromBuffer(buffer, SESSION_ID);

    expect(scene.actions).toHaveLength(2);
    expect(scene.actions![0].type).toBe('wb_open');
    expect(scene.actions![0].id).toBe('a-wb');
    expect(scene.actions![1].type).toBe('laser');
    expect(scene.actions![1].id).toBe('a-laser');
  });

  test('appends one synthetic speech action per audio entry, AFTER actions', () => {
    const buffer = reduceEvents([
      agentStart('m1'),
      textDelta('Hello, students.', 'm1'),
      actionEvent('a-wb', 'wb_open'),
      speechAudio('aud-1', 'QUJDREVG', 'm1'),  // base64 'ABCDEF'
      agentEnd('m1'),
    ]);
    const scene = buildSceneFromBuffer(buffer, SESSION_ID);

    expect(scene.actions).toHaveLength(2);
    // wb_open first (arrival order), speech last
    expect(scene.actions![0].type).toBe('wb_open');
    const speech = scene.actions![1] as SpeechAction;
    expect(speech.type).toBe('speech');
    expect(speech.id).toBe('speech-m1');
    expect(speech.text).toBe('Hello, students.');
    expect(speech.audioId).toBe('aud-1');
    expect(speech.audioUrl).toBe('data:audio/mp3;base64,QUJDREVG');
  });

  test('builds an empty Scene from a buffer with only thinking', () => {
    const buffer = reduceEvents([thinking()]);
    const scene = buildSceneFromBuffer(buffer, SESSION_ID);
    expect(scene.actions).toEqual([]);
  });
});


// ── Synthetic SpeechAction generation ──────────────────────────────


describe('buildSceneFromBuffer — speech action synthesis', () => {
  test('skips audio entries with empty audioB64 and no audioUrl', () => {
    // Manually craft a buffer with a bookkeeping-only audio entry.
    const buffer: SceneBuffer = {
      ...EMPTY_SCENE_BUFFER,
      currentAgent: {
        agentId: 'default-1',
        agentName: 'AI teacher',
        agentAvatar: null,
        agentColor: '#3b82f6',
        messageId: 'm1',
      },
      textByMessageId: { m1: 'Hello.' },
      audioByMessageId: {
        m1: {
          audioId: 'aud-1',
          audioB64: '',     // no bytes
          format: 'mp3',
          messageId: 'm1',
          agentId: 'default-1',
        },
      },
    };
    const scene = buildSceneFromBuffer(buffer, SESSION_ID);
    expect(scene.actions).toEqual([]);
  });

  test('uses URL-backed speech audio when no inline base64 exists', () => {
    const buffer: SceneBuffer = {
      ...EMPTY_SCENE_BUFFER,
      textByMessageId: { m1: 'This audio came from storage.' },
      messageOrder: ['m1'],
      audioByMessageId: {
        m1: {
          audioId: 'aud-url',
          audioB64: '',
          audioUrl: 'https://cdn.example.test/audio.mp3',
          format: 'mp3',
          messageId: 'm1',
          agentId: 'default-1',
        },
      },
    };
    const scene = buildSceneFromBuffer(buffer, SESSION_ID);
    const speech = scene.actions![0] as SpeechAction;
    expect(speech.audioUrl).toBe('https://cdn.example.test/audio.mp3');
    expect(speech.text).toBe('This audio came from storage.');
  });

  test('uses empty string text when text bucket missing for the messageId', () => {
    // Buffer with audio but no text — the engine still needs a stable
    // SpeechAction (so audio plays); reading-time would only fire if
    // audioUrl were also missing, which it isn't here.
    const buffer: SceneBuffer = {
      ...EMPTY_SCENE_BUFFER,
      audioByMessageId: {
        m1: {
          audioId: 'aud-1',
          audioB64: 'QUJD',
          format: 'mp3',
          messageId: 'm1',
          agentId: 'default-1',
        },
      },
    };
    const scene = buildSceneFromBuffer(buffer, SESSION_ID);
    expect(scene.actions).toHaveLength(1);
    const speech = scene.actions![0] as SpeechAction;
    expect(speech.text).toBe('');
    expect(speech.audioUrl).toBe('data:audio/mp3;base64,QUJD');
  });

  test('emits one speech action per messageId (Phase 3 multi-agent forward-compat)', () => {
    // Two simultaneous agents — buffer can hold audio for each.
    const buffer: SceneBuffer = {
      ...EMPTY_SCENE_BUFFER,
      textByMessageId: { m1: 'Hi from teacher.', m2: 'Hi from helper.' },
      audioByMessageId: {
        m1: { audioId: 'aud-1', audioB64: 'AAA', format: 'mp3', messageId: 'm1', agentId: 'default-1' },
        m2: { audioId: 'aud-2', audioB64: 'BBB', format: 'mp3', messageId: 'm2', agentId: 'default-2' },
      },
    };
    const scene = buildSceneFromBuffer(buffer, SESSION_ID);
    expect(scene.actions).toHaveLength(2);
    const speech1 = scene.actions![0] as SpeechAction;
    const speech2 = scene.actions![1] as SpeechAction;
    expect([speech1.id, speech2.id].sort()).toEqual(['speech-m1', 'speech-m2']);
    const byId = Object.fromEntries(
      [speech1, speech2].map((a) => [a.id, a]),
    ) as Record<string, SpeechAction>;
    expect(byId['speech-m1'].text).toBe('Hi from teacher.');
    expect(byId['speech-m2'].text).toBe('Hi from helper.');
  });

  test('orders speech actions by messageOrder instead of audio object insertion', () => {
    const buffer: SceneBuffer = {
      ...EMPTY_SCENE_BUFFER,
      messageOrder: ['m1', 'm2'],
      textByMessageId: { m1: 'First speaker.', m2: 'Second speaker.' },
      audioByMessageId: {
        m2: { audioId: 'aud-2', audioB64: 'BBB', format: 'mp3', messageId: 'm2', agentId: 'helper' },
        m1: { audioId: 'aud-1', audioB64: 'AAA', format: 'mp3', messageId: 'm1', agentId: 'teacher' },
      },
    };
    const scene = buildSceneFromBuffer(buffer, SESSION_ID);
    expect(scene.actions!.map((action) => action.id)).toEqual([
      'speech-m1',
      'speech-m2',
    ]);
  });
});


// ── End-to-end: real Phase-1 backend smoke sequence ────────────────


describe('buildSceneFromBuffer — end-to-end Phase-1 smoke', () => {
  test('produces a Scene the engine can play from the live-smoke event sequence', () => {
    // Mirrors PHASE-1-BACKEND-CLOSURE / NEXT-SESSION-START.md:
    //   thinking → agent_start → text_delta → text_delta →
    //   action(wb_open) → speech_audio → agent_end
    const buffer = reduceEvents([
      thinking(),
      agentStart('m-smoke'),
      textDelta('Welcome, students. ', 'm-smoke'),
      textDelta('Today we will discuss fractions.', 'm-smoke'),
      actionEvent('a-wb', 'wb_open'),
      speechAudio('aud-smoke', 'SU1QTDM=', 'm-smoke'),  // base64 'IMPL3'
      agentEnd('m-smoke'),
    ]);
    const scene = buildSceneFromBuffer(buffer, SESSION_ID);

    expect(scene.id).toBe('m-smoke');
    expect(scene.actions).toHaveLength(2);

    const wb = scene.actions![0] as WbOpenAction;
    expect(wb.type).toBe('wb_open');
    expect(wb.id).toBe('a-wb');

    const speech = scene.actions![1] as SpeechAction;
    expect(speech.type).toBe('speech');
    expect(speech.text).toBe('Welcome, students. Today we will discuss fractions.');
    expect(speech.audioId).toBe('aud-smoke');
    expect(speech.audioUrl).toBe('data:audio/mp3;base64,SU1QTDM=');
  });
});
