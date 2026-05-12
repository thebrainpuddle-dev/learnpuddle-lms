// src/components/maic/SceneRenderer.tsx
//
// Routes between different scene types (slide, quiz, interactive, pbl)
// based on scene.type. This is the main entry point for rendering any
// MAIC scene in the stage viewport.
//
// For slide-type scenes, the global slides[] array and currentSlideIndex
// from the store determine which slide to render, enabling multi-slide
// scene support.

import React, { useMemo } from 'react';
import { SlideRenderer } from './SlideRenderer';
import { QuizRenderer } from './QuizRenderer';
import { InteractiveRenderer } from './InteractiveRenderer';
import { PBLRenderer } from './PBLRenderer';
import { useMAICStageStore } from '../../stores/maicStageStore';
import type {
  MAICScene,
  MAICSlideContent,
  MAICQuizContent,
  MAICInteractiveContent,
  MAICPBLContent,
} from '../../types/maic-scenes';
import type { MAICRole } from '../../lib/maic/endpoints';
import { AlertTriangle } from 'lucide-react';

interface SceneRendererProps {
  scene: MAICScene;
  mode?: 'autonomous' | 'playback';
  /** Which portal rendered this scene. Forwarded to PBLRenderer so student
   *  PBL chat hits the student endpoint. Defaults to 'teacher' for legacy callers. */
  role?: MAICRole;
  /**
   * CG-P0-3: forwarded from the classroom detail response. When true the
   * Celery image-fill task is still running; SlideRenderer shows a
   * "fetching image…" skeleton instead of an immediate Unsplash fallback.
   */
  imagesPending?: boolean;
  /**
   * MAIC-608: callback for widget iframe events. Forwarded to
   * InteractiveRenderer when scene.type === 'interactive'. The
   * Stage-level owner (typically the WS hook holder) wires this to
   * `channel.send({action:'widget_event', ...})` so student
   * interactions reach the backend's pendingWidgetEvents buffer
   * (MAIC-603). When absent, no listener is attached — read-only
   * playback contexts pay zero overhead.
   */
  onWidgetEvent?: (
    sceneId: string,
    event: string,
    payload: Record<string, unknown>,
  ) => void;
}

export const SceneRenderer = React.memo<SceneRendererProps>(function SceneRenderer({
  scene,
  mode = 'autonomous',
  role,
  imagesPending,
  onWidgetEvent,
}) {
  const content = scene.content;
  const slides = useMAICStageStore((s) => s.slides);
  const currentSlideIndex = useMAICStageStore((s) => s.currentSlideIndex);
  // F2 (P0): scene index drives the per-element_key suffix the SlideRenderer
  // consumes. Read the live value from the store so we don't have to thread
  // it as a prop through every caller.
  const currentSceneIndex = useMAICStageStore((s) => s.currentSceneIndex);
  const totalSlides = slides.length;

  const rendered = useMemo(() => {
    switch (content.type) {
      case 'slide': {
        // Multi-slide support: use the current slide from the global slides
        // array when available, falling back to building a slide from the
        // scene content for single-slide or legacy scenes.
        const currentSlide = slides[currentSlideIndex];

        if (currentSlide) {
          return (
            <SlideRenderer
              slide={currentSlide}
              slideNumber={currentSlideIndex + 1}
              totalSlides={totalSlides}
              imagesPending={imagesPending}
              sceneIndex={currentSceneIndex}
              slideIndex={currentSlideIndex}
            />
          );
        }

        // Fallback: construct a slide from the scene's slide content
        const slideContent = content as MAICSlideContent;
        return (
          <SlideRenderer
            slide={{
              id: scene.id,
              title: scene.title,
              elements: slideContent.elements,
              background: slideContent.background,
              speakerScript: slideContent.speakerScript,
              audioUrl: slideContent.audioUrl,
            }}
            imagesPending={imagesPending}
            sceneIndex={currentSceneIndex}
            slideIndex={currentSlideIndex}
          />
        );
      }

      case 'quiz': {
        const quizContent = content as MAICQuizContent;
        return (
          <QuizRenderer questions={quizContent.questions} />
        );
      }

      case 'interactive': {
        const interactiveContent = content as MAICInteractiveContent;
        // MAIC-608: bind sceneId into the uplink so the parent's
        // widget_event handler doesn't have to re-derive it. Closure
        // captures scene.id; the callback identity is stable per
        // scene render which is fine for InteractiveRenderer's
        // useEffect dependency.
        const handleWidgetEvent = onWidgetEvent
          ? (event: string, payload: Record<string, unknown>) =>
              onWidgetEvent(scene.id, event, payload)
          : undefined;
        return (
          <InteractiveRenderer
            html={interactiveContent.html}
            url={interactiveContent.url}
            sceneId={scene.id}
            widgetConfig={interactiveContent.widgetConfig}
            onWidgetEvent={handleWidgetEvent}
          />
        );
      }

      case 'pbl': {
        const pblContent = content as MAICPBLContent;
        return (
          <PBLRenderer
            content={pblContent}
            sceneId={scene.id}
            mode={mode}
            role={role}
            pblSessionId={pblContent.pblSessionId}
          />
        );
      }

      default:
        return (
          <div className="flex flex-col items-center justify-center h-full bg-gray-50 text-gray-500 gap-2">
            <AlertTriangle className="h-8 w-8 text-amber-400" />
            <p className="text-sm font-medium">Unknown scene type</p>
            <p className="text-xs text-gray-400">
              This scene type is not supported by the current player version.
            </p>
          </div>
        );
    }
  }, [content, scene.id, scene.title, mode, slides, currentSlideIndex, currentSceneIndex, totalSlides, imagesPending, role, onWidgetEvent]);

  // Quiz scenes can have lots of questions — let them scroll within the
  // 16:9 viewport. All other scene types stay overflow-hidden so animations
  // and absolute-positioned overlays (highlight/spotlight/laser) aren't
  // visually truncated against the parent's rounded corners.
  const wrapperClass =
    content.type === 'quiz'
      ? 'relative w-full h-full overflow-y-auto'
      : 'relative w-full h-full overflow-hidden';

  return (
    <div className={wrapperClass} role="region" aria-label={`Scene: ${scene.title}`}>
      {rendered}
    </div>
  );
});
