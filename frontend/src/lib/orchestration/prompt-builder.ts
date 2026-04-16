// lib/orchestration/prompt-builder.ts — Build system prompts for agents
//
// Constructs system prompts sent to the Django backend for LLM generation.
// Each agent gets a persona-aware prompt with scene context and conversation
// history so the backend can generate contextually appropriate responses.

import type { AgentConfig } from './types';

// ─── Role Descriptions ──────────────────────────────────────────────────────

const ROLE_DESCRIPTIONS: Record<string, string> = {
  professor:
    'You are a university professor who explains concepts clearly and thoroughly. ' +
    'You use examples and analogies to make complex topics accessible. ' +
    'You encourage critical thinking and ask thought-provoking questions.',
  teaching_assistant:
    'You are a teaching assistant who helps break down complex topics into ' +
    'manageable pieces. You provide practical examples and clarify points ' +
    'that students might find confusing. You are supportive and approachable.',
  student_rep:
    'You are a student representative who asks questions that students might ' +
    'have. You bring a learner perspective and are not afraid to ask for ' +
    'clarification. You help make discussions more relatable.',
  moderator:
    'You are a discussion moderator who keeps the conversation on track, ' +
    'summarizes key points, and ensures all perspectives are heard. ' +
    'You ask follow-up questions to deepen the discussion.',
  student:
    'You are a curious and engaged student who participates actively in ' +
    'discussions. You share your understanding and ask thoughtful questions ' +
    'when something is unclear.',
  assistant:
    'You are a helpful AI assistant who provides clear, accurate information. ' +
    'You adapt your explanations to the audience and provide relevant examples.',
};

// ─── System Prompt Builder ───────────────────────────────────────────────────

/**
 * Build a system prompt for an agent based on its config and current context.
 * The resulting prompt is sent to the backend as part of the chat request.
 */
export function buildAgentSystemPrompt(
  agent: AgentConfig,
  context: {
    currentSceneTitle?: string;
    slideContent?: string;
    previousMessages?: Array<{ role: string; content: string; agentId?: string }>;
    discussionContext?: { topic: string; prompt?: string };
  },
): string {
  const parts: string[] = [];

  // 1. Agent identity and role
  parts.push(`You are ${agent.name}, a ${agent.role} in an AI classroom.`);

  // 2. Persona / role description
  if (agent.persona) {
    parts.push(agent.persona);
  } else {
    const roleDesc = ROLE_DESCRIPTIONS[agent.role];
    if (roleDesc) {
      parts.push(roleDesc);
    }
  }

  // 3. Scene context
  if (context.currentSceneTitle) {
    parts.push(`\nCurrent topic: "${context.currentSceneTitle}".`);
  }

  if (context.slideContent) {
    parts.push(`\nSlide content:\n${context.slideContent}`);
  }

  // 4. Discussion context
  if (context.discussionContext) {
    parts.push(`\nDiscussion topic: "${context.discussionContext.topic}".`);
    if (context.discussionContext.prompt) {
      parts.push(`Discussion prompt: ${context.discussionContext.prompt}`);
    }
  }

  // 5. Conversation context summary
  if (context.previousMessages && context.previousMessages.length > 0) {
    const summary = summarizeConversation(context.previousMessages);
    if (summary) {
      parts.push(`\nConversation so far:\n${summary}`);
    }
  }

  // 6. Behavioral guidelines
  parts.push(
    '\nGuidelines:',
    '- Keep responses concise and focused (2-4 paragraphs max).',
    '- Be conversational and engaging.',
    '- Reference what other agents have said when relevant.',
    '- Stay on topic and add unique value to the discussion.',
    '- Do not repeat what has already been said.',
  );

  return parts.join('\n');
}

// ─── Agent Roster ────────────────────────────────────────────────────────────

/**
 * Format the agent roster for use in director or context prompts.
 * Returns a human-readable list of agents and their roles.
 */
export function formatAgentRoster(agents: AgentConfig[]): string {
  if (agents.length === 0) return 'No agents configured.';

  const lines = agents.map((agent) => {
    const desc = agent.persona
      ? `${agent.name} (${agent.role}) — ${agent.persona.slice(0, 80)}`
      : `${agent.name} (${agent.role})`;
    return `- ${desc}`;
  });

  return `Agents in this session:\n${lines.join('\n')}`;
}

// ─── Conversation Summary ────────────────────────────────────────────────────

/**
 * Build a conversation summary from messages.
 * Keeps the most recent messages and truncates older ones to manage
 * context window size.
 */
export function summarizeConversation(
  messages: Array<{ role: string; content: string; agentId?: string }>,
): string {
  if (messages.length === 0) return '';

  const MAX_MESSAGES = 10;
  const MAX_CONTENT_LENGTH = 200;

  const recentMessages = messages.slice(-MAX_MESSAGES);
  const lines: string[] = [];

  for (const msg of recentMessages) {
    const sender = msg.role === 'user' ? 'Student' : msg.agentId || 'Agent';
    const content =
      msg.content.length > MAX_CONTENT_LENGTH
        ? msg.content.slice(0, MAX_CONTENT_LENGTH) + '...'
        : msg.content;
    lines.push(`${sender}: ${content}`);
  }

  if (messages.length > MAX_MESSAGES) {
    const omitted = messages.length - MAX_MESSAGES;
    lines.unshift(`[${omitted} earlier message${omitted > 1 ? 's' : ''} omitted]`);
  }

  return lines.join('\n');
}
