/**
 * Tests for src/lib/maic-v2/use-scene-buffer.ts (MAIC-403.3).
 *
 * Hook tests via @testing-library/react renderHook — verify
 * useMemo identity tracking + reducer parity with reduceEvents.
 */
import { describe, test, expect } from 'vitest';
import { renderHook } from '@testing-library/react';

import { useSceneBuffer } from '../use-scene-buffer';
import { reduceEvents } from '../scene-buffer';
import type { MaicEvent } from '../../../hooks/useMaicClassroomChannelV2';


function thinking(stage = 'agent_loading'): MaicEvent {
  return { type: 'thinking', data: { stage } };
}

function agentStart(messageId = 'm1'): MaicEvent {
  return {
    type: 'agent_start',
    data: {
      messageId,
      agentId: 'default-1',
      agentName: 'AI teacher',
      agentAvatar: null,
      agentColor: '#3b82f6',
    },
  };
}

function textDelta(content: string, messageId = 'm1'): MaicEvent {
  return { type: 'text_delta', data: { content, messageId } };
}


describe('useSceneBuffer', () => {
  test('returns EMPTY_SCENE_BUFFER shape for an empty events array', () => {
    const { result } = renderHook(() => useSceneBuffer([]));
    expect(result.current.status).toBe('idle');
    expect(result.current.currentAgent).toBeNull();
    expect(result.current.actions).toEqual([]);
    expect(result.current.textByMessageId).toEqual({});
  });

  test('matches reduceEvents byte-for-byte for a Phase-1 turn', () => {
    const events: MaicEvent[] = [
      thinking(),
      agentStart('m1'),
      textDelta('Hello, ', 'm1'),
      textDelta('students.', 'm1'),
    ];
    const { result } = renderHook(({ ev }) => useSceneBuffer(ev), {
      initialProps: { ev: events },
    });
    expect(result.current).toEqual(reduceEvents(events));
  });

  test('preserves identity across re-renders when events array reference is stable', () => {
    const events: MaicEvent[] = [thinking(), agentStart()];
    const { result, rerender } = renderHook(
      ({ ev }) => useSceneBuffer(ev),
      { initialProps: { ev: events } },
    );
    const first = result.current;
    rerender({ ev: events });
    expect(result.current).toBe(first);
  });

  test('recomputes when events array reference changes', () => {
    const initial: MaicEvent[] = [thinking()];
    const next: MaicEvent[] = [thinking(), agentStart('m1'), textDelta('Hi.', 'm1')];
    const { result, rerender } = renderHook(
      ({ ev }) => useSceneBuffer(ev),
      { initialProps: { ev: initial } },
    );
    expect(result.current.status).toBe('thinking');

    rerender({ ev: next });
    expect(result.current.status).toBe('streaming');
    expect(result.current.currentAgent?.messageId).toBe('m1');
    expect(result.current.textByMessageId['m1']).toBe('Hi.');
  });
});
