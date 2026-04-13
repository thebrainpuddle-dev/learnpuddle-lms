// src/components/maic/OutlineEditor.tsx
//
// Editable outline list for reviewing/modifying MAIC scene structure before
// generation. Supports editing title, description, reordering (up/down),
// adding, and removing scenes.

import React, { useCallback } from 'react';
import { ChevronUp, ChevronDown, Trash2, Plus, Users, Clock } from 'lucide-react';
import type { MAICOutline, MAICOutlineScene } from '../../types/maic';
import { cn } from '../../lib/utils';

interface OutlineEditorProps {
  outline: MAICOutline;
  onChange: (scenes: MAICOutlineScene[]) => void;
}

const typeColors: Record<MAICOutlineScene['type'], string> = {
  introduction: 'bg-indigo-100 text-indigo-700',
  lecture: 'bg-blue-100 text-blue-700',
  discussion: 'bg-purple-100 text-purple-700',
  quiz: 'bg-amber-100 text-amber-700',
  activity: 'bg-green-100 text-green-700',
  summary: 'bg-gray-100 text-gray-600',
};

export const OutlineEditor = React.memo<OutlineEditorProps>(function OutlineEditor({
  outline,
  onChange,
}) {
  const { scenes, agents } = outline;

  const updateScene = useCallback(
    (index: number, patch: Partial<MAICOutlineScene>) => {
      const updated = scenes.map((s, i) => (i === index ? { ...s, ...patch } : s));
      onChange(updated);
    },
    [scenes, onChange],
  );

  const moveScene = useCallback(
    (index: number, direction: -1 | 1) => {
      const targetIndex = index + direction;
      if (targetIndex < 0 || targetIndex >= scenes.length) return;

      const updated = [...scenes];
      const temp = updated[index];
      updated[index] = updated[targetIndex];
      updated[targetIndex] = temp;
      onChange(updated);
    },
    [scenes, onChange],
  );

  const removeScene = useCallback(
    (index: number) => {
      if (scenes.length <= 1) return; // Must keep at least one scene
      onChange(scenes.filter((_, i) => i !== index));
    },
    [scenes, onChange],
  );

  const addScene = useCallback(() => {
    const newScene: MAICOutlineScene = {
      id: `scene-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      title: 'New Scene',
      description: '',
      type: 'lecture',
      estimatedMinutes: 5,
      agentIds: agents.length > 0 ? [agents[0].id] : [],
    };
    onChange([...scenes, newScene]);
  }, [scenes, agents, onChange]);

  const getAgentName = useCallback(
    (agentId: string) => {
      const agent = agents.find((a) => a.id === agentId);
      return agent?.name || agentId;
    },
    [agents],
  );

  return (
    <div className="space-y-3" role="list" aria-label="Scene outline">
      {scenes.map((scene, index) => (
        <div
          key={scene.id}
          className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm"
          role="listitem"
        >
          {/* Header row */}
          <div className="flex items-start gap-3">
            {/* Scene number */}
            <span className="shrink-0 flex items-center justify-center h-6 w-6 rounded-full bg-gray-100 text-xs font-medium text-gray-500">
              {index + 1}
            </span>

            {/* Editable content */}
            <div className="flex-1 min-w-0 space-y-2">
              {/* Title */}
              <input
                type="text"
                value={scene.title}
                onChange={(e) => updateScene(index, { title: e.target.value })}
                className="w-full text-sm font-semibold text-gray-900 bg-transparent border-0 border-b border-transparent hover:border-gray-200 focus:border-primary-500 focus:ring-0 px-0 py-0.5 transition-colors"
                placeholder="Scene title"
                aria-label={`Scene ${index + 1} title`}
              />

              {/* Description */}
              <textarea
                value={scene.description}
                onChange={(e) => updateScene(index, { description: e.target.value })}
                rows={2}
                className="w-full text-sm text-gray-600 bg-transparent border rounded-md border-gray-200 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 px-2 py-1.5 resize-none"
                placeholder="Scene description..."
                aria-label={`Scene ${index + 1} description`}
              />

              {/* Meta row */}
              <div className="flex flex-wrap items-center gap-2">
                {/* Type badge */}
                <span
                  className={cn(
                    'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium',
                    typeColors[scene.type] || typeColors.lecture,
                  )}
                >
                  {scene.type}
                </span>

                {/* Estimated minutes */}
                <label className="inline-flex items-center gap-1 text-xs text-gray-400">
                  <Clock className="h-3 w-3" aria-hidden="true" />
                  <input
                    type="number"
                    min={1}
                    max={60}
                    value={scene.estimatedMinutes}
                    onChange={(e) =>
                      updateScene(index, {
                        estimatedMinutes: Math.max(1, parseInt(e.target.value, 10) || 1),
                      })
                    }
                    className="w-10 text-xs text-gray-600 bg-transparent border-0 border-b border-gray-200 focus:border-primary-500 focus:ring-0 px-0 py-0 text-center"
                    aria-label={`Scene ${index + 1} estimated minutes`}
                  />
                  <span>min</span>
                </label>

                {/* Assigned agents */}
                {scene.agentIds.length > 0 && (
                  <span className="inline-flex items-center gap-1 text-xs text-gray-400">
                    <Users className="h-3 w-3" aria-hidden="true" />
                    {scene.agentIds.map(getAgentName).join(', ')}
                  </span>
                )}

                {/* Type selector */}
                <select
                  value={scene.type}
                  onChange={(e) =>
                    updateScene(index, { type: e.target.value as MAICOutlineScene['type'] })
                  }
                  className="text-xs bg-transparent border border-gray-200 rounded px-1.5 py-0.5 text-gray-600 focus:ring-1 focus:ring-primary-500 focus:border-primary-500"
                  aria-label={`Scene ${index + 1} type`}
                >
                  <option value="introduction">Introduction</option>
                  <option value="lecture">Lecture</option>
                  <option value="discussion">Discussion</option>
                  <option value="quiz">Quiz</option>
                  <option value="activity">Activity</option>
                  <option value="summary">Summary</option>
                </select>
              </div>
            </div>

            {/* Actions */}
            <div className="shrink-0 flex flex-col items-center gap-0.5">
              <button
                type="button"
                onClick={() => moveScene(index, -1)}
                disabled={index === 0}
                className="p-1 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                aria-label={`Move scene ${index + 1} up`}
              >
                <ChevronUp className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => moveScene(index, 1)}
                disabled={index === scenes.length - 1}
                className="p-1 rounded text-gray-400 hover:text-gray-600 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                aria-label={`Move scene ${index + 1} down`}
              >
                <ChevronDown className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => removeScene(index)}
                disabled={scenes.length <= 1}
                className="p-1 rounded text-gray-400 hover:text-red-500 hover:bg-red-50 disabled:opacity-30 disabled:cursor-not-allowed transition-colors mt-1"
                aria-label={`Remove scene ${index + 1}`}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      ))}

      {/* Add scene button */}
      <button
        type="button"
        onClick={addScene}
        className={cn(
          'w-full flex items-center justify-center gap-2 rounded-lg border-2 border-dashed border-gray-200',
          'py-3 text-sm text-gray-500 hover:text-primary-600 hover:border-primary-300 hover:bg-primary-50',
          'transition-colors focus:outline-none focus:ring-2 focus:ring-primary-500',
        )}
      >
        <Plus className="h-4 w-4" />
        Add Scene
      </button>

      {/* Summary */}
      <div className="flex items-center justify-between text-xs text-gray-400 pt-1 px-1">
        <span>{scenes.length} scene{scenes.length !== 1 ? 's' : ''}</span>
        <span>
          ~{scenes.reduce((sum, s) => sum + s.estimatedMinutes, 0)} min total
        </span>
      </div>
    </div>
  );
});
