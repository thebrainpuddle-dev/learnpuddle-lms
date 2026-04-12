// src/components/maic/GuardrailConfig.tsx
//
// Persona preset selector and guardrail configuration for AI chatbot.
// Allows teachers to pick a persona (tutor, reference, open), add custom
// rules, and toggle off-topic blocking.

import React from 'react';
import { BookOpen, Library, MessageSquare } from 'lucide-react';
import { cn } from '../../lib/utils';
import type { PersonaPreset } from '../../types/chatbot';

interface GuardrailConfigProps {
  preset: PersonaPreset;
  onPresetChange: (preset: PersonaPreset) => void;
  customRules: string;
  onCustomRulesChange: (rules: string) => void;
  blockOffTopic: boolean;
  onBlockOffTopicChange: (block: boolean) => void;
}

const presetOptions: Array<{
  value: PersonaPreset;
  label: string;
  description: string;
  icon: React.ElementType;
}> = [
  {
    value: 'tutor',
    label: 'Socratic Tutor',
    description: 'Guides learning through questions',
    icon: BookOpen,
  },
  {
    value: 'reference',
    label: 'Reference Assistant',
    description: 'Answers only from knowledge base',
    icon: Library,
  },
  {
    value: 'open',
    label: 'Open Discussion',
    description: 'Helpful study companion',
    icon: MessageSquare,
  },
];

export function GuardrailConfig({
  preset,
  onPresetChange,
  customRules,
  onCustomRulesChange,
  blockOffTopic,
  onBlockOffTopicChange,
}: GuardrailConfigProps) {
  return (
    <div className="space-y-6">
      {/* Persona Preset Selector */}
      <fieldset>
        <legend className="text-sm font-medium text-gray-700 mb-3">
          Persona Preset
        </legend>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {presetOptions.map((option) => {
            const Icon = option.icon;
            const isSelected = preset === option.value;

            return (
              <label
                key={option.value}
                className={cn(
                  'relative flex flex-col items-center gap-2 rounded-xl border-2 p-4 cursor-pointer transition-all duration-200',
                  isSelected
                    ? 'border-primary-500 bg-primary-50 shadow-sm'
                    : 'border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50',
                )}
              >
                <input
                  type="radio"
                  name="persona-preset"
                  value={option.value}
                  checked={isSelected}
                  onChange={() => onPresetChange(option.value)}
                  className="sr-only"
                />
                <Icon
                  className={cn(
                    'h-6 w-6',
                    isSelected ? 'text-primary-600' : 'text-gray-400',
                  )}
                  aria-hidden="true"
                />
                <div className="text-center">
                  <p
                    className={cn(
                      'text-sm font-semibold',
                      isSelected ? 'text-primary-700' : 'text-gray-800',
                    )}
                  >
                    {option.label}
                  </p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {option.description}
                  </p>
                </div>
                {isSelected && (
                  <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-primary-500" />
                )}
              </label>
            );
          })}
        </div>
      </fieldset>

      {/* Custom Rules Textarea */}
      <div>
        <label
          htmlFor="custom-rules"
          className="block text-sm font-medium text-gray-700 mb-1.5"
        >
          Additional Rules
        </label>
        <textarea
          id="custom-rules"
          value={customRules}
          onChange={(e) => onCustomRulesChange(e.target.value)}
          placeholder="e.g. Always respond in formal English. Never provide direct answers to homework questions."
          rows={4}
          className={cn(
            'block w-full rounded-lg border border-gray-300 bg-white px-3 py-2',
            'text-sm text-gray-900 placeholder-gray-400',
            'focus:border-primary-500 focus:ring-1 focus:ring-primary-500',
            'resize-y transition-colors',
          )}
        />
        <p className="mt-1 text-xs text-gray-400">
          Custom instructions the chatbot must follow in every response.
        </p>
      </div>

      {/* Block Off-Topic Toggle */}
      <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3">
        <div>
          <p className="text-sm font-medium text-gray-700">
            Block off-topic messages
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            Reject student messages unrelated to the knowledge base
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={blockOffTopic}
          onClick={() => onBlockOffTopicChange(!blockOffTopic)}
          className={cn(
            'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200',
            blockOffTopic ? 'bg-primary-500' : 'bg-gray-200',
          )}
        >
          <span className="sr-only">Block off-topic messages</span>
          <span
            aria-hidden="true"
            className={cn(
              'pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow ring-0 transition-transform duration-200',
              blockOffTopic ? 'translate-x-5' : 'translate-x-0',
            )}
          />
        </button>
      </div>
    </div>
  );
}
