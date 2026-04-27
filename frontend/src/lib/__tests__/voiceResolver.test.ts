// voiceResolver.test.ts
//
// CG-P0-6 — When the LLM-assigned voiceId is missing, the runtime fallback
// must produce DISTINCT voices for distinct agents in the same roster.
// Previously every agent of the same role collapsed to one ROLE_VOICE_MAP
// entry → "all students sounded alike". Cycle-by-index fixes this.

import { describe, it, expect } from 'vitest';
import { resolveVoiceForAgent } from '../voiceResolver';
import type { MAICAgent } from '../../types/maic';

const mkAgent = (id: string, role: MAICAgent['role'], name = id): MAICAgent => ({
  id,
  name,
  role,
  avatar: '🦊',
  color: '#000',
});

describe('resolveVoiceForAgent — cycle-by-index distinct-voice property', () => {
  it('returns DISTINCT voices for two agents of the same role', () => {
    const agents: MAICAgent[] = [
      mkAgent('a1', 'student', 'Alice'),
      mkAgent('a2', 'student', 'Bob'),
    ];
    const v1 = resolveVoiceForAgent(agents[0], agents);
    const v2 = resolveVoiceForAgent(agents[1], agents);
    expect(v1).not.toBe(v2);
  });

  it('returns DISTINCT voices for three agents of the same role', () => {
    const agents: MAICAgent[] = [
      mkAgent('a1', 'student'),
      mkAgent('a2', 'student'),
      mkAgent('a3', 'student'),
    ];
    const voices = agents.map((a) => resolveVoiceForAgent(a, agents));
    expect(new Set(voices).size).toBe(3);
  });

  it('is deterministic — same agent in same roster always gets same voice', () => {
    const agents: MAICAgent[] = [
      mkAgent('a1', 'professor'),
      mkAgent('a2', 'student'),
      mkAgent('a3', 'student'),
    ];
    expect(resolveVoiceForAgent(agents[2], agents)).toBe(
      resolveVoiceForAgent(agents[2], agents),
    );
  });

  it('uses an Indian Azure neural voice (en-IN or hi-IN)', () => {
    // CG-P1-1: roster includes Hindi-locale Madhur/Swara that read
    // English well — needed because Microsoft only serves 3 en-IN
    // voices and our agent rosters need >3 distinct voices.
    const agent = mkAgent('a1', 'professor');
    expect(resolveVoiceForAgent(agent, [agent])).toMatch(/^(en-IN|hi-IN)-\w+Neural$/);
  });

  it('falls back gracefully for unknown agent (returns a real voice, not empty)', () => {
    const v = resolveVoiceForAgent(undefined, []);
    expect(v).toMatch(/^(en-IN|hi-IN)-\w+Neural$/);
  });

  it('falls back gracefully for unknown role (uses global pool, still distinct)', () => {
    const agents: MAICAgent[] = [
      mkAgent('a1', 'unknown_role' as MAICAgent['role']),
      mkAgent('a2', 'unknown_role' as MAICAgent['role']),
    ];
    const v1 = resolveVoiceForAgent(agents[0], agents);
    const v2 = resolveVoiceForAgent(agents[1], agents);
    expect(v1).not.toBe(v2);
  });
});
