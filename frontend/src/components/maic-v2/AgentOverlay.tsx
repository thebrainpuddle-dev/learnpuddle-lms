/**
 * AgentOverlay — visual identity strip for the currently-speaking agent.
 *
 * Used by:
 *   - frontend/src/components/maic-v2/Stage.tsx (MAIC-403.7)
 *
 * Renders avatar + name with the agent's theme color, plus an animated
 * three-bar voice-wave indicator when `speaking` is true. Pure
 * presentational — all state comes from props (sourced from
 * SceneBuffer.currentAgent and SceneBuffer.status === 'streaming').
 *
 * Why no shadcn Avatar dep: keeps Phase 1 self-contained — the
 * upstream `agent-avatar.tsx` (48 lines) uses shadcn primitives, but
 * for our visual surface a plain rounded div with the avatar string
 * (URL or emoji) is sufficient. We can re-introduce shadcn later if
 * we adopt that ui kit project-wide.
 *
 * Avatar string interpretation matches upstream:
 *   - http*, /, data: prefix  →  treated as image URL
 *   - anything else           →  rendered as text (emoji or single char)
 */
import type { AgentSnapshot } from '../../lib/maic-v2/scene-buffer';


export interface AgentOverlayProps {
  agent: AgentSnapshot | null;
  /** True when the agent is currently mid-speech (status==='streaming'). */
  speaking: boolean;
}


function isImageUrl(s: string): boolean {
  return s.startsWith('http') || s.startsWith('/') || s.startsWith('data:');
}


export function AgentOverlay({ agent, speaking }: AgentOverlayProps) {
  if (!agent) return null;

  const { agentName, agentAvatar, agentColor } = agent;
  const initial = agentName.charAt(0).toUpperCase();

  return (
    <div
      data-testid="maic-v2-agent-overlay"
      className="flex items-center gap-3 px-3 py-2 rounded-lg bg-white/80 backdrop-blur"
      style={{ borderLeft: `4px solid ${agentColor}` }}
    >
      <div
        data-testid="maic-v2-agent-avatar"
        className="w-10 h-10 rounded-full flex items-center justify-center overflow-hidden text-lg font-semibold"
        style={{
          backgroundColor: `${agentColor}20`,
          color: agentColor,
          border: `2px solid ${agentColor}`,
        }}
      >
        {agentAvatar && isImageUrl(agentAvatar) ? (
          <img src={agentAvatar} alt={agentName} className="w-full h-full object-cover" />
        ) : (
          <span>{agentAvatar || initial}</span>
        )}
      </div>

      <span
        data-testid="maic-v2-agent-name"
        className="text-sm font-semibold"
        style={{ color: agentColor }}
      >
        {agentName}
      </span>

      {speaking && (
        <div
          data-testid="maic-v2-voice-wave"
          aria-label="speaking"
          className="flex items-end gap-0.5 h-4 ml-1"
        >
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-1 rounded-sm"
              style={{
                backgroundColor: agentColor,
                animation: `maic-v2-wave 0.9s ease-in-out ${i * 0.15}s infinite`,
                height: '60%',
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}
