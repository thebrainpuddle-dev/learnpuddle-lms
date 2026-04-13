// src/components/maic/SceneRenderer.tsx
//
// Routes between different scene types (slide, quiz, interactive, pbl)
// based on scene.type. This is the main entry point for rendering any
// MAIC scene in the stage viewport.

import React, { useMemo } from 'react';
import { SlideRenderer } from './SlideRenderer';
import { QuizRenderer } from './QuizRenderer';
import { InteractiveRenderer } from './InteractiveRenderer';
import { PBLRenderer } from './PBLRenderer';
import type {
  MAICScene,
  MAICSlideContent,
  MAICQuizContent,
  MAICInteractiveContent,
  MAICPBLContent,
} from '../../types/maic-scenes';
import { AlertTriangle } from 'lucide-react';

interface SceneRendererProps {
  scene: MAICScene;
  mode?: 'autonomous' | 'playback';
}

export const SceneRenderer = React.memo<SceneRendererProps>(function SceneRenderer({
  scene,
  mode = 'autonomous',
}) {
  const content = scene.content;

  const rendered = useMemo(() => {
    switch (content.type) {
      case 'slide': {
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
        return (
          <InteractiveRenderer
            html={interactiveContent.html}
            url={interactiveContent.url}
            sceneId={scene.id}
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
  }, [content, scene.id, scene.title, mode]);

  return (
    <div className="relative w-full h-full overflow-hidden" role="region" aria-label={`Scene: ${scene.title}`}>
      {rendered}
    </div>
  );
});
