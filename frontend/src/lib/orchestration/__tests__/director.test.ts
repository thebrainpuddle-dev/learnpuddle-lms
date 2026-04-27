// director.test.ts — DirectorGraph LLM-decided next-speaker with fallback.
//
// The director calls `/api/v1/teacher/maic/director/turn/` to pick the
// next agent. On 204 / non-OK / network error / timeout, it must fall
// back to round-robin so discussions don't hard-stop on transient LLM
// failures. These specs lock in the fallback contract without actually
// running a real streamed discussion (we stub `streamMAIC` so each
// `runAgentGeneration` resolves immediately).

import { describe, test, expect, vi, beforeEach, afterEach } from 'vitest';
import { DirectorGraph } from '../director';
import type { OrchestrationCallbacks } from '../types';

// Stub the SSE helper so runAgentGeneration resolves without a network round-trip.
vi.mock('../../maicSSE', () => ({
  streamMAIC: vi.fn(async (opts: { onDone?: () => void }) => {
    opts.onDone?.();
  }),
}));

vi.mock('../../../utils/authSession', () => ({
  getAccessToken: () => 'test-token',
}));

const AGENTS = [
  { id: 'a1', name: 'Alice', role: 'professor' },
  { id: 'a2', name: 'Bob', role: 'student' },
  { id: 'a3', name: 'Carol', role: 'teaching_assistant' },
];

function buildCallbacks(): OrchestrationCallbacks & { starts: string[] } {
  const starts: string[] = [];
  return {
    starts,
    onAgentStart: (agentId: string) => starts.push(agentId),
    onTextDelta: () => undefined,
    onActionEmit: () => undefined,
    onAgentEnd: () => undefined,
    onThinking: () => undefined,
    onCueUser: () => undefined,
    onError: () => undefined,
  } as OrchestrationCallbacks & { starts: string[] };
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('DirectorGraph — LLM director with round-robin fallback', () => {
  test('first turn uses triggerAgentId (named inviter opens)', async () => {
    // No fetch calls for turn 0; we skip straight to the trigger agent.
    const cbs = buildCallbacks();
    const dg = new DirectorGraph(AGENTS, cbs, {
      maxTurns: 1,
      discussionContext: { topic: 'Why?' },
      triggerAgentId: 'a2', // bob invites
    });
    await dg.start();
    expect(cbs.starts[0]).toBe('a2');
    // No fetch should have been issued for the trigger-opened turn.
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBe(0);
  });

  test('falls back to round-robin when director endpoint returns 204', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(null, { status: 204 }),
    );
    const cbs = buildCallbacks();
    // maxTurns 2 so we burn the trigger-turn + one LLM-decided turn.
    const dg = new DirectorGraph(AGENTS, cbs, {
      maxTurns: 2,
      discussionContext: { topic: 'Why?' },
      triggerAgentId: 'a1',
    });
    await dg.start();
    // Turn 0: a1 (trigger). Turn 1: director called → 204 → fallback →
    // round-robin turnOrderIndex=1 → a2.
    expect(cbs.starts).toEqual(['a1', 'a2']);
    expect((fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBe(1);
  });

  test('falls back to round-robin when fetch throws (network error)', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('offline'));
    const cbs = buildCallbacks();
    const dg = new DirectorGraph(AGENTS, cbs, {
      maxTurns: 2,
      discussionContext: { topic: 'Why?' },
      triggerAgentId: 'a1',
    });
    await dg.start();
    expect(cbs.starts).toEqual(['a1', 'a2']);
  });

  test('uses LLM-picked agent when director returns a valid id', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(
        JSON.stringify({ next_speaker_id: 'a3', reasoning: 'Carol adds depth' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    const cbs = buildCallbacks();
    const dg = new DirectorGraph(AGENTS, cbs, {
      maxTurns: 2,
      discussionContext: { topic: 'Why?' },
      triggerAgentId: 'a1',
    });
    await dg.start();
    // Director skipped round-robin and picked a3 directly.
    expect(cbs.starts).toEqual(['a1', 'a3']);
  });

  test('rejects an unknown speaker id and falls back', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(
        JSON.stringify({ next_speaker_id: 'not-in-roster' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    const cbs = buildCallbacks();
    const dg = new DirectorGraph(AGENTS, cbs, {
      maxTurns: 2,
      discussionContext: { topic: 'Why?' },
      triggerAgentId: 'a1',
    });
    await dg.start();
    expect(cbs.starts).toEqual(['a1', 'a2']); // round-robin fallback
  });

  test('empty next_speaker_id ends the discussion', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(
        JSON.stringify({ next_speaker_id: '', reasoning: 'we are done' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );
    const cueSpy = vi.fn();
    const cbs: OrchestrationCallbacks = {
      onAgentStart: () => undefined,
      onTextDelta: () => undefined,
      onActionEmit: () => undefined,
      onAgentEnd: () => undefined,
      onThinking: () => undefined,
      onCueUser: cueSpy,
      onError: () => undefined,
    };
    const dg = new DirectorGraph(AGENTS, cbs, {
      maxTurns: 5,
      discussionContext: { topic: 'Why?' },
      triggerAgentId: 'a1',
    });
    await dg.start();
    expect(cueSpy).toHaveBeenCalled();
  });
});
