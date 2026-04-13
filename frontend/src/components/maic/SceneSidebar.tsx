// src/components/maic/SceneSidebar.tsx
//
// Scene navigation sidebar for the MAIC AI Classroom player. Displays a
// vertical list of scenes with type icon, title, and order number. The
// active scene is highlighted and clicking a scene navigates to it.

import React, { useCallback } from 'react';
import { Presentation, HelpCircle, Code2, Lightbulb, X } from 'lucide-react';
import { useMAICStageStore } from '../../stores/maicStageStore';
import type { MAICScene, MAICSceneType } from '../../types/maic-scenes';
import { cn } from '../../lib/utils';

interface SceneSidebarProps {
  visible: boolean;
  onClose: () => void;
}

const SCENE_ICON_MAP: Record<MAICSceneType, typeof Presentation> = {
  slide: Presentation,
  quiz: HelpCircle,
  interactive: Code2,
  pbl: Lightbulb,
};

const SCENE_LABEL_MAP: Record<MAICSceneType, string> = {
  slide: 'Slide',
  quiz: 'Quiz',
  interactive: 'Interactive',
  pbl: 'Project',
};

export const SceneSidebar = React.memo<SceneSidebarProps>(function SceneSidebar({
  visible,
  onClose,
}) {
  const scenes = useMAICStageStore((s) => s.scenes);
  const currentSceneIndex = useMAICStageStore((s) => s.currentSceneIndex);
  const goToScene = useMAICStageStore((s) => s.goToScene);

  const handleSceneClick = useCallback(
    (index: number) => {
      goToScene(index);
    },
    [goToScene],
  );

  return (
    <div
      className={cn(
        'absolute inset-y-0 left-0 z-30 w-64 bg-white dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 shadow-lg',
        'flex flex-col transition-transform duration-200 ease-in-out',
        visible ? 'translate-x-0' : '-translate-x-full',
      )}
      role="navigation"
      aria-label="Scene list"
    >
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-200 dark:border-gray-700">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Scenes
        </h2>
        <button
          type="button"
          onClick={onClose}
          className={cn(
            'p-1.5 rounded-md transition-colors',
            'focus:outline-none focus:ring-2 focus:ring-primary-500',
            'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-200 dark:hover:bg-gray-800',
          )}
          title="Close sidebar"
          aria-label="Close scene sidebar"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Scene list */}
      <ul className="flex-1 overflow-y-auto py-1">
        {scenes.map((scene: MAICScene, index: number) => {
          const isActive = index === currentSceneIndex;
          const Icon = SCENE_ICON_MAP[scene.type] ?? Presentation;
          const label = SCENE_LABEL_MAP[scene.type] ?? scene.type;

          return (
            <li key={scene.id}>
              <button
                type="button"
                onClick={() => handleSceneClick(index)}
                className={cn(
                  'w-full flex items-center gap-2.5 px-3 py-2 text-left transition-colors',
                  'focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary-500',
                  isActive
                    ? 'bg-primary-50 dark:bg-primary-900/30 border-l-[3px] border-l-primary-600 dark:border-l-primary-400'
                    : 'border-l-[3px] border-l-transparent hover:bg-gray-50 dark:hover:bg-gray-800',
                )}
                aria-current={isActive ? 'true' : undefined}
              >
                {/* Order number */}
                <span
                  className={cn(
                    'flex-shrink-0 flex items-center justify-center h-5 w-5 rounded text-[10px] font-medium',
                    isActive
                      ? 'bg-primary-600 text-white dark:bg-primary-500'
                      : 'bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-400',
                  )}
                >
                  {scene.order}
                </span>

                {/* Type icon */}
                <Icon
                  className={cn(
                    'flex-shrink-0 h-4 w-4',
                    isActive
                      ? 'text-primary-600 dark:text-primary-400'
                      : 'text-gray-400 dark:text-gray-500',
                  )}
                  aria-hidden="true"
                />

                {/* Title (truncated) */}
                <span
                  className={cn(
                    'flex-1 text-xs truncate',
                    isActive
                      ? 'text-primary-700 font-medium dark:text-primary-300'
                      : 'text-gray-700 dark:text-gray-300',
                  )}
                  title={scene.title}
                >
                  {scene.title}
                </span>

                {/* Type badge */}
                <span
                  className={cn(
                    'flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded-full font-medium',
                    isActive
                      ? 'bg-primary-100 text-primary-700 dark:bg-primary-800 dark:text-primary-300'
                      : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
                  )}
                >
                  {label}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
});
