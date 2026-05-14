/**
 * Transcript — progressive rendering of text deltas + status hints.
 *
 * Used by:
 *   - frontend/src/components/maic-v2/Stage.tsx (MAIC-403.7)
 *
 * Pure presentational. Reads from SceneBuffer-derived props:
 *   - textByMessageId: ordered keyed text chunks
 *   - messageOrder:    arrival order of messageIds (so text always
 *                      renders top-down in the order agents spoke)
 *   - agentsByMessageId: agent metadata for color/name treatment
 *   - status:          drives the optional thinking / completion hints
 *   - thinkingStage:   shown alongside the thinking spinner
 *   - cueingUser:      renders the "Your turn — respond below" line
 *
 * Why messageOrder is a separate prop rather than Object.keys(): JS
 * object key iteration is insertion-order in modern engines, but
 * relying on that for a UI surface is fragile. Stage will compute the
 * order from the buffer, which preserves earlier speakers when the
 * current agent advances.
 */
import type {
  AgentSnapshot,
  SceneBufferStatus,
} from '../../lib/maic-v2/scene-buffer';


export interface TranscriptProps {
  textByMessageId: Record<string, string>;
  /** Arrival order of messageIds (oldest first). */
  messageOrder: string[];
  /** Agent metadata keyed by messageId, if known. */
  agentsByMessageId?: Record<string, AgentSnapshot>;
  status: SceneBufferStatus;
  thinkingStage: string | null;
  cueingUser: boolean;
}

function avatarText(agent: AgentSnapshot): string {
  const avatar = agent.agentAvatar ?? '';
  if (avatar.startsWith('http') || avatar.startsWith('/') || avatar.startsWith('data:')) {
    return agent.agentName.charAt(0).toUpperCase();
  }
  return avatar || agent.agentName.charAt(0).toUpperCase();
}


export function Transcript({
  textByMessageId,
  messageOrder,
  agentsByMessageId = {},
  status,
  thinkingStage,
  cueingUser,
}: TranscriptProps) {
  const hasAnyText = messageOrder.some((id) => (textByMessageId[id] ?? '').length > 0);

  return (
    <div
      data-testid="maic-v2-transcript"
      className="space-y-2 text-sm leading-relaxed"
    >
      {status === 'thinking' && (
        <div
          data-testid="maic-v2-thinking"
          className="flex items-center gap-2 text-muted-foreground italic"
        >
          <span className="inline-block w-2 h-2 rounded-full bg-current animate-pulse" />
          <span>{thinkingStage ?? 'Thinking…'}</span>
        </div>
      )}

      {messageOrder.map((id) => {
        const text = textByMessageId[id] ?? '';
        if (!text) return null;
        const agent = agentsByMessageId[id];
        return (
          <div
            key={id}
            data-testid={`maic-v2-transcript-row-${id}`}
            className="rounded-md border bg-muted/30 px-3 py-2"
            style={agent ? { borderLeft: `4px solid ${agent.agentColor}` } : undefined}
          >
            {agent && (
              <div
                data-testid={`maic-v2-transcript-agent-${id}`}
                className="mb-1 flex items-center gap-2 text-xs font-semibold"
                style={{ color: agent.agentColor }}
              >
                <span
                  className="inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px]"
                  style={{
                    border: `1px solid ${agent.agentColor}`,
                    color: agent.agentColor,
                  }}
                >
                  {avatarText(agent)}
                </span>
                <span>{agent.agentName}</span>
              </div>
            )}
            <p
              data-testid={`maic-v2-transcript-line-${id}`}
              className="whitespace-pre-wrap"
            >
              {text}
            </p>
          </div>
        );
      })}

      {status === 'error' && !hasAnyText && (
        <p data-testid="maic-v2-transcript-error" className="text-destructive">
          Something went wrong. Try restarting.
        </p>
      )}

      {cueingUser && (
        <p
          data-testid="maic-v2-cue-user"
          className="text-primary font-medium"
        >
          Your turn — respond below.
        </p>
      )}
    </div>
  );
}
