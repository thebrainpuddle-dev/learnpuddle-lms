// src/components/maic/GuardrailConfig.tsx
//
// Guardrail configuration — custom instructions textarea and block off-topic toggle.

import { cn } from '../../lib/utils';

interface GuardrailConfigProps {
  customRules: string;
  onCustomRulesChange: (rules: string) => void;
  blockOffTopic: boolean;
  onBlockOffTopicChange: (block: boolean) => void;
}

export function GuardrailConfig({
  customRules,
  onCustomRulesChange,
  blockOffTopic,
  onBlockOffTopicChange,
}: GuardrailConfigProps) {
  return (
    <div className="space-y-6">
      {/* Custom Instructions Textarea */}
      <div>
        <label
          htmlFor="custom-rules"
          className="block text-sm font-medium text-gray-700 mb-1.5"
        >
          Custom Instructions <span className="font-normal text-gray-400">(optional)</span>
        </label>
        <textarea
          id="custom-rules"
          value={customRules}
          onChange={(e) => onCustomRulesChange(e.target.value)}
          placeholder="e.g. Always respond in formal English. Focus only on Chapter 3 material."
          rows={3}
          className={cn(
            'block w-full rounded-lg border border-gray-300 bg-white px-3 py-2',
            'text-sm text-gray-900 placeholder-gray-400',
            'focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500',
            'resize-y transition-colors',
          )}
        />
        <p className="mt-1 text-xs text-gray-400">
          Extra instructions the chatbot must follow in every response.
        </p>
      </div>

      {/* Block Off-Topic Toggle */}
      <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3">
        <div>
          <p className="text-sm font-medium text-gray-700">
            Block off-topic messages
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            Redirect students when their questions are unrelated to the material
          </p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={blockOffTopic}
          onClick={() => onBlockOffTopicChange(!blockOffTopic)}
          className={cn(
            'relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200',
            blockOffTopic ? 'bg-indigo-500' : 'bg-gray-200',
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
