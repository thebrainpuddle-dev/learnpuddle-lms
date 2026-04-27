// lib/orchestration/director.ts — Client-side Director Graph
//
// Pure-code director that manages agent turn-taking without LLM calls on the
// client. The director decides which agent speaks next using simple rules:
//   - Single agent: dispatch on turn 0, cue user on turn 1+.
//   - Multi agent: round-robin order, each agent gets one turn, then cue user.
//   - Discussion: all agents respond to the topic in order.
//
// LLM generation happens on the backend via SSE streaming.

import { streamMAIC } from '../maicSSE';
import { getAccessToken } from '../../utils/authSession';
import { buildAgentSystemPrompt } from './prompt-builder';
import { maicChatUrl, maicDirectorTurnUrl, type MAICRole } from '../maic/endpoints';
import type {
  AgentConfig,
  DirectorDecision,
  AgentTurnSummary,
  OrchestrationState,
  OrchestrationCallbacks,
} from './types';
import type { MAICSSEEvent } from '../../types/maic';

// ─── Constants ───────────────────────────────────────────────────────────────

const DEFAULT_MAX_TURNS = 10;

// ─── Director Graph ──────────────────────────────────────────────────────────

export class DirectorGraph {
  private state: OrchestrationState;
  private agents: AgentConfig[];
  private callbacks: OrchestrationCallbacks;
  private abortController: AbortController | null = null;
  private stopped = false;

  // Turn order tracking for round-robin
  private turnOrder: string[];
  private turnOrderIndex = 0;

  // Optional: trigger a specific agent first
  private triggerAgentId: string | null;

  // Player role — decides which chat endpoint to hit.
  private role: MAICRole;

  // Slide context for building prompts
  private slideContext?: {
    currentSceneTitle?: string;
    slideContent?: string;
    previousMessages?: Array<{ role: string; content: string; agentId?: string }>;
  };

  constructor(
    agents: AgentConfig[],
    callbacks: OrchestrationCallbacks,
    options?: {
      maxTurns?: number;
      discussionContext?: { topic: string; prompt?: string };
      triggerAgentId?: string;
      role?: MAICRole;
      slideContext?: {
        currentSceneTitle?: string;
        slideContent?: string;
        previousMessages?: Array<{ role: string; content: string; agentId?: string }>;
      };
    },
  ) {
    this.agents = agents;
    this.callbacks = callbacks;
    this.triggerAgentId = options?.triggerAgentId ?? null;
    this.role = options?.role ?? 'teacher';
    this.slideContext = options?.slideContext;

    // Build turn order — if triggerAgentId is specified, put it first
    if (this.triggerAgentId && agents.some((a) => a.id === this.triggerAgentId)) {
      const rest = agents.filter((a) => a.id !== this.triggerAgentId);
      this.turnOrder = [this.triggerAgentId, ...rest.map((a) => a.id)];
    } else {
      this.turnOrder = agents.map((a) => a.id);
    }

    this.state = {
      turnCount: 0,
      maxTurns: options?.maxTurns ?? DEFAULT_MAX_TURNS,
      currentAgentId: null,
      agentResponses: [],
      shouldEnd: false,
      discussionContext: options?.discussionContext,
    };
  }

  // ─── Public API ────────────────────────────────────────────────────

  /** Start orchestration from scratch. */
  async start(): Promise<void> {
    this.stopped = false;
    this.callbacks.onThinking('Starting orchestration...');

    // Loop: decide → generate → repeat until done or stopped
    while (!this.stopped && !this.state.shouldEnd) {
      await this.processTurn();
    }
  }

  /** Stop orchestration. */
  stop(): void {
    this.stopped = true;
    this.state.shouldEnd = true;
    this.abortController?.abort();
    this.abortController = null;
  }

  /** Get current orchestration state (read-only snapshot). */
  getState(): OrchestrationState {
    return { ...this.state };
  }

  // ─── Turn Processing ──────────────────────────────────────────────

  private async processTurn(): Promise<void> {
    // Guard: max turns reached
    if (this.state.turnCount >= this.state.maxTurns) {
      this.state.shouldEnd = true;
      this.callbacks.onCueUser(this.state.currentAgentId ?? undefined);
      return;
    }

    const decision = await this.decideAsync();

    if (decision.shouldEnd || !decision.nextAgentId) {
      this.state.shouldEnd = true;
      if (decision.reason) {
        this.callbacks.onThinking(decision.reason);
      }
      this.callbacks.onCueUser(this.state.currentAgentId ?? undefined);
      return;
    }

    // Run the chosen agent's generation
    this.state.currentAgentId = decision.nextAgentId;
    const agent = this.agents.find((a) => a.id === decision.nextAgentId);
    if (!agent) {
      this.callbacks.onError(`Agent ${decision.nextAgentId} not found`);
      this.state.shouldEnd = true;
      return;
    }

    this.callbacks.onThinking(`${agent.name} is preparing a response...`, agent.id);

    try {
      const summary = await this.runAgentGeneration(agent);
      this.state.agentResponses.push(summary);
      this.state.turnCount++;
      this.turnOrderIndex++;
    } catch (err) {
      if (this.stopped) return;
      const message = err instanceof Error ? err.message : 'Agent generation failed';
      this.callbacks.onError(message);
      // Don't halt entirely — try next agent
      this.state.turnCount++;
      this.turnOrderIndex++;
    }
  }

  // ─── Decision Logic ───────────────────────────────────────────────

  /** Synchronous round-robin decision — used as the fallback when the
   *  LLM director endpoint is unavailable or returns an invalid id. */
  private decide(): DirectorDecision {
    const agentCount = this.agents.length;

    // Single agent mode
    if (agentCount === 1) {
      if (this.state.turnCount === 0) {
        return { nextAgentId: this.agents[0].id, shouldEnd: false };
      }
      return { nextAgentId: null, shouldEnd: true, reason: 'Agent has responded' };
    }

    // Multi-agent fallback: round-robin
    if (this.turnOrderIndex < this.turnOrder.length) {
      const nextId = this.turnOrder[this.turnOrderIndex];
      return {
        nextAgentId: nextId,
        shouldEnd: false,
        reason: `Round-robin turn ${this.turnOrderIndex + 1}/${this.turnOrder.length}`,
      };
    }

    return { nextAgentId: null, shouldEnd: true, reason: 'All agents have contributed' };
  }

  /**
   * Porting P3.1 — LLM-decided next speaker. Calls the backend director
   * endpoint with the roster + transcript and returns its pick. On 204
   * (LLM declined), malformed output, network error, or timeout, falls
   * back to `this.decide()` (round-robin).
   */
  private async decideAsync(): Promise<DirectorDecision> {
    if (this.agents.length < 2) return this.decide();

    // Special-case the very first turn: prefer the user's trigger agent
    // so the conversation opens with the named inviter, not the LLM's
    // guess. Everything after that is LLM-picked.
    if (this.state.turnCount === 0 && this.triggerAgentId) {
      return {
        nextAgentId: this.triggerAgentId,
        shouldEnd: false,
        reason: 'Trigger agent opens the discussion',
      };
    }

    const token = getAccessToken();
    if (!token) return this.decide();

    try {
      const body = {
        agents: this.agents.map((a) => ({
          id: a.id,
          name: a.name,
          role: a.role,
          persona: a.persona,
          speakingStyle: (a as AgentConfig & { speakingStyle?: string }).speakingStyle,
        })),
        transcript: this.state.agentResponses,
        topic: this.state.discussionContext?.topic || '',
        lastSpeakerId: this.state.currentAgentId,
      };
      const res = await fetch(maicDirectorTurnUrl(this.role), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(body),
        // Abort quickly if the director endpoint is slow — we'd rather
        // round-robin than stall the discussion.
        signal: AbortSignal.timeout(8000),
      });
      if (res.status === 204 || !res.ok) return this.decide();
      const data = (await res.json()) as { next_speaker_id?: string; reasoning?: string };
      const nextId = (data.next_speaker_id || '').trim();
      if (!nextId) {
        // Empty id = director says end the discussion.
        return { nextAgentId: null, shouldEnd: true, reason: data.reasoning || 'Director ended discussion' };
      }
      if (!this.agents.some((a) => a.id === nextId)) return this.decide();
      // Advance our turnOrderIndex so round-robin fallback stays sensible
      // if the LLM dies mid-way.
      this.turnOrderIndex = Math.min(this.turnOrderIndex + 1, this.turnOrder.length);
      return { nextAgentId: nextId, shouldEnd: false, reason: data.reasoning };
    } catch {
      return this.decide();
    }
  }

  // ─── Agent Generation ─────────────────────────────────────────────

  private async runAgentGeneration(agent: AgentConfig): Promise<AgentTurnSummary> {
    const token = getAccessToken();
    if (!token) {
      throw new Error('No authentication token available');
    }

    const messageId = `orch-${agent.id}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;

    // Porting P3.3 — thread the running discussion transcript into the
    // agent's system prompt so they can reference prior turns ("as Alice
    // noted earlier…"). We fold `agentResponses` into `previousMessages`
    // on top of any slideContext history the caller already supplied.
    const transcriptAsMessages = this.state.agentResponses.map((r) => ({
      role: 'assistant',
      content: r.contentPreview,
      agentId: r.agentId,
    }));
    const priorMessages = [
      ...(this.slideContext?.previousMessages ?? []),
      ...transcriptAsMessages,
    ];

    // Build system prompt for this agent
    const systemPrompt = buildAgentSystemPrompt(agent, {
      currentSceneTitle: this.slideContext?.currentSceneTitle,
      slideContent: this.slideContext?.slideContent,
      previousMessages: priorMessages,
      discussionContext: this.state.discussionContext,
    });

    // Build messages array from conversation history
    const messages: Array<{ role: string; content: string }> = [];
    if (this.state.discussionContext) {
      messages.push({
        role: 'user',
        content: this.state.discussionContext.prompt || this.state.discussionContext.topic,
      });
    }

    // Add previous agent responses as context
    for (const resp of this.state.agentResponses) {
      messages.push({
        role: 'assistant',
        content: `[${resp.agentName}]: ${resp.contentPreview}`,
      });
    }

    // Notify start
    this.callbacks.onAgentStart(agent.id, agent.name);

    // Create abort controller for this generation
    this.abortController = new AbortController();

    let fullContent = '';
    let actionCount = 0;

    await streamMAIC({
      url: maicChatUrl(this.role),
      body: {
        agentId: agent.id,
        messages,
        systemPrompt,
        discussionContext: this.state.discussionContext,
      },
      token,
      signal: this.abortController.signal,
      onEvent: (event: MAICSSEEvent) => {
        if (this.stopped) return;

        if (event.type === 'chat_message') {
          const data = event.data as { content?: string; agentId?: string };
          if (data.content) {
            fullContent += data.content;
            this.callbacks.onTextDelta(data.content, agent.id);
          }
        } else if (event.type === 'agent_thinking') {
          const data = event.data as { text?: string };
          if (data.text) {
            this.callbacks.onThinking(data.text, agent.id);
          }
        } else if (event.type === 'error') {
          const data = event.data as { message?: string };
          this.callbacks.onError(data.message || 'Unknown streaming error');
        }
      },
      onError: (err) => {
        if (!this.stopped) {
          this.callbacks.onError(err.message);
        }
      },
      onDone: () => {
        // Stream complete
      },
    });

    this.abortController = null;

    // Notify end
    this.callbacks.onAgentEnd(agent.id);

    return {
      agentId: agent.id,
      agentName: agent.name,
      contentPreview: fullContent.slice(0, 500),
      actionCount,
    };
  }
}
