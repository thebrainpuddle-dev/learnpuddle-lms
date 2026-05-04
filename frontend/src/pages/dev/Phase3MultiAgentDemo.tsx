/**
 * Phase 3 Multi-Agent Demo — drives the FULL Stage with real
 * `useMaicClassroomChannelV2` against a running daphne backend.
 *
 * Mounts Stage with `startPayload: { agentIds, maxTurns }` so the
 * backend's `consumers.py:build_initial_state` constructs an
 * OrchestratorState with the 3-agent pool. The director's LLM-based
 * decision (MAIC-104.1) picks each next agent over the LangGraph
 * stream; agents emit `discussion` actions; the user joins via
 * ProactiveCard; LiveInput dispatches `user_message` over real WS;
 * backend's MAIC-110.5 user_message handler appends + restarts the
 * stream; agent reply renders via the same action protocol.
 *
 * No headless smoke for this route — daphne dependency would add CI
 * flake without new signal. Instead:
 *   - Backend pytest covers AC#1, AC#2 (`tests_director_graph_multi_agent.py`)
 *   - Frontend ProactiveCard + LiveInput unit tests cover AC#3-#5
 *   - `?scene=phase3-live-mode` smoke (MAIC-418.3) covers the
 *     full live-mode flow without backend
 *   - This route is the human-driven walkthrough that shows it all
 *     works end-to-end against real LangGraph + edge_tts
 *
 * Manual walkthrough recipe (from PHASE-3-CLOSURE.md):
 *   1. Run daphne with the standard env vars
 *   2. Visit /dev/maic-v2?scene=phase3-demo&token=<jwt>
 *   3. Click Start → observe 3-agent chain → ProactiveCard → Join →
 *      LiveInput → Send → backend agent reply → End → resume lecture
 */
import { useState } from 'react';

import { Stage } from '../../components/maic-v2/Stage';


/** Default 3-agent pool for the multi-agent demo. */
const DEFAULT_DEMO_AGENT_IDS = ['default-1', 'default-3', 'default-4'];

/** Generous turn budget — covers a teacher intro + 2 student reactions
 *  + a follow-up + cue_user, with headroom. Backend caps at this value;
 *  the director can decide to end earlier via cue_user. */
const DEFAULT_DEMO_MAX_TURNS = 6;


export default function Phase3MultiAgentDemo() {
  const [sessionId] = useState(
    () => `phase3-demo-${Math.random().toString(36).slice(2, 10)}`,
  );

  return (
    <div
      data-testid="phase3-multi-agent-demo"
      style={{ fontFamily: 'system-ui, sans-serif', padding: 24, maxWidth: 1100 }}
    >
      <h1 style={{ marginTop: 0 }}>MAIC v2 — Phase 3 Multi-Agent Demo</h1>
      <p style={{ color: '#666', fontSize: 13, marginBottom: 16 }}>
        Real LangGraph director + edge_tts + WS. Requires daphne running and
        a JWT (via <code>?token=&lt;jwt&gt;</code> URL param or
        <code> VITE_MAIC_DEV_TOKEN </code> env var). Click Start to drive a
        3-agent classroom (teacher + 2 students). Director picks the next
        agent on each turn. After the teacher emits a <code>discussion</code>
        action, the ProactiveCard appears 3s later — click Join to enter
        live mode and exchange messages with the responding agent.
      </p>
      <div style={{ marginBottom: 16, fontSize: 12, color: '#666' }}>
        Agent pool: <code>{DEFAULT_DEMO_AGENT_IDS.join(', ')}</code>
        {' · '}
        Max turns: <b>{DEFAULT_DEMO_MAX_TURNS}</b>
        {' · '}
        Session id: <code>{sessionId}</code>
      </div>
      <Stage
        sessionId={sessionId}
        startPayload={{
          agentIds: DEFAULT_DEMO_AGENT_IDS,
          maxTurns: DEFAULT_DEMO_MAX_TURNS,
        }}
      />
    </div>
  );
}
