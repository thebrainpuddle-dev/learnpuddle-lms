// voiceResolver.ts
//
// CG-P0-6 (2026-04-27): Cycle-by-index voice fallback for MAIC playback.
//
// Background: when an agent's `voiceId` is missing from the store (e.g. Stage
// mounted before setAgents() settled, or the LLM-picked voiceId got dropped
// somewhere in the publish path), the runtime fell back to a single literal
// `'en-IN-NeerjaNeural'` for every speech action. With multiple students in
// a roster, all students sounded identical.
//
// Fix: index-modulo through gender-appropriate per-role pools, so two
// distinct agents in the same roster CANNOT collapse to the same fallback
// voice (up to the pool size). Mirrors the backend's AGENT_VOICE_MAP +
// publish-time stamp.

import type { MAICAgent } from '../types/maic';

/** Full Azure en-IN voice roster, ordered M/F/M/F/... so the global cycling
 *  fallback alternates gender. Mirrors backend `maic_voices.py`. */
const VOICE_POOL: readonly string[] = [
  'en-IN-PrabhatNeural',  // M (adult)
  'en-IN-NeerjaNeural',   // F (adult)
  'en-IN-AaravNeural',    // M (young)
  'en-IN-KavyaNeural',    // F (adult)
  'en-IN-KunalNeural',    // M (adult)
  'en-IN-AashiNeural',    // F (young)
  'en-IN-RehaanNeural',   // M (young)
];

/** Per-role voice pools. Each role gets ≥2 voices so two agents of the same
 *  role still get distinct voices. Genders chosen per role's typical persona. */
const ROLE_VOICE_POOLS: Record<string, readonly string[]> = {
  professor: ['en-IN-PrabhatNeural', 'en-IN-KunalNeural'],            // M, M
  teaching_assistant: ['en-IN-NeerjaNeural', 'en-IN-KavyaNeural'],    // F, F
  student_rep: ['en-IN-AaravNeural', 'en-IN-RehaanNeural'],           // M, M
  moderator: ['en-IN-KavyaNeural', 'en-IN-NeerjaNeural'],             // F, F
  // Students are mixed-gender on purpose so a 3-student panel sounds varied
  student: ['en-IN-AashiNeural', 'en-IN-AaravNeural', 'en-IN-RehaanNeural'],
  assistant: ['en-IN-NeerjaNeural', 'en-IN-PrabhatNeural'],           // F, M
};

/**
 * Pick a deterministic voice for `agent` based on its index in the
 * `agents` roster. Same agent in same roster → same voice (idempotent).
 * Different agents of the same role → different voices (cycled).
 *
 * Use ONLY when the agent's explicit `voiceId` is missing — never as a
 * primary path.
 */
export function resolveVoiceForAgent(
  agent: MAICAgent | undefined,
  agents: readonly MAICAgent[],
): string {
  if (!agent) {
    // No agent record at all (e.g. unknown agentId from a stale action).
    // Use the first voice in the global pool as the safest stable default.
    return VOICE_POOL[0];
  }
  const idx = agents.findIndex((a) => a.id === agent.id);
  const safeIdx = idx >= 0 ? idx : 0;
  const pool = ROLE_VOICE_POOLS[agent.role] ?? VOICE_POOL;
  return pool[safeIdx % pool.length];
}
