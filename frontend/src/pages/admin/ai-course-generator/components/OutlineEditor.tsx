// src/pages/admin/ai-course-generator/components/OutlineEditor.tsx
// Inline-editable outline tree. Local state only; sync on materialise.

import React, { useCallback, useEffect, useMemo, useRef } from 'react';
import {
  PlusIcon,
  TrashIcon,
  ChevronUpIcon,
  ChevronDownIcon,
} from '@heroicons/react/24/outline';
import type {
  Outline,
  OutlineModule,
  OutlineContent,
} from '../../../../services/aiCourseGeneratorService';
import { validateOutline } from '../../../../services/aiCourseGeneratorService';

// ─── Debounce hook ────────────────────────────────────────────────────────────

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = React.useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// ─── Props ────────────────────────────────────────────────────────────────────

interface OutlineEditorProps {
  initialOutline: Outline;
  onChange: (outline: Outline, errors: Record<string, string>) => void;
}

// ─── Content row ─────────────────────────────────────────────────────────────

interface ContentRowProps {
  content: OutlineContent;
  mIdx: number;
  cIdx: number;
  errors: Record<string, string>;
  onChange: (field: keyof OutlineContent, value: string) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onRemove: () => void;
  isFirst: boolean;
  isLast: boolean;
}

const ContentRow: React.FC<ContentRowProps> = ({
  content,
  mIdx,
  cIdx,
  errors,
  onChange,
  onMoveUp,
  onMoveDown,
  onRemove,
  isFirst,
  isLast,
}) => {
  const titleKey = `module_${mIdx}_content_${cIdx}_title`;
  const descKey = `module_${mIdx}_content_${cIdx}_description`;

  return (
    <div
      data-testid={`content-row-${mIdx}-${cIdx}`}
      className="rounded-md border border-gray-200 bg-gray-50 p-3 space-y-2"
    >
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-gray-400 uppercase w-14 shrink-0">
          {content.type}
        </span>
        <input
          data-testid={`content-title-${mIdx}-${cIdx}`}
          type="text"
          value={content.title}
          onChange={(e) => onChange('title', e.target.value)}
          placeholder="Content title"
          className={`flex-1 min-w-0 rounded border px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 ${
            errors[titleKey] ? 'border-red-400' : 'border-gray-300'
          }`}
        />
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={onMoveUp}
            disabled={isFirst}
            title="Move up"
            className="cursor-pointer rounded p-1 text-gray-400 hover:text-gray-600 disabled:opacity-30 disabled:cursor-default"
          >
            <ChevronUpIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onMoveDown}
            disabled={isLast}
            title="Move down"
            className="cursor-pointer rounded p-1 text-gray-400 hover:text-gray-600 disabled:opacity-30 disabled:cursor-default"
          >
            <ChevronDownIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onRemove}
            title="Remove content"
            data-testid={`remove-content-${mIdx}-${cIdx}`}
            className="cursor-pointer rounded p-1 text-red-400 hover:text-red-600"
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>
      </div>
      {errors[titleKey] && (
        <p className="text-xs text-red-600">{errors[titleKey]}</p>
      )}
      <textarea
        data-testid={`content-desc-${mIdx}-${cIdx}`}
        value={content.description}
        onChange={(e) => onChange('description', e.target.value)}
        placeholder="Content description (optional, max 300)"
        rows={2}
        className={`w-full rounded border px-2 py-1 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary-500 ${
          errors[descKey] ? 'border-red-400' : 'border-gray-300'
        }`}
      />
      {errors[descKey] && (
        <p className="text-xs text-red-600">{errors[descKey]}</p>
      )}
    </div>
  );
};

// ─── Module block ─────────────────────────────────────────────────────────────

interface ModuleBlockProps {
  module: OutlineModule;
  mIdx: number;
  errors: Record<string, string>;
  onModuleChange: (field: 'title', value: string) => void;
  onContentChange: (
    cIdx: number,
    field: keyof OutlineContent,
    value: string
  ) => void;
  onMoveContentUp: (cIdx: number) => void;
  onMoveContentDown: (cIdx: number) => void;
  onRemoveContent: (cIdx: number) => void;
  onAddContent: () => void;
  onMoveModuleUp: () => void;
  onMoveModuleDown: () => void;
  onRemoveModule: () => void;
  isFirst: boolean;
  isLast: boolean;
}

const ModuleBlock: React.FC<ModuleBlockProps> = ({
  module,
  mIdx,
  errors,
  onModuleChange,
  onContentChange,
  onMoveContentUp,
  onMoveContentDown,
  onRemoveContent,
  onAddContent,
  onMoveModuleUp,
  onMoveModuleDown,
  onRemoveModule,
  isFirst,
  isLast,
}) => {
  const titleKey = `module_${mIdx}_title`;
  const contentsKey = `module_${mIdx}_contents`;

  return (
    <div
      data-testid={`module-block-${mIdx}`}
      className="rounded-lg border border-gray-300 bg-white p-4 space-y-3"
    >
      {/* Module header */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-gray-400 uppercase w-16 shrink-0">
          Module {mIdx + 1}
        </span>
        <input
          data-testid={`module-title-${mIdx}`}
          type="text"
          value={module.title}
          onChange={(e) => onModuleChange('title', e.target.value)}
          placeholder="Module title"
          className={`flex-1 min-w-0 rounded border px-2 py-1.5 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary-500 ${
            errors[titleKey] ? 'border-red-400' : 'border-gray-300'
          }`}
        />
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            onClick={onMoveModuleUp}
            disabled={isFirst}
            title="Move module up"
            className="cursor-pointer rounded p-1 text-gray-400 hover:text-gray-600 disabled:opacity-30 disabled:cursor-default"
          >
            <ChevronUpIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onMoveModuleDown}
            disabled={isLast}
            title="Move module down"
            className="cursor-pointer rounded p-1 text-gray-400 hover:text-gray-600 disabled:opacity-30 disabled:cursor-default"
          >
            <ChevronDownIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            data-testid={`remove-module-${mIdx}`}
            onClick={onRemoveModule}
            title="Remove module"
            className="cursor-pointer rounded p-1 text-red-400 hover:text-red-600"
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>
      </div>
      {errors[titleKey] && (
        <p className="text-xs text-red-600">{errors[titleKey]}</p>
      )}

      {/* Contents */}
      <div className="space-y-2 pl-2">
        {module.contents.map((content, cIdx) => (
          <ContentRow
            key={cIdx}
            content={content}
            mIdx={mIdx}
            cIdx={cIdx}
            errors={errors}
            onChange={(field, value) => onContentChange(cIdx, field, value)}
            onMoveUp={() => onMoveContentUp(cIdx)}
            onMoveDown={() => onMoveContentDown(cIdx)}
            onRemove={() => onRemoveContent(cIdx)}
            isFirst={cIdx === 0}
            isLast={cIdx === module.contents.length - 1}
          />
        ))}
        {errors[contentsKey] && (
          <p className="text-xs text-red-600">{errors[contentsKey]}</p>
        )}
        <button
          type="button"
          onClick={onAddContent}
          disabled={module.contents.length >= 6}
          className="flex cursor-pointer items-center gap-1 rounded-md border border-dashed border-gray-300 px-3 py-1.5 text-xs text-gray-500 hover:border-primary-400 hover:text-primary-600 disabled:opacity-40 disabled:cursor-default"
        >
          <PlusIcon className="h-3.5 w-3.5" />
          Add content
        </button>
      </div>
    </div>
  );
};

// ─── OutlineEditor ────────────────────────────────────────────────────────────

export const OutlineEditor: React.FC<OutlineEditorProps> = ({
  initialOutline,
  onChange,
}) => {
  const [outline, setOutline] = React.useState<Outline>(() =>
    JSON.parse(JSON.stringify(initialOutline))
  );

  // Debounce propagation to parent so fast typing doesn't thrash
  const debouncedOutline = useDebounce(outline, 100);

  // Memoized validation for immediate per-field error rendering (runs once per outline change).
  // CONTRACT: aiCourseGenerator.test.tsx (TASK-062-L8) asserts exactly two useMemo(validateOutline)
  // calls per single outline change (delta ≤ 2). If you add a third useMemo that calls
  // validateOutline, update the upper-bound assertion in that test.
  const errors = useMemo(() => validateOutline(outline), [outline]);

  // Memoized validation for the debounced outline used in parent propagation.
  // (This is the second useMemo(validateOutline) counted by the TASK-062-L8 delta assertion.)
  const debouncedErrors = useMemo(() => validateOutline(debouncedOutline), [debouncedOutline]);

  useEffect(() => {
    onChange(debouncedOutline, debouncedErrors);
  }, [debouncedOutline, debouncedErrors, onChange]);

  // Stable updater to avoid re-creating lambdas on each keystroke
  const update = useCallback((updater: (prev: Outline) => Outline) => {
    setOutline((prev) => updater(JSON.parse(JSON.stringify(prev))));
  }, []);

  const addModule = () => {
    update((o) => ({
      ...o,
      modules: [
        ...o.modules,
        {
          title: '',
          contents: [
            { type: 'text', title: '', description: '' },
            { type: 'text', title: '', description: '' },
          ],
        },
      ],
    }));
  };

  const removeModule = (mIdx: number) => {
    update((o) => ({
      ...o,
      modules: o.modules.filter((_, i) => i !== mIdx),
    }));
  };

  const moveModule = (mIdx: number, direction: 'up' | 'down') => {
    update((o) => {
      const mods = [...o.modules];
      const target = direction === 'up' ? mIdx - 1 : mIdx + 1;
      if (target < 0 || target >= mods.length) return o;
      [mods[mIdx], mods[target]] = [mods[target], mods[mIdx]];
      return { ...o, modules: mods };
    });
  };

  return (
    <div className="space-y-5">
      {/* Course-level fields */}
      <div className="space-y-3 rounded-lg border border-primary-200 bg-primary-50 p-4">
        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-primary-600 mb-1">
            Course Title
          </label>
          <input
            data-testid="outline-course-title"
            type="text"
            value={outline.title}
            onChange={(e) =>
              update((o) => ({ ...o, title: e.target.value }))
            }
            placeholder="Course title (max 120)"
            className={`w-full rounded-lg border px-3 py-2 text-sm font-medium focus:outline-none focus:ring-2 focus:ring-primary-500 ${
              errors['title'] ? 'border-red-400' : 'border-primary-300'
            }`}
          />
          {errors['title'] && (
            <p className="mt-1 text-xs text-red-600">{errors['title']}</p>
          )}
        </div>

        <div>
          <label className="block text-xs font-semibold uppercase tracking-wider text-primary-600 mb-1">
            Description
          </label>
          <textarea
            data-testid="outline-course-description"
            value={outline.description}
            onChange={(e) =>
              update((o) => ({ ...o, description: e.target.value }))
            }
            placeholder="Course description (max 500)"
            rows={3}
            className={`w-full rounded-lg border px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-primary-500 ${
              errors['description'] ? 'border-red-400' : 'border-primary-300'
            }`}
          />
          {errors['description'] && (
            <p className="mt-1 text-xs text-red-600">{errors['description']}</p>
          )}
        </div>
      </div>

      {/* Modules */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-700">
            Modules{' '}
            <span className="font-normal text-gray-400">
              ({outline.modules.length}/12)
            </span>
          </h3>
        </div>

        {errors['modules'] && (
          <p
            data-testid="modules-error"
            role="alert"
            className="text-sm text-red-600"
          >
            {errors['modules']}
          </p>
        )}

        {outline.modules.map((mod, mIdx) => (
          <ModuleBlock
            key={mIdx}
            module={mod}
            mIdx={mIdx}
            errors={errors}
            onModuleChange={(field, value) =>
              update((o) => {
                o.modules[mIdx] = { ...o.modules[mIdx], [field]: value };
                return o;
              })
            }
            onContentChange={(cIdx, field, value) =>
              update((o) => {
                o.modules[mIdx].contents[cIdx] = {
                  ...o.modules[mIdx].contents[cIdx],
                  [field]: value,
                };
                return o;
              })
            }
            onMoveContentUp={(cIdx) =>
              update((o) => {
                const contents = [...o.modules[mIdx].contents];
                if (cIdx === 0) return o;
                [contents[cIdx - 1], contents[cIdx]] = [
                  contents[cIdx],
                  contents[cIdx - 1],
                ];
                o.modules[mIdx] = { ...o.modules[mIdx], contents };
                return o;
              })
            }
            onMoveContentDown={(cIdx) =>
              update((o) => {
                const contents = [...o.modules[mIdx].contents];
                if (cIdx === contents.length - 1) return o;
                [contents[cIdx], contents[cIdx + 1]] = [
                  contents[cIdx + 1],
                  contents[cIdx],
                ];
                o.modules[mIdx] = { ...o.modules[mIdx], contents };
                return o;
              })
            }
            onRemoveContent={(cIdx) =>
              update((o) => {
                o.modules[mIdx].contents = o.modules[mIdx].contents.filter(
                  (_, i) => i !== cIdx
                );
                return o;
              })
            }
            onAddContent={() =>
              update((o) => {
                if (o.modules[mIdx].contents.length >= 6) return o;
                o.modules[mIdx].contents.push({
                  type: 'text',
                  title: '',
                  description: '',
                });
                return o;
              })
            }
            onMoveModuleUp={() => moveModule(mIdx, 'up')}
            onMoveModuleDown={() => moveModule(mIdx, 'down')}
            onRemoveModule={() => removeModule(mIdx)}
            isFirst={mIdx === 0}
            isLast={mIdx === outline.modules.length - 1}
          />
        ))}

        <button
          type="button"
          onClick={addModule}
          disabled={outline.modules.length >= 12}
          data-testid="add-module-btn"
          className="flex cursor-pointer w-full items-center justify-center gap-2 rounded-lg border-2 border-dashed border-gray-300 px-4 py-3 text-sm text-gray-500 hover:border-primary-400 hover:text-primary-600 disabled:opacity-40 disabled:cursor-default"
        >
          <PlusIcon className="h-4 w-4" />
          Add module
        </button>
      </div>
    </div>
  );
};
