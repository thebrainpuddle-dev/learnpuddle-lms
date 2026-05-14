// hooks/useStudentMAICGeneration.ts — Student classroom generation with guardrails
//
// Same flow as useMAICGeneration but uses student API endpoints
// and adds a validation step before outline generation.

import { useState, useCallback, useEffect, useRef } from 'react';
import { useAuthStore } from '../stores/authStore';
import { useMAICStageStore } from '../stores/maicStageStore';
import { streamMAIC } from '../lib/maicSSE';
import { saveClassroom } from '../lib/maicDb';
import { maicStudentApi } from '../services/openmaicService';
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

function pendingOutlineFromConfig(
  config: MAICGenerationConfig,
  agents: MAICAgent[],
): MAICOutline {
  const total = Math.max(1, Math.min(config.sceneCount || 1, 8));
  const agentIds = agents.map((agent) => agent.id);
  return {
    topic: config.topic,
    language: config.language,
    agents,
    totalMinutes: total * 2,
    scenes: Array.from({ length: total }, (_, index) => ({
      id: `student-v2-pending-${index + 1}`,
      title: `Scene ${index + 1}`,
      description: 'Prepared by the v2 PBL graph pipeline.',
      type: 'lecture',
      estimatedMinutes: 2,
      agentIds,
    })),
  };
}

function buildStudentV2Specifications(config: MAICGenerationConfig): string {
  return [
    'Create a production-ready student self-study AI classroom, not a static deck.',
    `Target exactly ${Math.min(config.sceneCount || 1, 8)} scenes with a coherent concept-to-practice arc.`,
    'Keep the classroom private to the student creator and suitable for independent revision.',
    'Use agents as collaborative peers/coaches who ask questions, challenge misconceptions, and hand off clearly.',
    'Include one meaningful PBL/activity or issue-board moment when the topic benefits from doing.',
    'Slides must be concise visual aids; spoken detail belongs in agent actions.',
    'Choreograph spotlight/laser/discussion handovers so audio, visual focus, and agent turns stay synchronized; point first, then speak.',
  ].join('\n');
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

function v2ClassroomId(
  result: Awaited<ReturnType<typeof maicStudentApi.getV2GenerationJob>>['data']['result'],
): string | null {
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
    return 'AI Classroom v2 is disabled for this deployment. Ask an admin to enable the backend flag before creating live classrooms.';
  }
  if (lower.includes('maic v2') && lower.includes('not enabled')) {
    return 'AI Classroom v2 is not enabled for this school. Ask an admin to enable it before creating live classrooms.';
  }
  if (lower.includes('ollama') && lower.includes('timed out')) {
    return 'The AI provider took too long while preparing the classroom. Try again, or switch this school to a faster production model.';
  }
  if (lower.includes('no classroom was materialized')) {
    return 'Generation finished but the classroom was not saved. Please try again; if it repeats, check the generation worker logs.';
  }
  if (lower.includes('network error') || lower.includes('failed to fetch')) {
    return 'Lost connection while checking generation progress. The classroom may still be running; refresh the page or check My Classrooms.';
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

  if (serverMessage) return generationErrorMessage(serverMessage);
  if (response?.status === 403) return generationErrorMessage('MAIC v2 not enabled');
  return generationErrorMessage(err instanceof Error ? err.message : 'Generation failed');
}

export type StudentGenerationStep = 'idle' | 'validating' | 'outlining' | 'editing' | 'generating' | 'complete' | 'error';
export type StudentGenerationPhase = 'idle' | 'validation' | 'outline' | 'content' | 'actions' | 'saving';

interface GuardrailResult {
  allowed: boolean;
  is_educational: boolean;
  subject_area: string;
  confidence: number;
  reason: string;
}

interface UseStudentMAICGenerationReturn {
  step: StudentGenerationStep;
  phase: StudentGenerationPhase;
  currentSceneIdx: number;
  totalScenes: number;
  outline: MAICOutline | null;
  progress: number;
  error: string | null;
  guardrailResult: GuardrailResult | null;
  /** ms timestamp when generation started; null until first start. */
  startedAt: number | null;
  /** Tab visibility mirror — paired with `startedAt` to drive the
   *  honest elapsed-timer UI in GenerationVisualizer. */
  isTabHidden: boolean;

  /**
   * Validate the topic through guardrails, then generate the outline.
   * Pass `preSelectedAgents` to send the wizard-approved roster to the
   * backend and override any agents the outline stream emits.
   */
  validateAndStartOutline: (config: MAICGenerationConfig, preSelectedAgents?: MAICAgent[]) => Promise<{ rejected: boolean }>;
  updateOutline: (scenes: MAICOutlineScene[]) => void;
  startContentGeneration: (classroomId: string) => Promise<void>;
  startV2Generation: (
    config: MAICGenerationConfig,
    preSelectedAgents?: MAICAgent[],
  ) => Promise<{ classroomId: string | null; rejected: boolean }>;
  cancel: () => void;
  reset: () => void;
}

export function useStudentMAICGeneration(): UseStudentMAICGenerationReturn {
  const [step, setStep] = useState<StudentGenerationStep>('idle');
  const [phase, setPhase] = useState<StudentGenerationPhase>('idle');
  const [currentSceneIdx, setCurrentSceneIdx] = useState(0);
  const [totalScenes, setTotalScenes] = useState(0);
  const [outline, setOutline] = useState<MAICOutline | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [guardrailResult, setGuardrailResult] = useState<GuardrailResult | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [isTabHidden, setIsTabHidden] = useState<boolean>(
    typeof document !== 'undefined' ? document.visibilityState === 'hidden' : false,
  );

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
    setGuardrailResult(null);
    setStartedAt(null);
  }, [cancel]);

  // ── Step 1: Validate topic, then generate outline ──
  const validateAndStartOutline = useCallback(
    async (config: MAICGenerationConfig, preSelectedAgents?: MAICAgent[]): Promise<{ rejected: boolean }> => {
      if (!accessToken) return { rejected: false };
      setStep('validating');
      setPhase('validation');
      setError(null);
      setProgress(0);
      setGuardrailResult(null);
      setStartedAt(Date.now());

      // Validate topic/PDF through guardrails
      try {
        const valRes = await maicStudentApi.validateTopic({
          topic: config.topic,
          pdfText: config.pdfText,
        });
        const validation = valRes.data;
        setGuardrailResult(validation);

        if (!validation.allowed) {
          setError(validation.reason || 'This topic was not approved. Please enter an educational topic.');
          setStep('error');
          return { rejected: true };
        }
      } catch (err) {
        // If validation endpoint fails, check for 422 guardrail rejection
        const axiosErr = err as { response?: { status: number; data?: { error?: string; guardrail?: GuardrailResult } } };
        if (axiosErr.response?.status === 422) {
          const guardrail = axiosErr.response.data?.guardrail;
          if (guardrail) setGuardrailResult(guardrail);
          setError(axiosErr.response.data?.error || 'Topic not approved.');
          setStep('error');
          return { rejected: true };
        }
        setError('Failed to validate topic. Please try again.');
        setStep('error');
        return { rejected: true };
      }

      // Validation passed — proceed with outline generation
      setStep('outlining');
      setPhase('outline');
      setProgress(10);

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
        url: '/api/v1/student/maic/generate/outlines/',
        body: {
          topic: config.topic,
          pdfText: config.pdfText,
          language: config.language,
          agentCount: Math.min(config.agentCount, 4),   // Student cap
          sceneCount: Math.min(config.sceneCount, 8),    // Student cap
          enableWebSearch: config.enableWebSearch ?? false,
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
            // Prefer the wizard-approved roster when present.
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
      return { rejected: false };
    },
    [accessToken, step],
  );

  const updateOutline = useCallback(
    (scenes: MAICOutlineScene[]) => {
      if (outline) {
        setOutline({ ...outline, scenes });
      }
    },
    [outline],
  );

  // ── Step 2: Generate content for all scenes ──
  const startContentGeneration = useCallback(
    async (classroomId: string) => {
      if (!outline || !accessToken) return;
      setStep('generating');
      setPhase('content');
      setProgress(0);
      setError(null);
      setTotalScenes(outline.scenes.length);
      setCurrentSceneIdx(0);

      const generatedSlides: MAICSlide[] = [];
      const generatedScenes: MAICScene[] = [];
      const sceneSlideBounds: SceneSlideBounds[] = [];
      const agents: MAICAgent[] = outline.agents;
      const totalSteps = outline.scenes.length * 2;
      let currentSlideOffset = 0;

      // Stamp GENERATING status immediately so MAICPlayerPage's polled
      // "Preparing Classroom" screen shows the correct copy right away.
      // `config.sceneCount` is the denominator for the progress bar.
      maicStudentApi.updateClassroom(classroomId, {
        status: 'GENERATING',
      }).catch(() => {});

      // Lock: prevent idle timeout and keep session alive during generation
      setGenerationActive(true);
      const heartbeat = window.setInterval(() => {
        setLastActivityTimestamp(Date.now());
      }, 30_000);

      try {
        // Phase 1: Generate slide content
        for (let i = 0; i < outline.scenes.length; i++) {
          const outlineScene = outline.scenes[i];
          setCurrentSceneIdx(i);
          setProgress(Math.round(((i + 1) / totalSteps) * 100));
          setLastActivityTimestamp(Date.now());

          const res = await withRetry(() =>
            maicStudentApi.generateSceneContent({
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

          // Only push bounds for scenes that actually generated slides.
          // Zero-slide scenes (e.g., quiz scenes returning `questions`)
          // would otherwise claim the next scene's first slide index,
          // producing duplicate thumbnails. See useMAICGeneration.ts.
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

          generatedScenes.push(scene);

          // Fire-and-forget scene_count increment so MAICPlayerPage's
          // progress bar advances in real time instead of jumping from
          // 0 to N at the end. A failed PATCH is harmless; the next
          // iteration's PATCH will catch up.
          maicStudentApi.updateClassroom(classroomId, {
            scene_count: generatedScenes.length,
          }).catch(() => {});
        }

        // Phase 2: Generate actions
        setPhase('actions');
        for (let i = 0; i < generatedScenes.length; i++) {
          const scene = generatedScenes[i];
          setCurrentSceneIdx(i);
          setProgress(Math.round(((outline.scenes.length + i + 1) / totalSteps) * 100));
          setLastActivityTimestamp(Date.now());

          try {
            const actionsRes = await withRetry(() =>
              maicStudentApi.generateSceneActions({
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
          } catch {
            scene.actions = buildFallbackActions(scene, agents);
          }
        }

        // Phase 3: Save
        setPhase('saving');
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

        // Update Django record
        await withRetry(() =>
          maicStudentApi.updateClassroom(classroomId, {
            status: 'READY',
            scene_count: generatedScenes.length,
            estimated_minutes: outline.totalMinutes,
            config: { agents, language: outline.language },
            content: {
              slides: generatedSlides,
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
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Generation failed';
        setError(message);
        setStep('error');

        await maicStudentApi.updateClassroom(classroomId, {
          status: 'FAILED',
          error_message: message,
        }).catch(() => {});
      } finally {
        window.clearInterval(heartbeat);
        setGenerationActive(false);
      }
    },
    [outline, accessToken, setSlides, setScenes, setAgents, setSceneSlideBounds],
  );

  const startV2Generation = useCallback(
    async (
      config: MAICGenerationConfig,
      preSelectedAgents: MAICAgent[] = [],
    ): Promise<{ classroomId: string | null; rejected: boolean }> => {
      if (!accessToken) return { classroomId: null, rejected: false };

      setStep('validating');
      setPhase('validation');
      setError(null);
      setProgress(0);
      setGuardrailResult(null);
      setStartedAt(Date.now());

      try {
        const valRes = await maicStudentApi.validateTopic({
          topic: config.topic,
          pdfText: config.pdfText,
        });
        const validation = valRes.data;
        setGuardrailResult(validation);
        if (!validation.allowed) {
          setError(validation.reason || 'This topic was not approved. Please enter an educational topic.');
          setStep('error');
          return { classroomId: null, rejected: true };
        }
      } catch (err) {
        const axiosErr = err as {
          response?: { status: number; data?: { error?: string; guardrail?: GuardrailResult } };
        };
        if (axiosErr.response?.status === 422) {
          const guardrail = axiosErr.response.data?.guardrail;
          if (guardrail) setGuardrailResult(guardrail);
          setError(axiosErr.response.data?.error || 'Topic not approved.');
          setStep('error');
          return { classroomId: null, rejected: true };
        }
        setError('Failed to validate topic. Please try again.');
        setStep('error');
        return { classroomId: null, rejected: true };
      }

      const targetScenes = Math.max(1, Math.min(config.sceneCount || 1, 8));
      const controller = new AbortController();
      abortRef.current = controller;

      setStep('generating');
      setPhase('outline');
      setCurrentSceneIdx(0);
      setTotalScenes(targetScenes);
      setOutline(pendingOutlineFromConfig(config, preSelectedAgents));
      setProgress(3);
      setAgents(preSelectedAgents);

      setGenerationActive(true);
      const heartbeat = window.setInterval(() => {
        setLastActivityTimestamp(Date.now());
      }, 30_000);

      try {
        const createRes = await maicStudentApi.generateV2Classroom({
          topic: config.topic,
          contentTitle: config.topic,
          language: config.language,
          level: 'student self-study',
          agentCount: Math.min(preSelectedAgents.length || config.agentCount, 4),
          sceneCount: targetScenes,
          specifications: buildStudentV2Specifications(config),
          pdfText: config.pdfText,
          researchContext: config.enableWebSearch ? config.webSearchContext : undefined,
          agents: preSelectedAgents,
          enablePBL: true,
          enableImageGeneration: Boolean(config.enableImages),
          isPublic: false,
        });

        const jobId = createRes.data.job_id;
        let lastMessage = 'Queued';
        let consecutivePollErrors = 0;

        while (!controller.signal.aborted) {
          await waitForPollInterval(controller.signal);
          let jobRes: Awaited<ReturnType<typeof maicStudentApi.getV2GenerationJob>>;
          try {
            jobRes = await maicStudentApi.getV2GenerationJob(jobId);
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
              v2ClassroomId((await maicStudentApi.getV2GenerationJob(jobId, { full: false })).data.result);
            if (!classroomId) {
              throw new Error('Generation completed but no classroom was materialized.');
            }
            setPhase('saving');
            setCurrentSceneIdx(Math.max(normalizedTotal - 1, 0));
            setProgress(100);
            setStep('complete');
            return { classroomId, rejected: false };
          }
        }

        throw new DOMException('Generation cancelled', 'AbortError');
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setStep('idle');
          setPhase('idle');
          return { classroomId: null, rejected: false };
        }
        setError(generationErrorFromException(err));
        setStep('error');
        return { classroomId: null, rejected: false };
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

  return {
    step,
    phase,
    currentSceneIdx,
    totalScenes,
    outline,
    progress,
    error,
    guardrailResult,
    startedAt,
    isTabHidden,
    validateAndStartOutline,
    updateOutline,
    startContentGeneration,
    startV2Generation,
    cancel,
    reset,
  };
}

// ─── Helpers (same as useMAICGeneration) ───────────────────────────────────

function mapOutlineTypeToSceneType(outlineType: MAICOutlineScene['type']): MAICSceneType {
  switch (outlineType) {
    case 'quiz': return 'quiz';
    case 'activity': return 'interactive';
    default: return 'slide';
  }
}

function buildSceneContent(
  sceneType: MAICSceneType,
  slide: MAICSlide | undefined,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  responseData: any,
  sceneSlides: MAICSlide[] = [],
): MAICScene['content'] {
  if (sceneType === 'quiz' && responseData?.questions) {
    return { type: 'quiz', questions: responseData.questions } as MAICQuizContent;
  }
  if (sceneType === 'interactive' && responseData?.html) {
    return { type: 'interactive', html: responseData.html, url: responseData.url };
  }
  return {
    type: 'slide',
    elements: slide?.elements || [],
    slides: sceneSlides,
    background: slide?.background,
    speakerScript: slide?.speakerScript,
    audioUrl: slide?.audioUrl,
  } as MAICSlideContent;
}

function buildFallbackActions(scene: MAICScene, agents: MAICAgent[]): MAICAction[] {
  const actions: MAICAction[] = [];
  if (scene.content.type === 'slide') {
    const slideContent = scene.content as MAICSlideContent;
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
      const speakerId = index % 2 === 0 ? speakerA : speakerB;
      const elements = slide.elements ?? [];
      const script = slide.speakerScript?.trim() || `Let's examine ${slide.title || scene.title}.`;
      if (index > 0) {
        actions.push({ type: 'transition', slideIndex: index });
      }
      actions.push({ type: 'speech', agentId: speakerId, text: script });
      if (elements[0]?.id) {
        actions.push({ type: 'spotlight', elementId: elements[0].id, duration: 2500 });
        actions.push({ type: 'laser', elementId: elements[0].id, color: '#2563EB', duration: 1200 });
      }
      if (elements[1]?.id) {
        actions.push({ type: 'highlight', elementId: elements[1].id, color: '#DBEAFE' });
      }
    });
  }
  return actions;
}
