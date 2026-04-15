// hooks/useStudentMAICGeneration.ts — Student classroom generation with guardrails
//
// Same flow as useMAICGeneration but uses student API endpoints
// and adds a validation step before outline generation.

import { useState, useCallback, useRef } from 'react';
import { useAuthStore } from '../stores/authStore';
import { useMAICStageStore } from '../stores/maicStageStore';
import { streamMAIC } from '../lib/maicSSE';
import { saveClassroom } from '../lib/maicDb';
import { maicStudentApi } from '../services/openmaicService';
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

  validateAndStartOutline: (config: MAICGenerationConfig) => Promise<void>;
  updateOutline: (scenes: MAICOutlineScene[]) => void;
  startContentGeneration: (classroomId: string) => Promise<void>;
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
  }, [cancel]);

  // ── Step 1: Validate topic, then generate outline ──
  const validateAndStartOutline = useCallback(
    async (config: MAICGenerationConfig) => {
      if (!accessToken) return;
      setStep('validating');
      setPhase('validation');
      setError(null);
      setProgress(0);
      setGuardrailResult(null);

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
          return;
        }
      } catch (err) {
        // If validation endpoint fails, check for 422 guardrail rejection
        const axiosErr = err as { response?: { status: number; data?: { error?: string; guardrail?: GuardrailResult } } };
        if (axiosErr.response?.status === 422) {
          const guardrail = axiosErr.response.data?.guardrail;
          if (guardrail) setGuardrailResult(guardrail);
          setError(axiosErr.response.data?.error || 'Topic not approved.');
          setStep('error');
          return;
        }
        setError('Failed to validate topic. Please try again.');
        setStep('error');
        return;
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
        agents: [],
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
        },
        token: accessToken,
        signal: controller.signal,
        onEvent: (event: MAICSSEEvent) => {
          if (event.type === 'outline') {
            const data = event.data as MAICOutline;
            partialOutline.scenes = data.scenes || partialOutline.scenes;
            partialOutline.agents = data.agents || partialOutline.agents;
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

      try {
        // Phase 1: Generate slide content
        for (let i = 0; i < outline.scenes.length; i++) {
          const outlineScene = outline.scenes[i];
          setCurrentSceneIdx(i);
          setProgress(Math.round(((i + 1) / totalSteps) * 100));

          const res = await maicStudentApi.generateSceneContent({
            scene: outlineScene,
            agents,
            language: outline.language,
          });

          const sceneSlides: MAICSlide[] = res.data?.slides
            ? (res.data.slides as MAICSlide[])
            : res.data?.slide
              ? [res.data.slide as MAICSlide]
              : [];

          generatedSlides.push(...sceneSlides);

          sceneSlideBounds.push({
            sceneIdx: i,
            startSlide: currentSlideOffset,
            endSlide: currentSlideOffset + Math.max(sceneSlides.length - 1, 0),
          });
          currentSlideOffset += sceneSlides.length;

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

          generatedScenes.push(scene);
        }

        // Phase 2: Generate actions
        setPhase('actions');
        for (let i = 0; i < generatedScenes.length; i++) {
          const scene = generatedScenes[i];
          setCurrentSceneIdx(i);
          setProgress(Math.round(((outline.scenes.length + i + 1) / totalSteps) * 100));

          try {
            const actionsRes = await maicStudentApi.generateSceneActions({
              scene: {
                id: scene.id,
                type: scene.type,
                title: scene.title,
                content: scene.content,
              },
              agents,
              language: outline.language,
            });

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
          audioCache: {},
          config: {},
          sceneSlideBounds,
          syncedAt: Date.now(),
        });

        // Update Django record
        await maicStudentApi.updateClassroom(classroomId, {
          status: 'READY',
          scene_count: generatedScenes.length,
          estimated_minutes: outline.totalMinutes,
          config: { agents, language: outline.language },
          content: {
            slides: generatedSlides,
            scenes: generatedScenes,
            sceneSlideBounds,
          },
        });

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
      }
    },
    [outline, accessToken, setSlides, setScenes, setAgents, setSceneSlideBounds],
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
    validateAndStartOutline,
    updateOutline,
    startContentGeneration,
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
    background: slide?.background,
    speakerScript: slide?.speakerScript,
    audioUrl: slide?.audioUrl,
  } as MAICSlideContent;
}

function buildFallbackActions(scene: MAICScene, agents: MAICAgent[]): MAICAction[] {
  const actions: MAICAction[] = [];
  if (scene.content.type === 'slide') {
    const slideContent = scene.content as MAICSlideContent;
    const speakerId = scene.multiAgent?.agentIds[0] || agents[0]?.id;
    if (slideContent.speakerScript && speakerId) {
      actions.push({ type: 'speech', agentId: speakerId, text: slideContent.speakerScript });
    }
    if (slideContent.elements.length > 0) {
      actions.push({ type: 'spotlight', elementId: slideContent.elements[0].id, duration: 3000 });
    }
  }
  return actions;
}
