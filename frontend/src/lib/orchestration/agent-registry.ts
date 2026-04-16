// lib/orchestration/agent-registry.ts — Zustand store for agent configurations
//
// Manages the registry of agent configs used by the Director Graph.
// Agents can be registered from classroom data, discussion panels, or
// dynamically created during generation.

import { create } from 'zustand';
import type { AgentConfig } from './types';

// ─── Store Interface ─────────────────────────────────────────────────────────

interface AgentRegistryState {
  agents: Record<string, AgentConfig>;
  registerAgent: (agent: AgentConfig) => void;
  registerAgents: (agents: AgentConfig[]) => void;
  getAgent: (id: string) => AgentConfig | undefined;
  removeAgent: (id: string) => void;
  clearAgents: () => void;
  getAllAgents: () => AgentConfig[];
}

// ─── Store Implementation ────────────────────────────────────────────────────

export const useAgentRegistry = create<AgentRegistryState>()((set, get) => ({
  agents: {},

  registerAgent: (agent) =>
    set((state) => ({
      agents: { ...state.agents, [agent.id]: agent },
    })),

  registerAgents: (agents) =>
    set((state) => {
      const updated = { ...state.agents };
      for (const agent of agents) {
        updated[agent.id] = agent;
      }
      return { agents: updated };
    }),

  getAgent: (id) => get().agents[id],

  removeAgent: (id) =>
    set((state) => {
      const updated = { ...state.agents };
      delete updated[id];
      return { agents: updated };
    }),

  clearAgents: () => set({ agents: {} }),

  getAllAgents: () => Object.values(get().agents),
}));

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * Convert a MAICAgent (from the existing type system) to an AgentConfig
 * for use with the orchestration system.
 */
export function toAgentConfig(agent: {
  id: string;
  name: string;
  role: string;
  avatar?: string;
  color?: string;
  personality?: string;
  voice?: string;
}): AgentConfig {
  return {
    id: agent.id,
    name: agent.name,
    role: agent.role,
    avatar: agent.avatar,
    color: agent.color,
    persona: agent.personality,
    voiceConfig: agent.voice
      ? { providerId: 'default', voiceId: agent.voice }
      : undefined,
  };
}
