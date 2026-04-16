// lib/orchestration/types.ts — Type definitions for the client-side
// Director Graph multi-agent orchestration system.
//
// These types drive turn-taking, streaming responses, and state management
// without importing any server-side libraries (LangGraph, AI SDK, etc.).

// ─── Agent Configuration ─────────────────────────────────────────────────────

export interface AgentConfig {
  id: string;
  name: string;
  role: string;
  persona?: string;
  avatar?: string;
  color?: string;
  allowedActions?: string[];
  voiceConfig?: { providerId: string; modelId?: string; voiceId: string };
  isDefault?: boolean;
}

// ─── Director Decision ───────────────────────────────────────────────────────

export interface DirectorDecision {
  nextAgentId: string | null;
  shouldEnd: boolean;
  reason?: string;
}

// ─── Turn Summary ────────────────────────────────────────────────────────────

export interface AgentTurnSummary {
  agentId: string;
  agentName: string;
  contentPreview: string;
  actionCount: number;
}

// ─── Orchestration State ─────────────────────────────────────────────────────

export interface OrchestrationState {
  turnCount: number;
  maxTurns: number;
  currentAgentId: string | null;
  agentResponses: AgentTurnSummary[];
  shouldEnd: boolean;
  discussionContext?: { topic: string; prompt?: string };
}

// ─── Callbacks ───────────────────────────────────────────────────────────────

export interface OrchestrationCallbacks {
  onAgentStart: (agentId: string, agentName: string) => void;
  onTextDelta: (text: string, agentId: string) => void;
  onActionEmit: (action: unknown, agentId: string) => void;
  onAgentEnd: (agentId: string) => void;
  onThinking: (stage: string, agentId?: string) => void;
  onCueUser: (fromAgentId?: string) => void;
  onError: (message: string) => void;
}

// ─── Orchestration Events ────────────────────────────────────────────────────

export type OrchestrationEvent =
  | {
      type: 'agent_start';
      data: {
        messageId: string;
        agentId: string;
        agentName: string;
        agentAvatar?: string;
        agentColor?: string;
      };
    }
  | { type: 'text_delta'; data: { content: string; messageId: string } }
  | {
      type: 'action';
      data: {
        actionId: string;
        actionName: string;
        params: Record<string, unknown>;
        agentId: string;
        messageId: string;
      };
    }
  | { type: 'agent_end'; data: { messageId: string; agentId: string } }
  | { type: 'thinking'; data: { stage: string; agentId?: string } }
  | { type: 'cue_user'; data: { fromAgentId?: string } }
  | { type: 'error'; data: { message: string } }
  | { type: 'done'; data: Record<string, never> };
