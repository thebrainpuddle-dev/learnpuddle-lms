// src/components/maic/AgentConfigPanel.tsx
//
// Panel for configuring MAIC agent personas. Allows editing agent name,
// role, persona description, color, voice selection, and reordering.

import React, { useCallback } from 'react';
import { Plus, Trash2, ChevronUp, ChevronDown } from 'lucide-react';
import type { MAICAgent } from '../../types/maic';
import { cn } from '../../lib/utils';

interface AgentConfigPanelProps {
  agents: MAICAgent[];
  onChange: (agents: MAICAgent[]) => void;
  ttsEnabled?: boolean;
}

const ROLE_OPTIONS: { value: MAICAgent['role']; label: string }[] = [
  { value: 'professor', label: 'Professor' },
  { value: 'student', label: 'Student' },
  { value: 'assistant', label: 'Assistant' },
  { value: 'moderator', label: 'Moderator' },
];

const VOICE_OPTIONS = [
  { value: '', label: 'Default' },
  { value: 'alloy', label: 'Alloy' },
  { value: 'echo', label: 'Echo' },
  { value: 'fable', label: 'Fable' },
  { value: 'onyx', label: 'Onyx' },
  { value: 'nova', label: 'Nova' },
  { value: 'shimmer', label: 'Shimmer' },
];

const PRESET_AGENT_COLORS = [
  '#3B82F6', '#EF4444', '#10B981', '#F59E0B',
  '#8B5CF6', '#EC4899', '#06B6D4', '#F97316',
];

function generateId(): string {
  return `agent-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export const AgentConfigPanel: React.FC<AgentConfigPanelProps> = ({
  agents,
  onChange,
  ttsEnabled = false,
}) => {
  const updateAgent = useCallback(
    (index: number, updates: Partial<MAICAgent>) => {
      const next = agents.map((a, i) => (i === index ? { ...a, ...updates } : a));
      onChange(next);
    },
    [agents, onChange],
  );

  const addAgent = useCallback(() => {
    const colorIndex = agents.length % PRESET_AGENT_COLORS.length;
    const newAgent: MAICAgent = {
      id: generateId(),
      name: `Agent ${agents.length + 1}`,
      role: 'student',
      avatar: '',
      color: PRESET_AGENT_COLORS[colorIndex],
      voice: undefined,
    };
    onChange([...agents, newAgent]);
  }, [agents, onChange]);

  const removeAgent = useCallback(
    (index: number) => {
      if (agents.length <= 1) return;
      onChange(agents.filter((_, i) => i !== index));
    },
    [agents, onChange],
  );

  const moveAgent = useCallback(
    (index: number, direction: 'up' | 'down') => {
      const targetIndex = direction === 'up' ? index - 1 : index + 1;
      if (targetIndex < 0 || targetIndex >= agents.length) return;
      const next = [...agents];
      [next[index], next[targetIndex]] = [next[targetIndex], next[index]];
      onChange(next);
    },
    [agents, onChange],
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          Agent Configuration
        </h3>
        <button
          type="button"
          onClick={addAgent}
          className={cn(
            'inline-flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-medium',
            'bg-primary-50 text-primary-700 hover:bg-primary-100',
            'dark:bg-primary-900 dark:text-primary-300 dark:hover:bg-primary-800',
            'focus:outline-none focus:ring-2 focus:ring-primary-500',
            'transition-colors',
          )}
        >
          <Plus className="h-3.5 w-3.5" />
          Add Agent
        </button>
      </div>

      <div className="space-y-3">
        {agents.map((agent, index) => (
          <div
            key={agent.id}
            className="rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-4 space-y-3"
          >
            {/* Header row: order controls + name + delete */}
            <div className="flex items-center gap-2">
              {/* Reorder buttons */}
              <div className="flex flex-col gap-0.5">
                <button
                  type="button"
                  onClick={() => moveAgent(index, 'up')}
                  disabled={index === 0}
                  className={cn(
                    'p-0.5 rounded transition-colors',
                    'focus:outline-none focus:ring-1 focus:ring-primary-500',
                    index === 0
                      ? 'text-gray-200 dark:text-gray-700 cursor-not-allowed'
                      : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-700',
                  )}
                  aria-label="Move up"
                >
                  <ChevronUp className="h-3.5 w-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => moveAgent(index, 'down')}
                  disabled={index === agents.length - 1}
                  className={cn(
                    'p-0.5 rounded transition-colors',
                    'focus:outline-none focus:ring-1 focus:ring-primary-500',
                    index === agents.length - 1
                      ? 'text-gray-200 dark:text-gray-700 cursor-not-allowed'
                      : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100 dark:hover:text-gray-300 dark:hover:bg-gray-700',
                  )}
                  aria-label="Move down"
                >
                  <ChevronDown className="h-3.5 w-3.5" />
                </button>
              </div>

              {/* Color indicator */}
              <span
                className="h-4 w-4 shrink-0 rounded-full border border-gray-200 dark:border-gray-600"
                style={{ backgroundColor: agent.color }}
                aria-hidden="true"
              />

              {/* Name input */}
              <input
                type="text"
                value={agent.name}
                onChange={(e) => updateAgent(index, { name: e.target.value })}
                className={cn(
                  'flex-1 min-w-0 rounded-md border border-gray-300 dark:border-gray-600',
                  'bg-white dark:bg-gray-900 px-2.5 py-1.5 text-sm',
                  'text-gray-900 dark:text-gray-100',
                  'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                )}
                placeholder="Agent name"
                aria-label="Agent name"
              />

              {/* Delete button */}
              <button
                type="button"
                onClick={() => removeAgent(index)}
                disabled={agents.length <= 1}
                className={cn(
                  'p-1.5 rounded-md transition-colors',
                  'focus:outline-none focus:ring-2 focus:ring-red-500',
                  agents.length <= 1
                    ? 'text-gray-200 dark:text-gray-700 cursor-not-allowed'
                    : 'text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/30',
                )}
                aria-label={`Remove ${agent.name}`}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>

            {/* Role select + Color picker */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                  Role
                </label>
                <select
                  value={agent.role}
                  onChange={(e) => updateAgent(index, { role: e.target.value as MAICAgent['role'] })}
                  className={cn(
                    'w-full rounded-md border border-gray-300 dark:border-gray-600',
                    'bg-white dark:bg-gray-900 px-2.5 py-1.5 text-sm',
                    'text-gray-900 dark:text-gray-100',
                    'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                  )}
                  aria-label="Agent role"
                >
                  {ROLE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                  Color
                </label>
                <div className="flex items-center gap-1.5">
                  {PRESET_AGENT_COLORS.map((color) => (
                    <button
                      key={color}
                      type="button"
                      onClick={() => updateAgent(index, { color })}
                      className={cn(
                        'h-6 w-6 rounded-full border-2 transition-transform hover:scale-110',
                        agent.color === color
                          ? 'border-gray-900 dark:border-gray-100 scale-110'
                          : 'border-gray-200 dark:border-gray-600',
                      )}
                      style={{ backgroundColor: color }}
                      aria-label={`Color ${color}`}
                      aria-pressed={agent.color === color}
                    />
                  ))}
                </div>
              </div>
            </div>

            {/* Persona description */}
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                Persona Description
              </label>
              <textarea
                value={agent.avatar}
                onChange={(e) => updateAgent(index, { avatar: e.target.value })}
                rows={2}
                className={cn(
                  'w-full rounded-md border border-gray-300 dark:border-gray-600',
                  'bg-white dark:bg-gray-900 px-2.5 py-1.5 text-sm',
                  'text-gray-900 dark:text-gray-100',
                  'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                  'resize-none',
                )}
                placeholder="Describe the agent's personality and teaching style..."
                aria-label="Persona description"
              />
            </div>

            {/* Voice selection (if TTS enabled) */}
            {ttsEnabled && (
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
                  Voice
                </label>
                <select
                  value={agent.voice || ''}
                  onChange={(e) => updateAgent(index, { voice: e.target.value || undefined })}
                  className={cn(
                    'w-full rounded-md border border-gray-300 dark:border-gray-600',
                    'bg-white dark:bg-gray-900 px-2.5 py-1.5 text-sm',
                    'text-gray-900 dark:text-gray-100',
                    'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
                  )}
                  aria-label="Voice selection"
                >
                  {VOICE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};
