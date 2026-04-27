// hooks/useMAICGeneration.ts — Orchestrates classroom generation flow

import { useState, useCallback, useEffect, useRef } from 'react';
import { useAuthStore } from '../stores/authStore';
import { useMAICStageStore } from '../stores/maicStageStore';
import { streamMAIC } from '../lib/maicSSE';
import { saveClassroom } from '../lib/maicDb';
import { maicApi } from '../services/openmaicService';
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
  }, [cancel]);

  const startOutlineGeneration = useCallback(
    async (config: MAICGenerationConfig, preSelectedAgents?: MAICAgent[]) => {
      if (!accessToken) return;
      setStep('outlining');
      setPhase('outline');
      setError(null);
      setProgress(0);
      setStartedAt(Date.now());

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
          ...(config.gradeLevel?.trim() ? { grade_level: config.gradeLevel.trim() } : {}),
          ...(config.subject?.trim() ? { subject: config.subject.trim() } : {}),
          ...(config.syllabusBoard?.trim() ? { syllabus_board: config.syllabusBoard.trim() } : {}),
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
          content: buildSceneContent(sceneType, primarySlide, res.data),
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
  return slides.map((s) => ({
    ...s,
    elements: (s.elements || []).map((el) => {
      const src =
        typeof (el as { src?: string }).src === 'string'
          ? (el as { src: string }).src
          : '';
      if (src.startsWith('data:')) {
        return { ...el, src: '' };
      }
      return el;
    }),
  }));
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

  const script = slideContent.speakerScript?.trim() ?? '';
  const elements = slideContent.elements ?? [];
  const firstEl = elements[0]?.id;
  const secondEl = elements[1]?.id;

  // Split the speakerScript into at most 3 chunks on sentence punctuation
  // so each agent gets a bite rather than A monologuing the whole thing.
  const chunks = script
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean);
  const partA = chunks.slice(0, Math.max(1, Math.ceil(chunks.length / 3))).join(' ');
  const partB = chunks.slice(partA ? 1 : 0, Math.max(2, Math.ceil((chunks.length * 2) / 3))).join(' ');
  const partC = chunks.slice(Math.max(2, Math.ceil((chunks.length * 2) / 3))).join(' ');

  if (partA) {
    actions.push({ type: 'speech', agentId: speakerA, text: partA });
  }
  if (firstEl) {
    actions.push({ type: 'spotlight', elementId: firstEl, duration: 2500 });
  }
  actions.push({ type: 'pause', duration: 200 });
  if (partB && speakerB) {
    actions.push({ type: 'speech', agentId: speakerB, text: partB });
  }
  if (secondEl) {
    actions.push({ type: 'highlight', elementId: secondEl, color: '#DBEAFE' });
    actions.push({ type: 'pause', duration: 300 });
  }
  if (partC) {
    actions.push({ type: 'speech', agentId: speakerA, text: partC });
  } else if (!partB && !partC && partA && speakerB) {
    // Short scripts — we only got partA. Add a closing acknowledgment
    // from the second speaker so the scene ends on a hand-off beat
    // rather than a single line.
    actions.push({
      type: 'speech',
      agentId: speakerB,
      text: 'Good framing — let\u2019s move on.',
    });
  }

  return actions;
}
