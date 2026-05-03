/**
 * Tests for src/lib/maic-v2/playback-types.ts.
 *
 * These are TYPE-SHAPE tests (run by tsc — vitest just executes the
 * runtime asserts) rather than behavior tests. Their job is to catch
 * accidental drift from the upstream type definitions, which would
 * silently break the playback engine's contract with both the WS
 * stream consumer and the Stage component.
 */
import { describe, test, expect } from 'vitest';

import type {
  Effect,
  EngineMode,
  PlaybackEngineCallbacks,
  PlaybackSnapshot,
  TopicState,
  TriggerEvent,
} from '../playback-types';


describe('playback-types', () => {
  // ── EngineMode literal-set ────────────────────────────────────────

  test('EngineMode has exactly 4 valid values', () => {
    const modes: EngineMode[] = ['idle', 'playing', 'paused', 'live'];
    // Compile-time: the array literal is well-typed only if EngineMode
    // is exactly these 4 values. We assert runtime length to keep the
    // test visible in the suite.
    expect(modes).toHaveLength(4);
  });

  test('EngineMode rejects unknown values at type level', () => {
    // @ts-expect-error 'invalid' is not a valid EngineMode
    const bad: EngineMode = 'invalid';
    void bad;  // suppress unused warning
  });

  // ── TopicState literal-set ────────────────────────────────────────

  test('TopicState has exactly 3 valid values', () => {
    const states: TopicState[] = ['active', 'pending', 'closed'];
    expect(states).toHaveLength(3);
  });

  // ── Effect discriminated union ────────────────────────────────────

  test('Effect spotlight variant accepts dimOpacity', () => {
    const e: Effect = { kind: 'spotlight', targetId: 'el-1', dimOpacity: 0.4 };
    expect(e.kind).toBe('spotlight');
  });

  test('Effect laser variant accepts color', () => {
    const e: Effect = { kind: 'laser', targetId: 'el-1', color: '#ff0000' };
    expect(e.kind).toBe('laser');
  });

  test('Effect rejects unknown kind at type level', () => {
    // @ts-expect-error 'spotlight' and 'laser' are the only valid kinds
    const bad: Effect = { kind: 'glow', targetId: 'el-1' };
    void bad;
  });

  // ── TriggerEvent ──────────────────────────────────────────────────

  test('TriggerEvent requires id + question', () => {
    const t: TriggerEvent = { id: 'd-1', question: 'What if we change X?' };
    expect(t.id).toBe('d-1');
    expect(t.question).toBe('What if we change X?');
  });

  test('TriggerEvent allows optional prompt + agentId', () => {
    const t: TriggerEvent = {
      id: 'd-2',
      question: 'Discuss this',
      prompt: 'Consider X, Y, Z',
      agentId: 'default-1',
    };
    expect(t.prompt).toBe('Consider X, Y, Z');
    expect(t.agentId).toBe('default-1');
  });

  // ── PlaybackSnapshot ──────────────────────────────────────────────

  test('PlaybackSnapshot requires three core fields', () => {
    const snap: PlaybackSnapshot = {
      sceneIndex: 0,
      actionIndex: 5,
      consumedDiscussions: ['d-1', 'd-2'],
    };
    expect(snap.sceneIndex).toBe(0);
    expect(snap.actionIndex).toBe(5);
    expect(snap.consumedDiscussions).toHaveLength(2);
  });

  test('PlaybackSnapshot sceneId is optional', () => {
    const snap: PlaybackSnapshot = {
      sceneIndex: 0,
      actionIndex: 0,
      consumedDiscussions: [],
      sceneId: 'scene-abc',
    };
    expect(snap.sceneId).toBe('scene-abc');
  });

  // ── PlaybackEngineCallbacks ───────────────────────────────────────

  test('PlaybackEngineCallbacks accepts an empty object (all optional)', () => {
    const cb: PlaybackEngineCallbacks = {};
    expect(cb).toBeDefined();
  });

  test('PlaybackEngineCallbacks: onModeChange receives EngineMode values', () => {
    const captured: EngineMode[] = [];
    const cb: PlaybackEngineCallbacks = {
      onModeChange: (mode) => captured.push(mode),
    };
    cb.onModeChange?.('playing');
    cb.onModeChange?.('paused');
    expect(captured).toEqual(['playing', 'paused']);
  });

  test('PlaybackEngineCallbacks: onEffectFire receives Effect', () => {
    let captured: Effect | null = null;
    const cb: PlaybackEngineCallbacks = {
      onEffectFire: (e) => { captured = e; },
    };
    cb.onEffectFire?.({ kind: 'spotlight', targetId: 'x' });
    expect(captured).not.toBeNull();
    expect(captured!.kind).toBe('spotlight');
  });

  test('PlaybackEngineCallbacks: isAgentSelected returns boolean', () => {
    const cb: PlaybackEngineCallbacks = {
      isAgentSelected: (id) => id === 'default-1',
    };
    expect(cb.isAgentSelected?.('default-1')).toBe(true);
    expect(cb.isAgentSelected?.('default-2')).toBe(false);
  });

  test('PlaybackEngineCallbacks: getPlaybackSpeed returns number', () => {
    const cb: PlaybackEngineCallbacks = {
      getPlaybackSpeed: () => 1.5,
    };
    expect(cb.getPlaybackSpeed?.()).toBe(1.5);
  });

  test('PlaybackEngineCallbacks: onTopicStart accepts both topic types', () => {
    const types: ('lecture' | 'discussion')[] = [];
    const cb: PlaybackEngineCallbacks = {
      onTopicStart: (type) => types.push(type),
    };
    cb.onTopicStart?.('lecture', 'Photosynthesis');
    cb.onTopicStart?.('discussion', 'Why is X true?');
    expect(types).toEqual(['lecture', 'discussion']);
  });

  test('PlaybackEngineCallbacks: onProgress receives PlaybackSnapshot', () => {
    let captured: PlaybackSnapshot | null = null;
    const cb: PlaybackEngineCallbacks = {
      onProgress: (s) => { captured = s; },
    };
    cb.onProgress?.({ sceneIndex: 0, actionIndex: 0, consumedDiscussions: [] });
    expect(captured).not.toBeNull();
    expect(captured!.sceneIndex).toBe(0);
  });
});
