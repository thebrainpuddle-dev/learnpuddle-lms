// AgentEditModal.tsx — edit one agent (name, persona, speakingStyle, voice).
//
// Used from AgentGenerationStep. Never calls the backend directly: Save emits
// the updated agent via onSave and the wizard keeps it in local state until
// the user clicks "Looks good →".

import { useEffect, useMemo, useState } from 'react';
import { X } from 'lucide-react';
import type { MAICAgent } from '../../types/maic';
import type { MAICVoice } from '../../services/openmaicService';

const MAX_PERSONALITY = 500;
const MAX_SPEAKING_STYLE = 200;

export interface AgentEditModalProps {
  agent: MAICAgent;
  voices: MAICVoice[];
  onSave: (agent: MAICAgent) => void;
  onCancel: () => void;
}

/** Turns "en-IN-PrabhatNeural" into "Prabhat" for dropdown options. */
function shortVoiceName(voiceId?: string): string {
  if (!voiceId) return 'voice';
  return voiceId.replace(/^en-[A-Z]{2}-/, '').replace(/Neural$/, '');
}

export function AgentEditModal({ agent, voices, onSave, onCancel }: AgentEditModalProps) {
  const [draft, setDraft] = useState<MAICAgent>(agent);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(agent);
    setError(null);
  }, [agent]);

  // Close on Escape.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onCancel]);

  const validVoices = useMemo(() => {
    // Prefer voices that suit the agent's role; fall back to the full list
    // so teachers aren't locked out if the backend happens to return a
    // shorter roster.
    const suited = voices.filter((v) => v.suits.includes(draft.role));
    if (suited.length > 0) return suited;
    return voices;
  }, [voices, draft.role]);

  const personality = draft.personality ?? '';
  const speakingStyle = draft.speakingStyle ?? '';

  function handleSave() {
    const trimmedName = draft.name.trim();
    if (!trimmedName) {
      setError('Name is required');
      return;
    }
    if (personality.length > MAX_PERSONALITY) {
      setError(`Personality is too long (${MAX_PERSONALITY} char max)`);
      return;
    }
    if (speakingStyle.length > MAX_SPEAKING_STYLE) {
      setError(`Speaking style is too long (${MAX_SPEAKING_STYLE} char max)`);
      return;
    }
    if (!draft.voiceId) {
      setError('Please choose a voice');
      return;
    }
    onSave({ ...draft, name: trimmedName });
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={`Edit ${agent.name}`}
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onCancel();
      }}
    >
      <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
        {/* Header */}
        <div className="mb-4 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">Edit agent</h2>
            <p className="text-xs text-slate-500">Changes save to this classroom only.</p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="-mt-1 -mr-1 rounded-full p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="Close"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        {/* Name */}
        <label className="mb-3 block">
          <span className="mb-1 block text-xs font-medium text-slate-700">Name</span>
          <input
            type="text"
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            value={draft.name}
            maxLength={80}
            onChange={(event) => setDraft({ ...draft, name: event.target.value })}
          />
        </label>

        {/* Personality */}
        <label className="mb-3 block">
          <span className="mb-1 flex items-center justify-between text-xs font-medium text-slate-700">
            <span>Personality</span>
            <span className="font-normal text-slate-400">
              {personality.length}/{MAX_PERSONALITY}
            </span>
          </span>
          <textarea
            className="w-full resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            rows={3}
            maxLength={MAX_PERSONALITY}
            value={personality}
            onChange={(event) => setDraft({ ...draft, personality: event.target.value })}
            placeholder="e.g., Patient and encouraging. Breaks down hard ideas with analogies."
          />
        </label>

        {/* Speaking style */}
        <label className="mb-3 block">
          <span className="mb-1 flex items-center justify-between text-xs font-medium text-slate-700">
            <span>Speaking style</span>
            <span className="font-normal text-slate-400">
              {speakingStyle.length}/{MAX_SPEAKING_STYLE}
            </span>
          </span>
          <textarea
            className="w-full resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            rows={2}
            maxLength={MAX_SPEAKING_STYLE}
            value={speakingStyle}
            onChange={(event) => setDraft({ ...draft, speakingStyle: event.target.value })}
            placeholder={"e.g., warm, reassuring, occasionally says 'theek hai?'"}
          />
        </label>

        {/* Voice */}
        <label className="mb-3 block">
          <span className="mb-1 block text-xs font-medium text-slate-700">Voice</span>
          <select
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
            value={draft.voiceId ?? ''}
            onChange={(event) => setDraft({ ...draft, voiceId: event.target.value })}
          >
            {!draft.voiceId && <option value="">— pick a voice —</option>}
            {validVoices.length === 0 && (
              <option value={draft.voiceId ?? ''} disabled>
                No voices available
              </option>
            )}
            {validVoices.map((voice) => (
              <option key={voice.id} value={voice.id}>
                {shortVoiceName(voice.id)} — {voice.gender}, {voice.tone}
              </option>
            ))}
          </select>
        </label>

        {error && (
          <p role="alert" className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
            {error}
          </p>
        )}

        {/* Footer */}
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

export default AgentEditModal;
