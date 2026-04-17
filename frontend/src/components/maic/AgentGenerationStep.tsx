// AgentGenerationStep.tsx — wizard step that generates, previews, edits, and
// regenerates AI agent profiles before outline generation.
//
// Owned by Frontend-Wizard (WS-C). Shared between teacher and student wizards:
// pass role="teacher" or role="student" to pick the right API surface.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RotateCcw, Sparkles, Loader2, AlertCircle } from 'lucide-react';
import { maicApi, maicStudentApi, type MAICVoice } from '../../services/openmaicService';
import { AgentCard } from './AgentCard';
import { AgentEditModal } from './AgentEditModal';
import type { MAICAgent } from '../../types/maic';

/**
 * Default role split per the spec §8.3: 1 prof, 1 TA, 2 students = 4 agents.
 * The count can be tuned later; this keeps the voice roster diverse and the
 * roundtable balanced.
 */
const DEFAULT_ROLE_SLOTS = [
  { role: 'professor', count: 1 },
  { role: 'teaching_assistant', count: 1 },
  { role: 'student', count: 2 },
];

/**
 * Canned sample sentence for voice preview. Short enough to be TTS-friendly,
 * personable enough to give a real feel for the voice.
 */
const PREVIEW_SENTENCE = "Hello students, I'm excited to teach you about this topic today.";

export interface AgentGenerationStepProps {
  topic: string;
  language: string;
  role: 'teacher' | 'student';
  onComplete: (agents: MAICAgent[]) => void;
  onBack: () => void;
  /** Previously-approved agents. When provided (and non-empty), the step
   *  re-hydrates from them instead of regenerating. Lets users click "Back"
   *  from the outline step without losing the roster they already approved. */
  initialAgents?: MAICAgent[];
}

export function AgentGenerationStep({
  topic,
  language,
  role,
  onComplete,
  onBack,
  initialAgents,
}: AgentGenerationStepProps) {
  // Pick the right service surface based on caller role. The TTS-preview +
  // voice-roster endpoints only live on the teacher service today (per the
  // plan — both wizards can use them because they're tenant-scoped only).
  const api = role === 'student' ? maicStudentApi : maicApi;

  const [agents, setAgents] = useState<MAICAgent[]>(initialAgents ?? []);
  const [voices, setVoices] = useState<MAICVoice[]>([]);
  const [loading, setLoading] = useState(!(initialAgents && initialAgents.length));
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<MAICAgent | null>(null);
  const [regenIds, setRegenIds] = useState<Set<string>>(() => new Set());
  const [previewingVoice, setPreviewingVoice] = useState<string | null>(null);
  // Preview banner split into two channels:
  //   - `previewError`  (red)    — real failure worth a visible banner.
  //   - `previewInfo`   (slate)  — soft info, e.g. TTS provider not
  //                                configured in this env (backend 204 +
  //                                `X-TTS-Status: unavailable`). We must
  //                                not scare demo audiences with a red
  //                                alert for a non-error.
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewInfo, setPreviewInfo] = useState<string | null>(null);

  // Shared audio element — only one preview plays at a time.
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const blobUrlRef = useRef<string | null>(null);
  // Monotonic generation token — bumped on every preview start or stop.
  // Any async handler captured by an older token is a no-op. Kills the
  // double-click race (audio overlap + blob-URL leak + stuck pause icon).
  const previewGenRef = useRef(0);

  /** Tear down any active preview audio. */
  const stopPreview = useCallback(() => {
    previewGenRef.current++;
    if (audioRef.current) {
      audioRef.current.onended = null;
      audioRef.current.onerror = null;
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current);
      blobUrlRef.current = null;
    }
    setPreviewingVoice(null);
  }, []);

  const generateAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    stopPreview();
    try {
      const response = await api.generateAgentProfiles({
        topic,
        language,
        roleSlots: DEFAULT_ROLE_SLOTS,
      });
      const next = response.data?.agents ?? [];
      if (next.length === 0) {
        setError("We couldn't generate agents for that topic. Please try again.");
      } else {
        setAgents(next);
      }
    } catch {
      setError("We couldn't generate agents. Please try again.");
    } finally {
      setLoading(false);
    }
  }, [api, language, stopPreview, topic]);

  // Load voices once. Uses the teacher-surface listVoices which is a tenant-
  // scoped read, so both wizards can call it.
  useEffect(() => {
    let cancelled = false;
    maicApi
      .listVoices()
      .then((r) => {
        if (!cancelled) setVoices(r.data?.voices ?? []);
      })
      .catch(() => {
        // Non-fatal — editor falls back to "no voices available".
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Generate agents when the step mounts — unless the parent already supplied
  // an approved roster (e.g. user navigated Back from the outline step).
  useEffect(() => {
    if (initialAgents && initialAgents.length > 0) return;
    void generateAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Clean up any in-flight preview when the component unmounts.
  useEffect(() => {
    return () => stopPreview();
  }, [stopPreview]);

  const handleRegenerate = useCallback(
    async (agentId: string) => {
      setRegenIds((prev) => {
        const next = new Set(prev);
        next.add(agentId);
        return next;
      });
      try {
        const response = await api.regenerateAgent({
          topic,
          existingAgents: agents,
          targetAgentId: agentId,
          lockedFields: [],
        });
        const updated = response.data?.agent;
        if (updated) {
          setAgents((prev) => prev.map((a) => (a.id === agentId ? updated : a)));
        }
      } catch {
        // Soft-fail: surface a lightweight warning so the UI stays usable.
        setPreviewError("Couldn't regenerate that agent. Try again in a moment.");
      } finally {
        setRegenIds((prev) => {
          const next = new Set(prev);
          next.delete(agentId);
          return next;
        });
      }
    },
    [agents, api, topic],
  );

  const handlePreviewVoice = useCallback(
    async (voiceId: string) => {
      if (!voiceId) return;

      // Clicking the currently-playing voice pauses it.
      if (previewingVoice === voiceId) {
        stopPreview();
        return;
      }

      stopPreview();                              // stopPreview bumps the token
      const myGen = previewGenRef.current;        // capture THIS preview's token
      setPreviewError(null);
      setPreviewInfo(null);

      try {
        const response = await maicApi.ttsPreview({
          voiceId,
          text: PREVIEW_SENTENCE,
        });
        // Stale? Another click superseded us — drop the response on the floor.
        if (myGen !== previewGenRef.current) return;

        // Backend returns HTTP 204 when the tenant's TTS provider is not
        // configured (common in fresh demo environments). The API client
        // still resolves — but .data is an empty Blob. Calling Audio.play
        // on an empty blob triggers onerror and historically flashed a
        // red "Voice preview unavailable" banner. Treat 204 as a soft
        // INFO state instead, and only warn on real errors.
        const ttsStatus =
          (response.headers as Record<string, string | undefined>)?.[
            'x-tts-status'
          ]?.toLowerCase() ?? '';
        if (response.status === 204 || ttsStatus === 'unavailable') {
          setPreviewInfo(
            'Preview unavailable in this environment — the voice will still be used during playback.',
          );
          stopPreview();
          return;
        }
        if (ttsStatus === 'error') {
          setPreviewError(
            'Voice preview failed. The voice will still be used during playback.',
          );
          stopPreview();
          return;
        }

        const blobUrl = URL.createObjectURL(response.data as Blob);
        // Race check a second time — in case stopPreview() fired while decoding.
        if (myGen !== previewGenRef.current) {
          URL.revokeObjectURL(blobUrl);
          return;
        }

        blobUrlRef.current = blobUrl;
        const audio = new Audio(blobUrl);
        audioRef.current = audio;
        audio.onended = () => {
          // Only tear down if WE own the current preview.
          if (myGen === previewGenRef.current) stopPreview();
        };
        audio.onerror = () => {
          if (myGen === previewGenRef.current) {
            setPreviewError(
              'Voice preview failed. The voice will still be used during playback.',
            );
            stopPreview();
          }
        };
        await audio.play();
        if (myGen !== previewGenRef.current) return;  // stopPreview() fired during play()
        setPreviewingVoice(voiceId);
      } catch (err) {
        if (myGen === previewGenRef.current) {
          // Axios throws for non-2xx when responseType: 'blob' — including
          // 204 on some clients. Sniff the response for the info channel.
          const axiosErr = err as { response?: { status?: number; headers?: Record<string, string | undefined> } };
          const errStatus =
            axiosErr.response?.headers?.['x-tts-status']?.toLowerCase?.() ?? '';
          if (axiosErr.response?.status === 204 || errStatus === 'unavailable') {
            setPreviewInfo(
              'Preview unavailable in this environment — the voice will still be used during playback.',
            );
          } else {
            setPreviewError(
              'Voice preview failed. The voice will still be used during playback.',
            );
          }
          stopPreview();
        }
      }
    },
    [previewingVoice, stopPreview],
  );

  const handleRegenerateAll = useCallback(() => {
    const ok = window.confirm(
      'Regenerate all agents? Any edits you made will be discarded.',
    );
    if (ok) {
      void generateAll();
    }
  }, [generateAll]);

  const agentCount = useMemo(() => agents.length, [agents.length]);

  // ── Render ──────────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="py-14 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100">
          <Sparkles className="h-6 w-6 animate-pulse text-indigo-500" aria-hidden="true" />
        </div>
        <h2 className="text-lg font-semibold text-slate-900">Meeting your agents…</h2>
        <p className="mt-1 text-sm text-slate-500">This takes about 10 seconds.</p>
        <div className="mx-auto mt-5 flex w-32 justify-center gap-1" aria-hidden="true">
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-indigo-400 [animation-delay:-0.3s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-indigo-400 [animation-delay:-0.15s]" />
          <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-indigo-400" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-12 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100">
          <AlertCircle className="h-6 w-6 text-red-500" aria-hidden="true" />
        </div>
        <p className="mb-4 text-sm text-red-700">{error}</p>
        <div className="flex items-center justify-center gap-2">
          <button
            type="button"
            onClick={onBack}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            ← Back
          </button>
          <button
            type="button"
            onClick={generateAll}
            className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700"
          >
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-5">
        <h2 className="text-xl font-semibold text-slate-900">Meet your classroom</h2>
        <p className="mt-1 text-sm text-slate-600">
          Your AI classroom has{' '}
          <span className="font-medium text-slate-900">
            {agentCount} {agentCount === 1 ? 'agent' : 'agents'}
          </span>
          . Preview their voices, tweak personas, or regenerate.
        </p>
      </div>

      {/* Error banner — shown only when preview actually failed. */}
      {previewError && (
        <div
          role="alert"
          className="mb-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{previewError}</span>
        </div>
      )}

      {/* Info banner — shown when TTS provider isn't configured in this
          environment. Neutral styling so demo audiences don't think
          something is broken. */}
      {previewInfo && !previewError && (
        <div
          role="status"
          className="mb-4 flex items-start gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-slate-400" aria-hidden="true" />
          <span>{previewInfo}</span>
        </div>
      )}

      {/* Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {agents.map((agent) => (
          <AgentCard
            key={agent.id}
            agent={agent}
            onEdit={setEditing}
            onRegenerate={handleRegenerate}
            onPreviewVoice={handlePreviewVoice}
            isPreviewing={previewingVoice !== null && previewingVoice === agent.voiceId}
            isRegenerating={regenIds.has(agent.id)}
          />
        ))}
      </div>

      {/* Footer */}
      <div className="mt-6 flex flex-col-reverse items-stretch justify-between gap-3 sm:flex-row sm:items-center">
        <button
          type="button"
          onClick={handleRegenerateAll}
          disabled={regenIds.size > 0}
          className={[
            'inline-flex items-center justify-center gap-1 rounded-lg border border-slate-200',
            'px-3 py-2 text-sm font-medium text-slate-700',
            'transition-colors hover:bg-slate-50 hover:border-slate-300',
            'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
            'disabled:cursor-not-allowed disabled:opacity-50',
          ].join(' ')}
        >
          {regenIds.size > 0 ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <RotateCcw className="h-4 w-4" aria-hidden="true" />
          )}
          Regenerate all
        </button>

        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onBack}
            className="rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            ← Back
          </button>
          <button
            type="button"
            onClick={() => {
              stopPreview();
              onComplete(agents);
            }}
            disabled={agents.length === 0}
            className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Looks good →
          </button>
        </div>
      </div>

      {/* Edit modal */}
      {editing && (
        <AgentEditModal
          agent={editing}
          voices={voices}
          onSave={(updated) => {
            setAgents((prev) => prev.map((a) => (a.id === updated.id ? updated : a)));
            setEditing(null);
          }}
          onCancel={() => setEditing(null)}
        />
      )}
    </div>
  );
}

export default AgentGenerationStep;
