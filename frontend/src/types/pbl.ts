/**
 * PBL (Project-Based Learning) Type Definitions
 *
 * Source: THU-MAIC/OpenMAIC lib/pbl/types.ts (lifted under ADR-001a).
 *         Backend mirror at backend/apps/maic_pbl/types.py (Pydantic
 *         port). Keep in lockstep.
 *
 * Used by:
 *  - frontend/src/types/maic-scenes.ts:MAICPBLContent (wraps
 *    PBLProjectConfig — landed in MAIC-705)
 *  - frontend/src/components/maic/PBLRenderer.tsx (consumes the
 *    full nested shape — updated in MAIC-705)
 *  - frontend/src/hooks/useMaicPBLChannel.ts (sends + receives
 *    PBLChatMessage shapes over WS — landed in MAIC-706)
 */

export type PBLMode = 'project_info' | 'agent' | 'issueboard' | 'idle';

export interface PBLProjectInfo {
  title: string;
  description: string;
}

export type PBLRoleDivision = 'management' | 'development';

export interface PBLAgent {
  name: string;
  actor_role: string;
  role_division: PBLRoleDivision;
  system_prompt: string;
  default_mode: string;
  delay_time: number;
  env: Record<string, unknown>;
  is_user_role: boolean;
  is_active: boolean;
  is_system_agent: boolean;
}

export interface PBLIssue {
  id: string;
  title: string;
  description: string;
  person_in_charge: string;
  participants: string[];
  notes: string;
  parent_issue: string | null;
  index: number;
  is_done: boolean;
  is_active: boolean;
  generated_questions: string;
  question_agent_name: string;
  judge_agent_name: string;
}

export interface PBLIssueboard {
  agent_ids: string[];
  issues: PBLIssue[];
  current_issue_id: string | null;
}

export interface PBLChatMessage {
  id: string;
  agent_name: string;
  message: string;
  timestamp: number;
  read_by: string[];
}

export interface PBLChat {
  messages: PBLChatMessage[];
}

export interface PBLProjectConfig {
  projectInfo: PBLProjectInfo;
  agents: PBLAgent[];
  issueboard: PBLIssueboard;
  chat: PBLChat;
  selectedRole?: string | null;
}

/**
 * MCP tool result envelope — every Phase 7 design tool returns this.
 * `extra='allow'` semantics on the backend (Pydantic) → arbitrary
 * extra fields are preserved on the wire. TS reflects that with an
 * index signature for unknown keys.
 */
export interface PBLToolResult {
  success: boolean;
  error?: string;
  message?: string;
  [key: string]: unknown;
}
