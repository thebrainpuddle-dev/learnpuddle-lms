// hooks/useMAICGeneration.ts — Orchestrates classroom generation flow

import { useState, useCallback, useEffect, useRef } from 'react';
import { useAuthStore } from '../stores/authStore';
import { useMAICStageStore } from '../stores/maicStageStore';
import { streamMAIC } from '../lib/maicSSE';
import { saveClassroom } from '../lib/maicDb';
import { maicApi } from '../services/openmaicService';
import type { MAICGenerationContextPayload } from '../services/openmaicService';
import { setGenerationActive } from '../utils/generationLock';
import { setLastActivityTimestamp } from '../utils/authSession';
import type {
  MAICOutline,
  MAICOutlineScene,
  MAICSlide,
  MAICAgent,
  MAICGenerationConfig,
  MAICSSEEvent,
} from '../types/maic';
import type { MAICScene, MAICSceneType, MAICSlideContent, MAICQuizContent, SceneSlideBounds } from '../types/maic-scenes';
import type { MAICAction } from '../types/maic-actions';

const V2_JOB_POLL_INTERVAL_MS = 2000;
const V2_JOB_MAX_CONSECUTIVE_POLL_ERRORS = 5;

/** Retry an async operation with exponential backoff. */
async function withRetry<T>(fn: () => Promise<T>, retries = 2, baseDelayMs = 2000): Promise<T> {
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      if (attempt === retries) throw err;
      await new Promise((r) => setTimeout(r, baseDelayMs * (attempt + 1)));
    }
  }
  throw new Error('Unreachable');
}

function generationContextFromConfig(config: MAICGenerationConfig): MAICGenerationContextPayload {
  return {
    ...(config.gradeLevel?.trim() ? { grade_level: config.gradeLevel.trim() } : {}),
    ...(config.subject?.trim() ? { subject: config.subject.trim() } : {}),
    ...(config.syllabusBoard?.trim() ? { syllabus_board: config.syllabusBoard.trim() } : {}),
    ...(config.classGuide?.trim() ? { class_guide: config.classGuide.trim() } : {}),
  };
}

function buildV2Specifications(config: MAICGenerationConfig): string {
  return [
    'Create a production-ready teacher-led AI classroom, not a static deck.',
    `Target exactly ${config.sceneCount} scenes with a coherent lesson arc.`,
    'Use slide, quiz, interactive, and PBL scene types only where they improve learning.',
    'Prefer one meaningful PBL/activity handoff over shallow extra slides when the topic benefits from doing.',
    'If a PBL/activity is used, place it after the concept foundation and include projectTopic, projectDescription, targetSkills, issueCount, roles, deliverable, constraints, and success criteria.',
    'Every scene description and keyPoints should preserve the teacher guide intent: audience, standards, misconceptions, formative checks, PBL brief, and discussion handoffs.',
    'Slides must be concise visual aids; spoken detail belongs in agent actions.',
    'Choreograph spotlight/laser/discussion handovers so audio, visual focus, and agent turns stay synchronized; point first, then speak.',
    config.classGuide?.trim()
      ? 'Follow the teacher class guide as the controlling planning document.'
      : '',
  ].filter(Boolean).join('\n');
}

function pendingOutlineFromConfig(
  config: MAICGenerationConfig,
  agents: MAICAgent[],
): MAICOutline {
  const total = Math.max(1, config.sceneCount || 1);
  const agentIds = agents.map((agent) => agent.id);
  return {
    topic: config.topic,
    language: config.language,
    agents,
    totalMinutes: total * 2,
    scenes: Array.from({ length: total }, (_, index) => ({
      id: `v2-pending-${index + 1}`,
      title: `Scene ${index + 1}`,
      description: 'Prepared by the v2 PBL graph pipeline.',
      type: 'lecture',
      estimatedMinutes: 2,
      agentIds,
    })),
  };
}

function waitForPollInterval(signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new DOMException('Generation cancelled', 'AbortError'));
      return;
    }
    const timer = window.setTimeout(resolve, V2_JOB_POLL_INTERVAL_MS);
    signal.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timer);
        reject(new DOMException('Generation cancelled', 'AbortError'));
      },
      { once: true },
    );
  });
}

function v2ClassroomId(result: Awaited<ReturnType<typeof maicApi.getV2GenerationJob>>['data']['result']): string | null {
  const artifact = result?.artifact;
  return (
    result?.classroomId ||
    result?.classroom_id ||
    artifact?.classroomId ||
    artifact?.classroom_id ||
    null
  );
}

function generationErrorMessage(raw: string): string {
  const message = raw.replace(/^RuntimeError:\s*/i, '').trim();
  const lower = message.toLowerCase();
  if (lower.includes('maic v2') && lower.includes('disabled for this deployment')) {
    return 'AI Classroom v2 is disabled for this deployment. Enable the MAIC_V2_ENABLED backend flag before creating live classrooms.';
  }
  if (lower.includes('maic v2') && lower.includes('not enabled')) {
    return 'AI Classroom v2 is not enabled for this school. Ask an admin to enable the tenant feature before creating live classrooms.';
  }
  if (lower.includes('ollama') && lower.includes('timed out')) {
    return 'The AI provider took too long while preparing the class outline. Try again, or switch this school to a faster production model before running a full PBL classroom.';
  }
  if (lower.includes('workerlosterror') || lower.includes('signal 11') || lower.includes('sigsegv')) {
    return 'The generation worker restarted unexpectedly while preparing scenes. Try again; if it repeats, run the worker with a safer concurrency setting and check the generation logs.';
  }
  if (lower.includes('no classroom was materialized')) {
    return 'Generation finished but the classroom was not saved. Please try again; if it repeats, check the generation worker logs.';
  }
  if (lower.includes('network error') || lower.includes('failed to fetch')) {
    return 'Lost connection while checking generation progress. The classroom may still be running; refresh the page or check the AI Classroom library.';
  }
  return message || 'Generation failed';
}

function generationErrorFromException(err: unknown): string {
  const response = (err as { response?: { data?: unknown; status?: number } } | null)?.response;
  const data = response?.data;
  let serverMessage = '';

  if (typeof data === 'string') {
    serverMessage = data;
  } else if (data && typeof data === 'object') {
    const body = data as {
      error?: unknown;
      detail?: unknown;
      message?: unknown;
      messages?: Array<{ message?: unknown }>;
    };
    serverMessage = String(body.error || body.detail || body.message || '').trim();
    if (!serverMessage && Array.isArray(body.messages)) {
      serverMessage = body.messages
        .map((item) => String(item?.message || '').trim())
        .filter(Boolean)
        .join(' ');
    }
  }

  if (serverMessage) {
    return generationErrorMessage(serverMessage);
  }
  if (response?.status === 403) {
    return generationErrorMessage('MAIC v2 not enabled');
  }
  return generationErrorMessage(err instanceof Error ? err.message : 'Generation failed');
}

export type GenerationStep = 'idle' | 'outlining' | 'editing' | 'generating' | 'complete' | 'error';
export type GenerationPhase = 'idle' | 'outline' | 'content' | 'actions' | 'saving';

interface UseMAICGenerationReturn {
  step: GenerationStep;
  phase: GenerationPhase;
  currentSceneIdx: number;
  totalScenes: number;
  outline: MAICOutline | null;
  progress: number;
  error: string | null;
  /** ms timestamp when generation started; null until first start. Used by
   *  GenerationVisualizer to render an honest elapsed timer. */
  startedAt: number | null;
  /** Whether the browser tab is currently hidden — UI freezes its local
   *  ticker when true and re-syncs on return so the user doesn't return
   *  to a stale/lying clock. */
  isTabHidden: boolean;
  /** T1.1 — ms timestamp set the moment scene 1 (content + actions) is
   *  fully generated. Null until it lands. The wizard uses this to
   *  offer an "Open now (scene 1 only)" button so the teacher can get
   *  into the classroom without waiting the full 5–10 min pipeline. */
  firstSceneReadyAt: number | null;

  /**
   * Generate the outline. Optionally pass `preSelectedAgents` — the roster
   * approved by the agent-picker wizard step (WS-C). When provided, these
   * agents are sent to the backend and will override any agents that the
   * outline stream emits, keeping the approved roster authoritative.
   */
  startOutlineGeneration: (config: MAICGenerationConfig, preSelectedAgents?: MAICAgent[]) => Promise<void>;
  updateOutline: (scenes: MAICOutlineScene[]) => void;
  startContentGeneration: (classroomId: string) => Promise<void>;
  startV2Generation: (config: MAICGenerationConfig, preSelectedAgents?: MAICAgent[]) => Promise<string | null>;
  /** T4 — re-run content + actions for a single outline scene id. Used
   *  by the sidebar "retry" button on failed tiles. Clears the failure
   *  flag on success, re-marks it on re-failure. */
  retryScene: (outlineId: string) => Promise<void>;
  cancel: () => void;
  reset: () => void;
}

export function useMAICGeneration(): UseMAICGenerationReturn {
  const [step, setStep] = useState<GenerationStep>('idle');
  const [phase, setPhase] = useState<GenerationPhase>('idle');
  const [currentSceneIdx, setCurrentSceneIdx] = useState(0);
  const [totalScenes, setTotalScenes] = useState(0);
  const [outline, setOutline] = useState<MAICOutline | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [isTabHidden, setIsTabHidden] = useState<boolean>(
    typeof document !== 'undefined' ? document.visibilityState === 'hidden' : false,
  );
  const [firstSceneReadyAt, setFirstSceneReadyAt] = useState<number | null>(null);

  // Mirror browser visibility into state. When the user returns we also
  // ping the activity timestamp so the session-idle logout doesn't fire on
  // next render. The content-generation loop is fully client-side, so the
  // generation keeps running while the tab is hidden — the only thing we
  // pause is the visible elapsed ticker.
  useEffect(() => {
    if (typeof document === 'undefined') return;
    const handler = () => {
      const hidden = document.visibilityState === 'hidden';
      setIsTabHidden(hidden);
      if (!hidden) setLastActivityTimestamp(Date.now());
    };
    document.addEventListener('visibilitychange', handler);
    return () => document.removeEventListener('visibilitychange', handler);
  }, []);

  const abortRef = useRef<AbortController | null>(null);
  const generationContextRef = useRef<MAICGenerationContextPayload>({});
  const { accessToken } = useAuthStore();
  const { setSlides, setAgents, setScenes, setSceneSlideBounds } = useMAICStageStore();

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const reset = useCallback(() => {
    cancel();
    setStep('idle');
    setPhase('idle');
    setCurrentSceneIdx(0);
    setTotalScenes(0);
    setOutline(null);
    setProgress(0);
    setError(null);
    setStartedAt(null);
    setFirstSceneReadyAt(null);
    generationContextRef.current = {};
  }, [cancel]);

  const startOutlineGeneration = useCallback(
    async (config: MAICGenerationConfig, preSelectedAgents?: MAICAgent[]) => {
      if (!accessToken) return;
      setStep('outlining');
      setPhase('outline');
      setError(null);
      setProgress(0);
      setStartedAt(Date.now());
      const generationContext = generationContextFromConfig(config);
      generationContextRef.current = generationContext;

      const controller = new AbortController();
      abortRef.current = controller;

      const partialOutline: Partial<MAICOutline> = {
        topic: config.topic,
        scenes: [],
        agents: preSelectedAgents ?? [],
        language: config.language,
        totalMinutes: 0,
      };

      await streamMAIC({
        url: '/api/v1/teacher/maic/generate/outlines/',
        body: {
          topic: config.topic,
          pdfText: config.pdfText,
          language: config.language,
          agentCount: config.agentCount,
          sceneCount: config.sceneCount,
          // Toggle from the wizard (default ON) — tells the sidecar / backend
          // to enrich the outline with web-search context before calling the LLM.
          enableWebSearch: config.enableWebSearch ?? false,
          // FULL-1 — grade-aware prompt knobs. Backend extractor in
          // apps/courses/maic_views.py:84-113 reads either snake_case or
          // camelCase, but we send canonical snake_case here so the network
          // payload matches the documented API. Omit empty values entirely
          // so the backend's "Generic" / no-grade defaults apply.
          ...generationContext,
          // When the wizard already picked a roster (WS-C), send it along so
          // the backend can reuse personality/voice mapping for outline prompts.
          ...(preSelectedAgents && preSelectedAgents.length > 0
            ? { agents: preSelectedAgents }
            : {}),
        },
        token: accessToken,
        signal: controller.signal,
        onEvent: (event: MAICSSEEvent) => {
          if (event.type === 'outline') {
            const data = event.data as MAICOutline;
            partialOutline.scenes = data.scenes || partialOutline.scenes;
            // Prefer the roster the user just approved in the wizard. If
            // there is no approved roster yet, fall back to whatever the
            // outline event emitted.
            partialOutline.agents =
              preSelectedAgents && preSelectedAgents.length > 0
                ? preSelectedAgents
                : data.agents || partialOutline.agents;
            partialOutline.totalMinutes = data.totalMinutes || 0;
            setOutline({ ...partialOutline } as MAICOutline);
          } else if (event.type === 'generation_progress') {
            setProgress((event.data as { progress: number }).progress || 0);
          } else if (event.type === 'error') {
            setError((event.data as { message: string }).message);
            setStep('error');
          }
        },
        onError: (err) => {
          setError(err.message);
          setStep('error');
        },
        onDone: () => {
          if (step !== 'error') {
            setStep('editing');
            setProgress(100);
          }
        },
      });
    },
    [accessToken, step]
  );

  const updateOutline = useCallback(
    (scenes: MAICOutlineScene[]) => {
      if (outline) {
        setOutline({ ...outline, scenes });
      }
    },
    [outline]
  );

  const startContentGeneration = useCallback(
    async (classroomId: string) => {
      if (!outline || !accessToken) return;
      setStep('generating');
      setPhase('content');
      setProgress(0);
      setError(null);
      setTotalScenes(outline.scenes.length);
      setCurrentSceneIdx(0);
      setFirstSceneReadyAt(null);

      // Fire-and-forget progress ping — stamps last_progress_at on the
      // server so MAICPlayerPage can render an honest progress bar and
      // detect stalled runs even if the browser tab later closes.
      const pingProgress = (patch: {
        phase?: 'outline' | 'content' | 'actions' | 'saving' | 'complete';
        phase_scene_index?: number;
        scenes_ready?: number;
      }) => {
        void maicApi.pingClassroomProgress(classroomId, patch).catch(() => {});
      };

      const generatedSlides: MAICSlide[] = [];
      const generatedScenes: MAICScene[] = [];
      const sceneSlideBounds: SceneSlideBounds[] = [];
      const agents: MAICAgent[] = outline.agents;
      const totalSteps = outline.scenes.length * 2; // content + actions per scene
      let currentSlideOffset = 0;

      // Stamp GENERATING status immediately so the MAICPlayerPage's
      // polled state shows the "Preparing Classroom" screen with the
      // correct copy + planned scene total. `config.sceneCount` was
      // stamped at classroom creation and serves as the denominator.
      // Fire-and-forget — a PATCH failure doesn't block generation.
      maicApi.updateClassroom(classroomId, {
        status: 'GENERATING',
      }).catch(() => {});

      // Lock: prevent idle timeout and keep session alive during generation
      setGenerationActive(true);
      const heartbeat = window.setInterval(() => {
        setLastActivityTimestamp(Date.now());
      }, 30_000);

      // T1.1 — generate scene 0 CONTENT then ACTIONS first, back to back,
      // so the first-scene-ready signal fires as early as possible. The
      // remaining scenes still follow the original content-all-then-
      // actions-all shape because the action prompt likes to reference
      // prior-scene content for context. Helpers below keep the code
      // readable without duplicating the inside-loop bookkeeping.

      const runContent = async (i: number): Promise<void> => {
        const outlineScene = outline.scenes[i];
        setCurrentSceneIdx(i);
        setProgress(Math.round(((i + 1) / totalSteps) * 100));
        setLastActivityTimestamp(Date.now());
        pingProgress({ phase: 'content', phase_scene_index: i + 1 });

        const res = await withRetry(() =>
          maicApi.generateSceneContent({
            scene: outlineScene,
            agents,
            language: outline.language,
            // CG-P0-9: pipe classroom + scene idx so the backend image
            // service has the storage context it needs to save Imagen
            // bytes to /media instead of returning a base64 data URL
            // that scrubSlideDataUrls then strips to empty.
            classroomId,
            sceneIdx: i,
            ...generationContextRef.current,
          }),
        );

        const sceneSlides: MAICSlide[] = res.data?.slides
          ? (res.data.slides as MAICSlide[])
          : res.data?.slide
            ? [res.data.slide as MAICSlide]
            : [];

        generatedSlides.push(...sceneSlides);

        if (sceneSlides.length > 0) {
          sceneSlideBounds.push({
            sceneIdx: i,
            startSlide: currentSlideOffset,
            endSlide: currentSlideOffset + sceneSlides.length - 1,
          });
          currentSlideOffset += sceneSlides.length;
        }

        const sceneType = mapOutlineTypeToSceneType(outlineScene.type);
        const primarySlide = sceneSlides[0];
        const scene: MAICScene = {
          id: outlineScene.id,
          type: sceneType,
          title: outlineScene.title,
          order: i + 1,
          content: buildSceneContent(sceneType, primarySlide, res.data, sceneSlides),
          actions: [],
          multiAgent: outlineScene.agentIds.length > 0
            ? { enabled: true, agentIds: outlineScene.agentIds }
            : undefined,
        };
        generatedScenes[i] = scene;

        // T1 — push PARTIAL state into the global store after each scene
        // finishes content. Stage.tsx reads from the same store so if
        // the user has already clicked "Open classroom now" (or they
        // never navigated and are still staring at the wizard), they
        // see the new scene land in real time rather than waiting for
        // the whole loop.
        const compactScenes = generatedScenes.filter(Boolean) as MAICScene[];
        setScenes(compactScenes);
        setSlides([...generatedSlides]);
        setSceneSlideBounds([...sceneSlideBounds]);

        maicApi.updateClassroom(classroomId, {
          scene_count: compactScenes.length,
        }).catch(() => {});
      };

      const runActions = async (i: number): Promise<void> => {
        const scene = generatedScenes[i];
        if (!scene) return;
        setCurrentSceneIdx(i);
        setProgress(Math.round(((outline.scenes.length + i + 1) / totalSteps) * 100));
        setLastActivityTimestamp(Date.now());
        pingProgress({ phase: 'actions', phase_scene_index: i + 1 });
        try {
          const actionsRes = await withRetry(() =>
            maicApi.generateSceneActions({
              scene: {
                id: scene.id,
                type: scene.type,
                title: scene.title,
                content: scene.content,
              },
              agents,
              language: outline.language,
              classroomId,
              ...generationContextRef.current,
            }),
          );
          if (actionsRes.data?.actions?.length) {
            scene.actions = actionsRes.data.actions;
          }
          // T1 — re-push scenes after actions land so Stage.tsx picks
          // up the fresh `actions` array. Without this, a mid-gen
          // navigation would show scenes whose content loads but whose
          // action lists stay empty until the next store write.
          const compactScenes = generatedScenes.filter(Boolean) as MAICScene[];
          setScenes(compactScenes);
          // Count scenes that have BOTH content and actions for the
          // authoritative "ready" count (mirrors the backend auto-
          // heartbeat logic in teacher_maic_classroom_update).
          const readyCount = generatedScenes.filter(
            (s) => s && s.actions && s.actions.length > 0,
          ).length;
          pingProgress({ scenes_ready: readyCount });
        } catch {
          scene.actions = buildFallbackActions(scene, agents);
        }
      };

      // T4 — per-scene failure tracking. `runContent` / `runActions`
      // throws on a bad LLM response or network error; we catch per
      // iteration, mark the outline id in the store, and keep the loop
      // going so ONE failed scene doesn't abort the whole pipeline.
      const stageStore = useMAICStageStore.getState();
      stageStore.clearAllOutlineFailures();
      const markFail = (idx: number) => {
        const id = outline.scenes[idx]?.id;
        if (id) useMAICStageStore.getState().markOutlineFailed(id);
      };
      const runContentSafe = async (i: number): Promise<void> => {
        try {
          await runContent(i);
          useMAICStageStore.getState().clearOutlineFailure(outline.scenes[i]?.id ?? '');
        } catch (err) {
          console.warn(`[MAIC] scene ${i} content generation failed`, err);
          markFail(i);
        }
      };
      const runActionsSafe = async (i: number): Promise<void> => {
        try {
          await runActions(i);
        } catch (err) {
          console.warn(`[MAIC] scene ${i} actions generation failed`, err);
          markFail(i);
        }
      };

      // CG-P0-4 (2026-04-25): persist the in-progress classroom snapshot to
      // the server after every scene so a navigation/tab-close mid-flow no
      // longer orphans the row on `status=GENERATING` with empty `content`.
      // See incidents/2026-04-25-classroom-generation-orphan.md.
      //
      // Scenes whose action-gen has not run yet are saved with deterministic
      // fallback actions (buildFallbackActions) so the partial classroom is
      // playable end-to-end even if the wizard never reaches the actions
      // loop. The next persistPartial() call after that scene's real actions
      // land overwrites the fallback with the real ones.
      const persistPartial = async (): Promise<void> => {
        const compactScenes = generatedScenes.filter(Boolean) as MAICScene[];
        if (compactScenes.length === 0) return;
        const playableScenes = compactScenes.map((s) =>
          s.actions && s.actions.length > 0
            ? s
            : { ...s, actions: buildFallbackActions(s, agents) },
        );
        try {
          await maicApi.updateClassroom(classroomId, {
            scene_count: compactScenes.length,
            content: {
              slides: scrubSlideDataUrls(generatedSlides),
              agents,
              scenes: playableScenes,
              sceneSlideBounds,
            },
          });
        } catch (err) {
          // Best-effort — the next persistPartial() will retry with even
          // more data. Don't abort the wizard on a transient PATCH failure.
          console.warn('[MAIC] partial content persist failed (will retry next scene)', err);
        }
      };

      try {
        // ── Scene 0 end-to-end: content → actions → mark first-scene-ready ──
        await runContentSafe(0);
        await persistPartial();
        setPhase('actions');
        await runActionsSafe(0);
        await persistPartial();
        setFirstSceneReadyAt(Date.now());

        // ── Remaining scenes: content-all-then-actions-all (original order) ──
        setPhase('content');
        for (let i = 1; i < outline.scenes.length; i++) {
          await runContentSafe(i);
          await persistPartial();
        }
        setPhase('actions');
        for (let i = 1; i < outline.scenes.length; i++) {
          await runActionsSafe(i);
          await persistPartial();
        }

        // ── Phase 3: Save ──
        setPhase('saving');
        pingProgress({ phase: 'saving' });
        await saveClassroom({
          id: classroomId,
          title: outline.topic,
          slides: generatedSlides,
          scenes: generatedScenes,
          outlines: outline.scenes,
          agents,
          chatHistory: [],
          config: {},
          sceneSlideBounds,
          syncedAt: Date.now(),
        });

        // Final Django PATCH: flips status to READY and stamps the canonical
        // closing snapshot. Per-scene persistPartial() calls above already
        // saved the content incrementally; this is the closing marker.
        await withRetry(() =>
          maicApi.updateClassroom(classroomId, {
            status: 'READY',
            scene_count: generatedScenes.length,
            estimated_minutes: outline.totalMinutes,
            config: { agents, language: outline.language },
            content: {
              slides: scrubSlideDataUrls(generatedSlides),
              agents,
              scenes: generatedScenes,
              sceneSlideBounds,
            },
          }),
        );

        setSlides(generatedSlides);
        setScenes(generatedScenes);
        setAgents(agents);
        setSceneSlideBounds(sceneSlideBounds);
        setStep('complete');
        setProgress(100);
        pingProgress({
          phase: 'complete',
          scenes_ready: generatedScenes.length,
        });
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Generation failed';
        setError(message);
        setStep('error');

        await maicApi.updateClassroom(classroomId, {
          status: 'FAILED',
          error_message: message,
        }).catch(() => {});
      } finally {
        window.clearInterval(heartbeat);
        setGenerationActive(false);
      }
    },
    [outline, accessToken, setSlides, setScenes, setAgents, setSceneSlideBounds]
  );

  const startV2Generation = useCallback(
    async (config: MAICGenerationConfig, preSelectedAgents: MAICAgent[] = []) => {
      if (!accessToken) return null;

      const targetScenes = Math.max(1, config.sceneCount || 1);
      const controller = new AbortController();
      abortRef.current = controller;
      generationContextRef.current = generationContextFromConfig(config);

      setStep('generating');
      setPhase('outline');
      setCurrentSceneIdx(0);
      setTotalScenes(targetScenes);
      setOutline(pendingOutlineFromConfig(config, preSelectedAgents));
      setProgress(3);
      setError(null);
      setStartedAt(Date.now());
      setFirstSceneReadyAt(null);
      setAgents(preSelectedAgents);

      setGenerationActive(true);
      const heartbeat = window.setInterval(() => {
        setLastActivityTimestamp(Date.now());
      }, 30_000);

      try {
        const createRes = await maicApi.generateV2Classroom({
          topic: config.topic,
          contentTitle: config.topic,
          language: config.language,
          level: config.gradeLevel || 'intermediate',
          agentCount: preSelectedAgents.length || config.agentCount,
          sceneCount: targetScenes,
          specifications: buildV2Specifications(config),
          courseId: config.courseId,
          gradeLevel: config.gradeLevel,
          subject: config.subject,
          syllabusBoard: config.syllabusBoard,
          classGuide: config.classGuide,
          // Chunk 3a typed pedagogy targets — only included when populated so
          // omission lands an origin/main-identical request payload.
          learningObjective: config.learningObjective,
          misconceptions: config.misconceptions?.length
            ? config.misconceptions
            : undefined,
          successCriteria: config.successCriteria?.length
            ? config.successCriteria
            : undefined,
          pblBrief: config.pblBrief,
          pdfText: config.pdfText,
          researchContext: config.enableWebSearch ? config.webSearchContext : undefined,
          agents: preSelectedAgents,
          enablePBL: true,
          enableImageGeneration: Boolean(config.enableImages),
        });

        const jobId = createRes.data.job_id;
        let lastMessage = 'Queued';
        let consecutivePollErrors = 0;

        while (!controller.signal.aborted) {
          await waitForPollInterval(controller.signal);
          let jobRes: Awaited<ReturnType<typeof maicApi.getV2GenerationJob>>;
          try {
            jobRes = await maicApi.getV2GenerationJob(jobId);
            consecutivePollErrors = 0;
          } catch (err) {
            consecutivePollErrors += 1;
            if (consecutivePollErrors < V2_JOB_MAX_CONSECUTIVE_POLL_ERRORS) {
              lastMessage = 'Reconnecting to generation progress...';
              continue;
            }
            throw err;
          }
          const job = jobRes.data;
          const jobProgress = job.progress || {};
          const stage = Number(job.step ?? jobProgress.stage ?? 0);
          const completed = Number(jobProgress.completed ?? job.scenesGenerated ?? 0);
          const total = Number(jobProgress.total ?? job.totalScenes ?? targetScenes);
          const normalizedTotal = Number.isFinite(total) && total > 0 ? total : targetScenes;
          lastMessage = job.message || jobProgress.message || lastMessage;

          setTotalScenes(normalizedTotal);
          if (stage <= 1) {
            setPhase('outline');
            setCurrentSceneIdx(0);
            setProgress(stage === 1 ? 18 : 6);
          } else if (stage === 2) {
            setPhase('content');
            setCurrentSceneIdx(Math.min(Math.max(completed - 1, 0), normalizedTotal - 1));
            const sceneRatio = normalizedTotal > 0 ? completed / normalizedTotal : 0;
            setProgress(Math.min(94, Math.max(25, Math.round(25 + sceneRatio * 65))));
          } else {
            setPhase('saving');
            setCurrentSceneIdx(Math.max(normalizedTotal - 1, 0));
            setProgress(96);
          }

          if (job.status === 'failed') {
            throw new Error(generationErrorMessage(job.error || lastMessage || 'Generation failed'));
          }

          if (job.status === 'succeeded' || job.done) {
            const classroomId =
              v2ClassroomId(job.result) ||
              v2ClassroomId((await maicApi.getV2GenerationJob(jobId, { full: false })).data.result);
            if (!classroomId) {
              throw new Error('Generation completed but no classroom was materialized.');
            }
            setPhase('saving');
            setCurrentSceneIdx(Math.max(normalizedTotal - 1, 0));
            setProgress(100);
            setStep('complete');
            return classroomId;
          }
        }

        throw new DOMException('Generation cancelled', 'AbortError');
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setStep('idle');
          setPhase('idle');
          return null;
        }
        const message = generationErrorFromException(err);
        setError(message);
        setStep('error');
        return null;
      } finally {
        window.clearInterval(heartbeat);
        setGenerationActive(false);
        if (abortRef.current === controller) {
          abortRef.current = null;
        }
      }
    },
    [accessToken, setAgents],
  );

  // T4 — retry a single scene's action generation after it failed in
  // the main loop. Scoped to re-running actions (not content) because
  // content failures are rare and rebuilding flat slides + bounds on
  // partial retry is a different kind of bug-farm. If actions succeed,
  // we replace the scene's `actions` array in the store and clear the
  // failure flag. On re-failure we re-mark it.
  const retryScene = useCallback(async (outlineId: string) => {
    if (!outline || !accessToken) return;
    const idx = outline.scenes.findIndex((s) => s.id === outlineId);
    if (idx < 0) return;
    const store = useMAICStageStore.getState();
    const scenes = [...store.scenes];
    const target = scenes.find((s) => s.id === outlineId);
    if (!target) {
      // Scene didn't get built at all (content failure). For now we
      // can't auto-recover partial slide bounds; surface the flag.
      store.markOutlineFailed(outlineId);
      return;
    }
    try {
      const actionsRes = await maicApi.generateSceneActions({
        scene: {
          id: target.id,
          type: target.type,
          title: target.title,
          content: target.content,
        },
        agents: outline.agents,
        language: outline.language,
        ...generationContextRef.current,
      });
      const fresh = { ...target, actions: actionsRes.data?.actions ?? [] };
      if (fresh.actions.length === 0) {
        fresh.actions = buildFallbackActions(fresh, outline.agents);
      }
      const nextScenes = scenes.map((s) => (s.id === outlineId ? fresh : s));
      store.setScenes(nextScenes);
      store.clearOutlineFailure(outlineId);
    } catch (err) {
      console.warn(`[MAIC] retryScene(${outlineId}) failed`, err);
      store.markOutlineFailed(outlineId);
    }
  }, [outline, accessToken]);

  return {
    step,
    phase,
    currentSceneIdx,
    totalScenes,
    outline,
    progress,
    error,
    startedAt,
    isTabHidden,
    firstSceneReadyAt,
    startOutlineGeneration,
    updateOutline,
    startContentGeneration,
    startV2Generation,
    retryScene,
    cancel,
    reset,
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/**
 * CG-P0-4 (2026-04-25): defensively scrub `data:` URLs from element `src`s
 * before any PATCH that ships slide payloads. Backend `_fill_image_urls`
 * already rejects data: at the ingress, and the SlideRenderer strips them at
 * read, but running the scrubber here keeps the PATCH body lean AND
 * guarantees the DB never sees a base64 image even if an LLM sneaks one in
 * via a code path the backend guard doesn't cover. Also keeps the PATCH
 * comfortably under DATA_UPLOAD_MAX_MEMORY_SIZE (50 MB).
 */
function scrubSlideDataUrls(slides: MAICSlide[]): MAICSlide[] {
  let strippedCount = 0;
  const out = slides.map((s) => ({
    ...s,
    elements: (s.elements || []).map((el) => {
      const src =
        typeof (el as { src?: string }).src === 'string'
          ? (el as { src: string }).src
          : '';
      if (src.startsWith('data:')) {
        strippedCount += 1;
        return { ...el, src: '' };
      }
      return el;
    }),
  }));
  // CG-P0-9: this scrubber should be a no-op now that the backend image
  // service has full storage context. If ANY data: URL gets stripped,
  // something regressed (likely Imagen fell back to `_bytes_to_data_url`
  // because tenant_id/classroom_id/scene_idx weren't piped through). Log
  // loudly so the regression is visible during local dev — production
  // ops can grep for the metric.
  if (strippedCount > 0 && typeof console !== 'undefined') {
    console.warn(
      `[MAIC] scrubSlideDataUrls stripped ${strippedCount} data: URL(s) — ` +
      `expected zero post-CG-P0-9. Backend storage context likely missing.`,
    );
  }
  return out;
}

/** Map outline scene types to playback scene types */
function mapOutlineTypeToSceneType(
  outlineType: MAICOutlineScene['type'],
): MAICSceneType {
  switch (outlineType) {
    case 'quiz':
      return 'quiz';
    case 'activity':
    case 'interactive':
      return 'interactive';
    default:
      return 'slide';
  }
}

/** Build the polymorphic scene content from generated data */
function buildSceneContent(
  sceneType: MAICSceneType,
  slide: MAICSlide | undefined,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  responseData: any,
  sceneSlides: MAICSlide[] = slide ? [slide] : [],
): MAICScene['content'] {
  if (sceneType === 'quiz' && responseData?.questions) {
    return {
      type: 'quiz',
      questions: responseData.questions,
    } as MAICQuizContent;
  }

  if (sceneType === 'interactive' && responseData?.html) {
    return {
      type: 'interactive',
      html: responseData.html,
      url: responseData.url,
    };
  }

  // Default: slide content
  return {
    type: 'slide',
    elements: slide?.elements || [],
    slides: sceneSlides,
    background: slide?.background,
    speakerScript: slide?.speakerScript,
    audioUrl: slide?.audioUrl,
  } as MAICSlideContent;
}

/**
 * Build fallback actions when the scene-actions endpoint is unavailable.
 *
 * Porting P5.2 — previously this emitted only speech + spotlight, which
 * degraded the classroom to a silent slide-show on action-gen failure
 * (one agent monologues the entire speakerScript without any visual
 * variety or pacing). We now emit a richer sequence:
 *
 *   speech(agent A — opener)
 *   spotlight(first element)
 *   pause(200ms)
 *   speech(agent B — follow-up, if available)
 *   highlight(second element)
 *   pause(300ms)
 *   speech(agent A — wrap)
 *
 * Still deterministic, but feels like a conversation rather than a
 * single voice reading a script. Uses agent roster for dialogue even
 * when the LLM couldn't script one.
 */
function buildFallbackActions(scene: MAICScene, agents: MAICAgent[]): MAICAction[] {
  const actions: MAICAction[] = [];

  if (scene.content.type !== 'slide') return actions;
  const slideContent = scene.content as MAICSlideContent;

  // Build a 2-agent speaker pair when we have at least two agents.
  const assignedIds = scene.multiAgent?.agentIds ?? [];
  const speakerA = assignedIds[0] || agents[0]?.id;
  const speakerB = assignedIds[1] || agents.find((a) => a.id !== speakerA)?.id || speakerA;
  if (!speakerA) return actions;

  const slides = slideContent.slides?.length
    ? slideContent.slides
    : [{
        id: `${scene.id}-fallback-slide`,
        title: scene.title,
        elements: slideContent.elements ?? [],
        speakerScript: slideContent.speakerScript,
      }];

  slides.forEach((slide, index) => {
    const elements = slide.elements ?? [];
    const firstEl = elements[0]?.id;
    const secondEl = elements[1]?.id;
    const speakerId = index % 2 === 0 ? speakerA : speakerB;
    const followUpId = speakerId === speakerA ? speakerB : speakerA;
    const script = slide.speakerScript?.trim() || `Let's examine ${slide.title || scene.title}.`;

    if (index > 0) {
      actions.push({ type: 'transition', slideIndex: index });
    }
    actions.push({ type: 'speech', agentId: speakerId, text: script });
    if (firstEl) {
      actions.push({ type: 'spotlight', elementId: firstEl, duration: 2500 });
      actions.push({ type: 'laser', elementId: firstEl, color: '#2563EB', duration: 1200 });
    }
    if (secondEl) {
      actions.push({ type: 'highlight', elementId: secondEl, color: '#DBEAFE' });
    }
    if (followUpId && followUpId !== speakerId && index < slides.length - 1) {
      actions.push({
        type: 'speech',
        agentId: followUpId,
        text: `That gives us the next anchor for ${slides[index + 1]?.title || scene.title}.`,
      });
    }
  });

  return actions;
}
