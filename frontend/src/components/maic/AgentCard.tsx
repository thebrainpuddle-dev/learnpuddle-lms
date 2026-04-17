// AgentCard.tsx — per-agent card for the wizard's Meet-your-classroom step.
//
// Shows avatar, name, role badge, a short persona teaser, a voice preview
// button with play/pause animation, and edit/regenerate actions. Voice-preview
// state is driven by the parent (a single audio element is shared across the
// whole grid so only one card plays at a time).

import { Play, Pause, Edit3, RotateCcw, Loader2 } from 'lucide-react';
import type { MAICAgent } from '../../types/maic';

export interface AgentCardProps {
  agent: MAICAgent;
  onEdit: (agent: MAICAgent) => void;
  onRegenerate: (agentId: string) => void;
  onPreviewVoice: (voiceId: string) => void;
  isPreviewing: boolean;
  isRegenerating?: boolean;
}

/** Turns "en-IN-PrabhatNeural" into "Prabhat" for compact display. */
function shortVoiceName(voiceId?: string): string {
  if (!voiceId) return 'voice';
  return voiceId.replace(/^en-[A-Z]{2}-/, '').replace(/Neural$/, '');
}

/** Normalises role enum values for display. "teaching_assistant" → "teaching assistant". */
function displayRole(role: string): string {
  return role.replace(/_/g, ' ');
}

export function AgentCard({
  agent,
  onEdit,
  onRegenerate,
  onPreviewVoice,
  isPreviewing,
  isRegenerating = false,
}: AgentCardProps) {
  const voiceLabel = shortVoiceName(agent.voiceId);
  const voiceId = agent.voiceId ?? '';

  return (
    <div
      data-testid="agent-card"
      data-agent-id={agent.id}
      className={[
        'group relative flex flex-col rounded-2xl border border-slate-200 bg-white p-5',
        'shadow-sm transition-all duration-200',
        'hover:-translate-y-0.5 hover:shadow-lg hover:border-slate-300',
        isRegenerating ? 'pointer-events-none' : '',
      ].join(' ')}
      style={{ borderTopColor: agent.color, borderTopWidth: 4 }}
    >
      {/* Regenerating overlay */}
      {isRegenerating && (
        <div
          className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 rounded-2xl bg-white/80 backdrop-blur-sm"
          aria-live="polite"
        >
          <Loader2 className="h-5 w-5 animate-spin text-slate-500" aria-hidden="true" />
          <span className="text-sm font-medium text-slate-600">Regenerating…</span>
        </div>
      )}

      {/* Avatar */}
      <div
        className="mb-3 flex h-14 w-14 items-center justify-center rounded-full text-4xl leading-none"
        style={{ backgroundColor: `${agent.color}14` /* 8% alpha */ }}
        role="img"
        aria-label={`Avatar for ${agent.name}`}
      >
        <span>{agent.avatar}</span>
      </div>

      {/* Name + role. `truncate` on the name keeps long-name cards the
          same height as short-name cards — no more 2-line "Mr. Kunal /
          Reddy" squeeze. `whitespace-nowrap` on the role chip prevents
          "Teaching Assistant" from splitting across two lines inside
          its own pill. */}
      <h3
        className="mb-1 truncate text-base font-semibold leading-tight text-slate-900"
        title={agent.name}
      >
        {agent.name}
      </h3>
      <span
        className="mb-3 inline-flex w-fit max-w-full items-center truncate whitespace-nowrap rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium capitalize text-slate-600"
      >
        {displayRole(agent.role)}
      </span>

      {/* Persona / teaser */}
      <p
        className="mb-4 line-clamp-2 min-h-[2.5rem] text-xs leading-relaxed text-slate-600"
        title={agent.personality ?? ''}
      >
        {agent.personality ?? 'No persona description.'}
      </p>

      {/* Voice preview row */}
      <div className="mb-4">
        <button
          type="button"
          onClick={() => onPreviewVoice(voiceId)}
          disabled={!voiceId}
          data-playing={isPreviewing ? 'true' : 'false'}
          aria-label="Preview voice"
          aria-pressed={isPreviewing}
          className={[
            'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
            'border transition-colors',
            isPreviewing
              ? 'border-indigo-200 bg-indigo-50 text-indigo-700'
              : 'border-slate-200 bg-slate-50 text-slate-700 hover:bg-slate-100',
            'disabled:cursor-not-allowed disabled:opacity-50',
          ].join(' ')}
        >
          <span className="relative flex h-3.5 w-3.5 items-center justify-center">
            {/* Play/Pause swap — absolutely positioned so the icon swap doesn't shift layout */}
            <Play
              size={13}
              className={[
                'absolute transition-all duration-150',
                isPreviewing ? 'scale-75 opacity-0' : 'scale-100 opacity-100',
              ].join(' ')}
              aria-hidden="true"
            />
            <Pause
              size={13}
              className={[
                'absolute transition-all duration-150',
                isPreviewing ? 'scale-100 opacity-100' : 'scale-75 opacity-0',
              ].join(' ')}
              aria-hidden="true"
            />
          </span>
          <span>{voiceLabel}</span>
          {isPreviewing && (
            <span className="ml-0.5 flex items-end gap-0.5" aria-hidden="true">
              <span className="h-1 w-0.5 animate-pulse rounded-sm bg-indigo-500 [animation-delay:-0.3s]" />
              <span className="h-1.5 w-0.5 animate-pulse rounded-sm bg-indigo-500 [animation-delay:-0.15s]" />
              <span className="h-1 w-0.5 animate-pulse rounded-sm bg-indigo-500" />
            </span>
          )}
        </button>
      </div>

      {/* Edit + regen actions */}
      <div className="mt-auto flex items-center gap-2">
        <button
          type="button"
          onClick={() => onEdit(agent)}
          className={[
            'flex-1 inline-flex items-center justify-center gap-1 rounded-lg border border-slate-200',
            'px-3 py-1.5 text-xs font-medium text-slate-700',
            'transition-colors hover:bg-slate-50 hover:border-slate-300',
            'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
          ].join(' ')}
          aria-label={`Edit ${agent.name}`}
        >
          <Edit3 size={12} aria-hidden="true" />
          <span>Edit</span>
        </button>
        <button
          type="button"
          onClick={() => onRegenerate(agent.id)}
          className={[
            'flex-1 inline-flex items-center justify-center gap-1 rounded-lg border border-slate-200',
            'px-3 py-1.5 text-xs font-medium text-slate-700',
            'transition-colors hover:bg-slate-50 hover:border-slate-300',
            'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
          ].join(' ')}
          aria-label={`Regen ${agent.name}`}
        >
          <RotateCcw size={12} aria-hidden="true" />
          <span>Regen</span>
        </button>
      </div>
    </div>
  );
}

export default AgentCard;
