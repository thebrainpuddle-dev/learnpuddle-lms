// hooks/useMAICGeneration.ts — Orchestrates classroom generation flow

import { useState, useCallback, useRef } from 'react';
import { useAuthStore } from '../stores/authStore';
import { useMAICStageStore } from '../stores/maicStageStore';
import { streamMAIC } from '../lib/maicSSE';
import { saveClassroom } from '../lib/maicDb';
import { maicApi } from '../services/openmaicService';
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

  startOutlineGeneration: (config: MAICGenerationConfig) => Promise<void>;
  updateOutline: (scenes: MAICOutlineScene[]) => void;
  startContentGeneration: (classroomId: string) => Promise<void>;
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
  }, [cancel]);

  const startOutlineGeneration = useCallback(
    async (config: MAICGenerationConfig) => {
      if (!accessToken) return;
      setStep('outlining');
      setPhase('outline');
      setError(null);
      setProgress(0);

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
        url: '/api/v1/teacher/maic/generate/outlines/',
        body: {
          topic: config.topic,
          pdfText: config.pdfText,
          language: config.language,
          agentCount: config.agentCount,
          sceneCount: config.sceneCount,
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

      const generatedSlides: MAICSlide[] = [];
      const generatedScenes: MAICScene[] = [];
      const sceneSlideBounds: SceneSlideBounds[] = [];
      const agents: MAICAgent[] = outline.agents;
      const totalSteps = outline.scenes.length * 2; // content + actions per scene
      let currentSlideOffset = 0;

      try {
        // ── Phase 1: Generate slide content for each scene ──
        for (let i = 0; i < outline.scenes.length; i++) {
          const outlineScene = outline.scenes[i];
          setCurrentSceneIdx(i);
          setProgress(Math.round(((i + 1) / totalSteps) * 100));

          const res = await maicApi.generateSceneContent({
            scene: outlineScene,
            agents,
            language: outline.language,
          });

          // Support multi-slide response: `slides: [...]` array or legacy `slide: {...}`
          const sceneSlides: MAICSlide[] = res.data?.slides
            ? (res.data.slides as MAICSlide[])
            : res.data?.slide
              ? [res.data.slide as MAICSlide]
              : [];

          generatedSlides.push(...sceneSlides);

          // Build scene-to-slide bounds mapping
          sceneSlideBounds.push({
            sceneIdx: i,
            startSlide: currentSlideOffset,
            endSlide: currentSlideOffset + Math.max(sceneSlides.length - 1, 0),
          });
          currentSlideOffset += sceneSlides.length;

          // Map outline type to scene type
          const sceneType = mapOutlineTypeToSceneType(outlineScene.type);

          // Build MAICScene from the outline + generated content
          // For multi-slide, use the first slide as the primary content
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

        // ── Phase 2: Generate playback actions for each scene ──
        setPhase('actions');
        for (let i = 0; i < generatedScenes.length; i++) {
          const scene = generatedScenes[i];
          setCurrentSceneIdx(i);
          setProgress(Math.round(((outline.scenes.length + i + 1) / totalSteps) * 100));

          try {
            const actionsRes = await maicApi.generateSceneActions({
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
            // If action generation fails, build fallback actions from speaker script
            scene.actions = buildFallbackActions(scene, agents);
          }
        }

        // ── Phase 3: Save ──
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

        // Update Django record — include agents in config for chat fallback
        // Push full content so students can load it from the API
        await maicApi.updateClassroom(classroomId, {
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

        await maicApi.updateClassroom(classroomId, {
          status: 'FAILED',
          error_message: message,
        });
      }
    },
    [outline, accessToken, setSlides, setScenes, setAgents, setSceneSlideBounds]
  );

  return {
    step,
    phase,
    currentSceneIdx,
    totalScenes,
    outline,
    progress,
    error,
    startOutlineGeneration,
    updateOutline,
    startContentGeneration,
    cancel,
    reset,
  };
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Map outline scene types to playback scene types */
function mapOutlineTypeToSceneType(
  outlineType: MAICOutlineScene['type'],
): MAICSceneType {
  switch (outlineType) {
    case 'quiz':
      return 'quiz';
    case 'activity':
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
 * Creates a speech action from the speaker script + spotlight on first element.
 */
function buildFallbackActions(scene: MAICScene, agents: MAICAgent[]): MAICAction[] {
  const actions: MAICAction[] = [];

  if (scene.content.type === 'slide') {
    const slideContent = scene.content as MAICSlideContent;

    // Pick the first agent assigned to this scene, or the first agent overall
    const speakerId =
      scene.multiAgent?.agentIds[0] || agents[0]?.id;

    // Speech action from speaker script
    if (slideContent.speakerScript && speakerId) {
      actions.push({
        type: 'speech',
        agentId: speakerId,
        text: slideContent.speakerScript,
      });
    }

    // Spotlight the first element
    if (slideContent.elements.length > 0) {
      actions.push({
        type: 'spotlight',
        elementId: slideContent.elements[0].id,
        duration: 3000,
      });
    }
  }

  return actions;
}
