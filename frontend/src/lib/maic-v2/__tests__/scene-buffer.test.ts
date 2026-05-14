/**
 * Tests for src/lib/maic-v2/scene-buffer.ts (MAIC-403.1).
 *
 * Pure-function reducer tests — no React, no DOM, no async.
 */
import { describe, test, expect } from 'vitest';

import {
  EMPTY_SCENE_BUFFER,
  applyEvent,
  reduceEvents,
} from '../scene-buffer';
import type { MaicEvent } from '../../../hooks/useMaicClassroomChannelV2';


// ── Helpers ──────────────────────────────────────────────────────


function thinking(stage = 'agent_loading', agentId?: string): MaicEvent {
  return {
    type: 'thinking',
    data: agentId ? { stage, agentId } : { stage },
  };
}

function agentStart(
  messageId = 'm1',
  agentId = 'default-1',
  agentName = 'AI teacher',
  agentColor = '#3b82f6',
): MaicEvent {
  return {
    type: 'agent_start',
    data: { messageId, agentId, agentName, agentAvatar: null, agentColor },
  };
}

function textDelta(content: string, messageId = 'm1'): MaicEvent {
  return { type: 'text_delta', data: { content, messageId } };
}

function actionEvent(
  actionId: string,
  actionName: string,
  params: Record<string, unknown> = {},
  agentId = 'default-1',
  messageId = 'm1',
): MaicEvent {
  return {
    type: 'action',
    data: { actionId, actionName, params, agentId, messageId },
  };
}

function speechAudio(
  audioId: string,
  audioB64: string,
  agentId = 'default-1',
  messageId = 'm1',
): MaicEvent {
  return {
    type: 'speech_audio',
    data: {
      audioId,
      format: 'mp3',
      // The wire format ships base64 — we accept both `audioB64` and
      // upstream's older `base64` field name for forward-compat tests.
      base64: audioB64,
    },
  };
}

function agentEnd(messageId = 'm1', agentId = 'default-1'): MaicEvent {
  return { type: 'agent_end', data: { messageId, agentId } };
}

function cueUser(fromAgentId = 'default-1'): MaicEvent {
  return { type: 'cue_user', data: { fromAgentId } };
}

function errorFrame(message: string): MaicEvent {
  return { type: 'error', data: { message } };
}


// ── EMPTY_SCENE_BUFFER ────────────────────────────────────────────


describe('EMPTY_SCENE_BUFFER', () => {
  test('starts at status=idle with empty containers', () => {
    expect(EMPTY_SCENE_BUFFER.status).toBe('idle');
    expect(EMPTY_SCENE_BUFFER.currentAgent).toBeNull();
    expect(EMPTY_SCENE_BUFFER.agentsByMessageId).toEqual({});
    expect(EMPTY_SCENE_BUFFER.textByMessageId).toEqual({});
    expect(EMPTY_SCENE_BUFFER.messageOrder).toEqual([]);
    expect(EMPTY_SCENE_BUFFER.actions).toEqual([]);
    expect(EMPTY_SCENE_BUFFER.audioByMessageId).toEqual({});
    expect(EMPTY_SCENE_BUFFER.cueingUser).toBe(false);
    expect(EMPTY_SCENE_BUFFER.lastError).toBeNull();
    expect(EMPTY_SCENE_BUFFER.thinkingStage).toBeNull();
  });
});


// ── applyEvent — purity ───────────────────────────────────────────


describe('applyEvent purity', () => {
  test('does not mutate input buffer', () => {
    const before = { ...EMPTY_SCENE_BUFFER };
    applyEvent(EMPTY_SCENE_BUFFER, thinking());
    expect(EMPTY_SCENE_BUFFER).toEqual(before);
  });

  test('returns a new object reference (no shared mutation)', () => {
    const next = applyEvent(EMPTY_SCENE_BUFFER, thinking());
    expect(next).not.toBe(EMPTY_SCENE_BUFFER);
  });
});


// ── thinking → status & stage ─────────────────────────────────────


describe('applyEvent thinking', () => {
  test('sets status=thinking and captures stage', () => {
    const next = applyEvent(EMPTY_SCENE_BUFFER, thinking('agent_loading'));
    expect(next.status).toBe('thinking');
    expect(next.thinkingStage).toBe('agent_loading');
  });

  test('overwrites earlier thinking stage', () => {
    let buf = applyEvent(EMPTY_SCENE_BUFFER, thinking('agent_loading'));
    buf = applyEvent(buf, thinking('director'));
    expect(buf.thinkingStage).toBe('director');
  });
});


// ── agent_start → currentAgent ────────────────────────────────────


describe('applyEvent agent_start', () => {
  test('captures full agent metadata', () => {
    const next = applyEvent(
      EMPTY_SCENE_BUFFER,
      agentStart('m-1', 'default-1', 'AI teacher', '#3b82f6'),
    );
    expect(next.currentAgent).toEqual({
      messageId: 'm-1',
      agentId: 'default-1',
      agentName: 'AI teacher',
      agentAvatar: null,
      agentColor: '#3b82f6',
    });
    expect(next.agentsByMessageId['m-1']).toEqual(next.currentAgent);
    expect(next.messageOrder).toEqual(['m-1']);
    expect(next.status).toBe('streaming');
  });

  test('clears thinkingStage', () => {
    let buf = applyEvent(EMPTY_SCENE_BUFFER, thinking('agent_loading'));
    buf = applyEvent(buf, agentStart());
    expect(buf.thinkingStage).toBeNull();
  });

  test('initializes textByMessageId bucket for the new messageId', () => {
    const next = applyEvent(EMPTY_SCENE_BUFFER, agentStart('m-7'));
    expect(next.textByMessageId['m-7']).toBe('');
  });

  test('does NOT clobber an existing text buffer for the same messageId', () => {
    // Phase 3 multi-agent: out-of-order agent_start arrival shouldn't
    // wipe text already accumulated for that messageId.
    let buf = applyEvent(EMPTY_SCENE_BUFFER, textDelta('hello', 'm-7'));
    buf = applyEvent(buf, agentStart('m-7'));
    expect(buf.textByMessageId['m-7']).toBe('hello');
    expect(buf.messageOrder).toEqual(['m-7']);
  });

  test('does not duplicate messageOrder when agent_start follows early text', () => {
    let buf = applyEvent(EMPTY_SCENE_BUFFER, textDelta('early', 'm-7'));
    buf = applyEvent(buf, agentStart('m-7'));
    expect(buf.messageOrder).toEqual(['m-7']);
  });
});


// ── text_delta — accumulation ────────────────────────────────────


describe('applyEvent text_delta', () => {
  test('appends to the named messageId bucket', () => {
    let buf = applyEvent(EMPTY_SCENE_BUFFER, agentStart('m-1'));
    buf = applyEvent(buf, textDelta('Hello ', 'm-1'));
    buf = applyEvent(buf, textDelta('students.', 'm-1'));
    expect(buf.textByMessageId['m-1']).toBe('Hello students.');
  });

  test('different messageIds accumulate independently', () => {
    let buf = applyEvent(EMPTY_SCENE_BUFFER, textDelta('A', 'm-1'));
    buf = applyEvent(buf, textDelta('B', 'm-2'));
    buf = applyEvent(buf, textDelta('C', 'm-1'));
    expect(buf.textByMessageId['m-1']).toBe('AC');
    expect(buf.textByMessageId['m-2']).toBe('B');
  });

  test('handles delta arriving BEFORE agent_start (forward-compat)', () => {
    // Phase 3 may have multi-agent races where text arrives before
    // agent_start is processed.  Buffer must tolerate this.
    const buf = applyEvent(EMPTY_SCENE_BUFFER, textDelta('hi', 'm-?'));
    expect(buf.textByMessageId['m-?']).toBe('hi');
    expect(buf.messageOrder).toEqual(['m-?']);
  });
});


// ── action — append in arrival order ─────────────────────────────


describe('applyEvent action', () => {
  test('appends action with reconstituted Action shape', () => {
    const buf = applyEvent(
      EMPTY_SCENE_BUFFER,
      actionEvent('a-1', 'wb_open', {}),
    );
    expect(buf.actions).toHaveLength(1);
    expect(buf.actions[0]).toEqual({ id: 'a-1', type: 'wb_open' });
  });

  test('preserves params spread into the action shape', () => {
    const buf = applyEvent(
      EMPTY_SCENE_BUFFER,
      actionEvent('a-2', 'spotlight', { elementId: 'el-7', dimOpacity: 0.4 }),
    );
    expect(buf.actions[0]).toEqual({
      id: 'a-2',
      type: 'spotlight',
      elementId: 'el-7',
      dimOpacity: 0.4,
    });
  });

  test('preserves arrival order across multiple actions', () => {
    let buf = EMPTY_SCENE_BUFFER;
    buf = applyEvent(buf, actionEvent('a', 'wb_open'));
    buf = applyEvent(buf, actionEvent('b', 'spotlight', { elementId: 'el' }));
    buf = applyEvent(buf, actionEvent('c', 'wb_close'));
    expect(buf.actions.map((a) => a.id)).toEqual(['a', 'b', 'c']);
  });
});


// ── speech_audio — indexed by messageId ──────────────────────────


describe('applyEvent speech_audio', () => {
  test('stores audio under the messageId from the event payload', () => {
    // Use a custom event with messageId in data
    const event: MaicEvent = {
      type: 'speech_audio',
      data: {
        audioId: 'aud-1',
        audioB64: 'AAA=',
        format: 'mp3',
        messageId: 'm-1',
        agentId: 'default-1',
      },
    };
    const buf = applyEvent(EMPTY_SCENE_BUFFER, event);
    expect(buf.audioByMessageId['m-1']).toEqual({
      audioId: 'aud-1',
      audioB64: 'AAA=',
      format: 'mp3',
      messageId: 'm-1',
      agentId: 'default-1',
    });
    expect(buf.messageOrder).toEqual(['m-1']);
  });

  test('ignores frames missing audioId', () => {
    const event: MaicEvent = {
      type: 'speech_audio',
      data: { audioId: '', format: 'mp3', messageId: 'm-1' },
    };
    const buf = applyEvent(EMPTY_SCENE_BUFFER, event);
    expect(buf.audioByMessageId).toEqual({});
  });

  test('accepts upstream-style `base64` field name as fallback', () => {
    const event: MaicEvent = {
      type: 'speech_audio',
      data: {
        audioId: 'aud-2',
        base64: 'BBB=',
        format: 'mp3',
        messageId: 'm-2',
      },
    };
    const buf = applyEvent(EMPTY_SCENE_BUFFER, event);
    expect(buf.audioByMessageId['m-2'].audioB64).toBe('BBB=');
  });

  test('stores URL-backed speech audio frames', () => {
    const event: MaicEvent = {
      type: 'speech_audio',
      data: {
        audioId: 'aud-url',
        url: 'https://cdn.example.test/audio.mp3',
        format: 'mp3',
        messageId: 'm-url',
        agentId: 'default-1',
      },
    };
    const buf = applyEvent(EMPTY_SCENE_BUFFER, event);
    expect(buf.audioByMessageId['m-url'].audioUrl).toBe(
      'https://cdn.example.test/audio.mp3',
    );
  });

  test('falls back to currentAgent metadata when speech frame omits ids', () => {
    let buf = applyEvent(EMPTY_SCENE_BUFFER, agentStart('m-current', 'agent-1'));
    buf = applyEvent(buf, {
      type: 'speech_audio',
      data: { audioId: 'aud-current', audioB64: 'AAA=', format: 'mp3' },
    });
    expect(buf.audioByMessageId['m-current']).toMatchObject({
      audioId: 'aud-current',
      messageId: 'm-current',
      agentId: 'agent-1',
    });
  });
});


// ── agent_end → completed ─────────────────────────────────────────


describe('applyEvent agent_end', () => {
  test('flips status to completed', () => {
    let buf = applyEvent(EMPTY_SCENE_BUFFER, agentStart());
    buf = applyEvent(buf, agentEnd());
    expect(buf.status).toBe('completed');
  });
});


// ── cue_user → cueingUser flag ───────────────────────────────────


describe('applyEvent cue_user', () => {
  test('sets cueingUser true', () => {
    const buf = applyEvent(EMPTY_SCENE_BUFFER, cueUser());
    expect(buf.cueingUser).toBe(true);
  });

  test('does NOT change status (agent turn stays "completed")', () => {
    let buf = applyEvent(EMPTY_SCENE_BUFFER, agentStart());
    buf = applyEvent(buf, agentEnd());
    buf = applyEvent(buf, cueUser());
    expect(buf.status).toBe('completed');
    expect(buf.cueingUser).toBe(true);
  });
});


// ── error → status=error, lastError populated ───────────────────


describe('applyEvent error', () => {
  test('sets status=error and stores message', () => {
    const buf = applyEvent(EMPTY_SCENE_BUFFER, errorFrame('LLM timeout'));
    expect(buf.status).toBe('error');
    expect(buf.lastError).toBe('LLM timeout');
  });
});


// ── unknown event type — forward-compat ──────────────────────────


describe('applyEvent unknown type', () => {
  test('returns buffer unchanged', () => {
    // Cast to MaicEvent for the test (TS would normally reject this)
    const unknown = { type: 'future_type', data: { foo: 1 } } as unknown as MaicEvent;
    const buf = applyEvent(EMPTY_SCENE_BUFFER, unknown);
    expect(buf).toBe(EMPTY_SCENE_BUFFER);
  });
});


// ── reduceEvents — full Phase 1 wire stream ──────────────────────


describe('reduceEvents — end-to-end', () => {
  test('reproduces the Phase 1 backend live-smoke output', () => {
    // The exact 7-event sequence from the MAIC-301 cert smoke
    const events: MaicEvent[] = [
      thinking('agent_loading'),
      agentStart('m-1', 'default-1', 'AI teacher', '#3b82f6'),
      textDelta('Hello students. ', 'm-1'),
      textDelta('Today we will learn.', 'm-1'),
      actionEvent('a-1', 'wb_open', {}),
      {
        type: 'speech_audio',
        data: {
          audioId: 'speech-aaa',
          audioB64: 'AAA=',
          format: 'mp3',
          messageId: 'm-1',
          agentId: 'default-1',
        },
      },
      agentEnd('m-1'),
    ];
    const buf = reduceEvents(events);

    expect(buf.status).toBe('completed');
    expect(buf.currentAgent?.agentName).toBe('AI teacher');
    expect(buf.textByMessageId['m-1']).toBe('Hello students. Today we will learn.');
    expect(buf.messageOrder).toEqual(['m-1']);
    expect(buf.actions).toHaveLength(1);
    expect(buf.actions[0].type).toBe('wb_open');
    expect(buf.audioByMessageId['m-1'].audioId).toBe('speech-aaa');
    expect(buf.cueingUser).toBe(false);
    expect(buf.lastError).toBeNull();
  });

  test('multi-turn cue_user appears after completed', () => {
    const events: MaicEvent[] = [
      thinking('agent_loading'),
      agentStart('m-1'),
      textDelta('hi', 'm-1'),
      agentEnd('m-1'),
      cueUser('default-1'),
    ];
    const buf = reduceEvents(events);
    expect(buf.status).toBe('completed');
    expect(buf.cueingUser).toBe(true);
  });

  test('keeps all agent turns in arrival order', () => {
    const events: MaicEvent[] = [
      agentStart('m-1', 'teacher', 'Teacher', '#2563eb'),
      textDelta('First turn.', 'm-1'),
      agentEnd('m-1', 'teacher'),
      agentStart('m-2', 'coach', 'Coach', '#16a34a'),
      textDelta('Second turn.', 'm-2'),
      agentEnd('m-2', 'coach'),
    ];
    const buf = reduceEvents(events);
    expect(buf.messageOrder).toEqual(['m-1', 'm-2']);
    expect(buf.textByMessageId).toMatchObject({
      'm-1': 'First turn.',
      'm-2': 'Second turn.',
    });
    expect(buf.agentsByMessageId['m-1'].agentName).toBe('Teacher');
    expect(buf.agentsByMessageId['m-2'].agentName).toBe('Coach');
  });

  test('error mid-stream surfaces in lastError', () => {
    const events: MaicEvent[] = [
      thinking('agent_loading'),
      agentStart('m-1'),
      errorFrame('LLM crashed'),
    ];
    const buf = reduceEvents(events);
    expect(buf.status).toBe('error');
    expect(buf.lastError).toBe('LLM crashed');
  });

  test('empty events → unchanged EMPTY buffer', () => {
    expect(reduceEvents([])).toEqual(EMPTY_SCENE_BUFFER);
  });
});
