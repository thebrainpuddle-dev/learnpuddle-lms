// src/components/courses/AIGenerationPanel.tsx
//
// Single-page progressive AI content generator.
// Flow: Input -> Outline Review -> Content Generation -> Preview & Add to Module

import React, { useState, useCallback, useRef } from 'react';
import DOMPurify from 'dompurify';
import {
  ArrowUpTrayIcon,
  DocumentTextIcon,
  TrashIcon,
  PlusIcon,
  CheckIcon,
  XMarkIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  ArrowPathIcon,
  ExclamationTriangleIcon,
  VideoCameraIcon,
  DocumentIcon,
} from '@heroicons/react/24/outline';
import { aiService } from '../../services/aiService';
import { createContent } from '../../pages/admin/course-editor/api';
import { adminService } from '../../services/adminService';
import api from '../../config/api';
import type {
  GeneratorState,
  ContentType,
  AIGenerationPanelProps,
  OutlineSection,
  GeneratedItem,
  GeneratedQuestion,
  SectionProgress,
} from './ai-generation/types';
import { ALL_CONTENT_TYPES } from './ai-generation/types';
import { genId, extractErrorMessage, formatFileSize } from './ai-generation/helpers';

// ── Display Constants ─────────────────────────────────────────────────────────

const TYPE_BADGE_CLASSES: Record<ContentType, string> = {
  lesson: 'bg-blue-100 text-blue-700',
  quiz: 'bg-amber-100 text-amber-700',
  assignment: 'bg-purple-100 text-purple-700',
  summary: 'bg-green-100 text-green-700',
};

const TYPE_LABELS: Record<ContentType, string> = {
  lesson: 'Lesson',
  quiz: 'Quiz',
  assignment: 'Assignment',
  summary: 'Summary',
};

// ── Sub-components ─────────────────────────────────────────────────────────────

function ModuleSelector({
  modules,
  selectedId,
  onChange,
}: {
  modules: AIGenerationPanelProps['modules'];
  selectedId: string;
  onChange: (id: string) => void;
}) {
  return (
    <div>
      <label htmlFor="ai-module-selector" className="block text-sm font-medium text-gray-700 mb-1.5">
        Target Module
      </label>
      <select
        id="ai-module-selector"
        value={selectedId}
        onChange={(e) => onChange(e.target.value)}
        className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
        aria-label="Select a module to generate content for"
      >
        <option value="">Select a module...</option>
        {modules.map((m) => (
          <option key={m.id} value={m.id}>
            {m.order}. {m.title}
          </option>
        ))}
      </select>
    </div>
  );
}

function FilePreviewCard({
  file,
  onRemove,
}: {
  file: File;
  onRemove: () => void;
}) {
  const icon =
    file.type.includes('pdf') ? (
      <DocumentTextIcon className="h-5 w-5 text-red-500" />
    ) : file.type.includes('video') ? (
      <VideoCameraIcon className="h-5 w-5 text-blue-500" />
    ) : (
      <DocumentIcon className="h-5 w-5 text-gray-500" />
    );

  return (
    <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 mt-3">
      {icon}
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-gray-900 truncate">{file.name}</p>
        <p className="text-xs text-gray-500">{formatFileSize(file.size)}</p>
      </div>
      <button
        type="button"
        onClick={onRemove}
        className="p-1 text-gray-400 hover:text-gray-600 rounded"
        aria-label="Remove file"
      >
        <XMarkIcon className="h-4 w-4" />
      </button>
    </div>
  );
}

function ContentTypePills({
  selected,
  onToggle,
}: {
  selected: Set<ContentType>;
  onToggle: (type: ContentType) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {ALL_CONTENT_TYPES.map((type) => {
        const isActive = selected.has(type);
        return (
          <button
            key={type}
            type="button"
            onClick={() => onToggle(type)}
            className={`rounded-full px-3 py-1.5 text-xs font-medium border cursor-pointer transition-colors ${
              isActive
                ? 'border-primary-500 bg-primary-50 text-primary-700'
                : 'border-gray-200 text-gray-500 hover:border-gray-300'
            }`}
            aria-pressed={isActive}
            aria-label={`Toggle ${TYPE_LABELS[type]} generation`}
          >
            {TYPE_LABELS[type]}
          </button>
        );
      })}
    </div>
  );
}

function OutlineCard({
  section,
  index,
  total,
  onUpdate,
  onMoveUp,
  onMoveDown,
  onDelete,
}: {
  section: OutlineSection;
  index: number;
  total: number;
  onUpdate: (updated: OutlineSection) => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onDelete: () => void;
}) {
  const updateKeyPoint = (kpIndex: number, value: string) => {
    const newPoints = [...section.keyPoints];
    newPoints[kpIndex] = value;
    onUpdate({ ...section, keyPoints: newPoints });
  };

  const addKeyPoint = () => {
    onUpdate({ ...section, keyPoints: [...section.keyPoints, ''] });
  };

  const removeKeyPoint = (kpIndex: number) => {
    onUpdate({ ...section, keyPoints: section.keyPoints.filter((_, i) => i !== kpIndex) });
  };

  const toggleType = (type: ContentType) => {
    const next = new Set(section.selectedTypes);
    if (next.has(type)) {
      next.delete(type);
    } else {
      next.add(type);
    }
    onUpdate({ ...section, selectedTypes: next });
  };

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
      <div className="flex items-start gap-3">
        <div className="w-6 h-6 rounded-full bg-primary-500 text-white text-sm flex items-center justify-center shrink-0 mt-1">
          {index + 1}
        </div>
        <div className="flex-1 min-w-0 space-y-3">
          <div>
            <label className="sr-only">Section title</label>
            <input
              type="text"
              value={section.title}
              onChange={(e) => onUpdate({ ...section, title: e.target.value })}
              className="w-full text-sm font-semibold text-gray-900 border border-gray-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              placeholder="Section title"
              aria-label={`Section ${index + 1} title`}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Description</label>
            <textarea
              value={section.description}
              onChange={(e) => onUpdate({ ...section, description: e.target.value })}
              rows={2}
              className="w-full text-sm text-gray-700 border border-gray-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-none"
              placeholder="Section description"
              aria-label={`Section ${index + 1} description`}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Learning Objectives</label>
            <textarea
              value={section.learningObjectives}
              onChange={(e) => onUpdate({ ...section, learningObjectives: e.target.value })}
              rows={2}
              className="w-full text-sm text-gray-700 border border-gray-200 rounded-lg px-3 py-2 focus:ring-2 focus:ring-primary-500 focus:border-primary-500 resize-none"
              placeholder="What learners will be able to do after this section"
              aria-label={`Section ${index + 1} learning objectives`}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Key Points</label>
            <div className="space-y-1.5">
              {section.keyPoints.map((kp, kpIdx) => (
                <div key={kpIdx} className="flex items-center gap-2">
                  <span className="text-xs text-gray-400 w-4 text-right shrink-0">{kpIdx + 1}.</span>
                  <input
                    type="text"
                    value={kp}
                    onChange={(e) => updateKeyPoint(kpIdx, e.target.value)}
                    className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-1.5 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    placeholder={`Key point ${kpIdx + 1}`}
                    aria-label={`Section ${index + 1}, key point ${kpIdx + 1}`}
                  />
                  {section.keyPoints.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeKeyPoint(kpIdx)}
                      className="p-1 text-gray-400 hover:text-red-500 rounded"
                      aria-label={`Remove key point ${kpIdx + 1}`}
                    >
                      <XMarkIcon className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              ))}
              <button
                type="button"
                onClick={addKeyPoint}
                className="text-xs font-medium text-primary-600 hover:text-primary-700"
              >
                + Add key point
              </button>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1">Content types to generate</label>
            <div className="flex flex-wrap gap-1.5">
              {ALL_CONTENT_TYPES.map((type) => {
                const isActive = section.selectedTypes.has(type);
                return (
                  <button
                    key={type}
                    type="button"
                    onClick={() => toggleType(type)}
                    className={`rounded-full px-2.5 py-1 text-xs font-medium border cursor-pointer transition-colors ${
                      isActive
                        ? 'border-primary-500 bg-primary-50 text-primary-700'
                        : 'border-gray-200 text-gray-400 hover:border-gray-300'
                    }`}
                    aria-pressed={isActive}
                  >
                    {TYPE_LABELS[type]}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          <button
            type="button"
            onClick={onMoveUp}
            disabled={index === 0}
            className="p-1 text-gray-400 hover:text-gray-600 rounded disabled:opacity-30 disabled:cursor-not-allowed"
            aria-label="Move section up"
          >
            <ChevronUpIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onMoveDown}
            disabled={index === total - 1}
            className="p-1 text-gray-400 hover:text-gray-600 rounded disabled:opacity-30 disabled:cursor-not-allowed"
            aria-label="Move section down"
          >
            <ChevronDownIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="p-1 text-gray-400 hover:text-red-500 rounded"
            aria-label="Delete section"
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

function GenerationProgressView({ sections }: { sections: SectionProgress[] }) {
  return (
    <div className="space-y-2">
      {sections.map((s, i) => (
        <div key={i} className="flex items-center gap-3 py-2">
          {s.status === 'generating' && (
            <div className="h-5 w-5 shrink-0">
              <div className="h-5 w-5 rounded-full border-2 border-primary-500 border-t-transparent animate-spin" />
            </div>
          )}
          {s.status === 'done' && (
            <CheckIcon className="h-5 w-5 text-green-500 shrink-0" />
          )}
          {s.status === 'failed' && (
            <ExclamationTriangleIcon className="h-5 w-5 text-red-500 shrink-0" />
          )}
          {s.status === 'pending' && (
            <div className="h-5 w-5 rounded-full border-2 border-gray-200 shrink-0" />
          )}
          <span className="text-sm text-gray-700">{s.sectionTitle}</span>
          <span className="text-xs text-gray-400 ml-auto">
            {s.status === 'generating' ? 'Generating...' : s.status === 'done' ? 'Done' : s.status === 'failed' ? 'Failed' : 'Pending'}
          </span>
        </div>
      ))}
    </div>
  );
}

function ContentPreviewCard({
  item,
  onAdd,
  onRegenerate,
}: {
  item: GeneratedItem;
  onAdd: () => void;
  onRegenerate: () => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3">
      <div className="flex items-center gap-3">
        {item.status === 'done' && <CheckIcon className="h-5 w-5 text-green-500 shrink-0" />}
        {item.status === 'failed' && <ExclamationTriangleIcon className="h-5 w-5 text-red-500 shrink-0" />}
        <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${TYPE_BADGE_CLASSES[item.type]}`}>
          {TYPE_LABELS[item.type]}
        </span>
        <span className="text-sm font-medium text-gray-900 flex-1 min-w-0 truncate">{item.title}</span>
      </div>

      {item.status === 'failed' && item.error && (
        <p className="text-xs text-red-600">{item.error}</p>
      )}

      {item.status === 'done' && (
        <>
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-xs font-medium text-primary-600 hover:text-primary-700"
            aria-expanded={expanded}
          >
            {expanded ? 'Hide Preview' : 'Preview'}
          </button>

          {expanded && (
            <div className="border border-gray-100 rounded-lg p-4 bg-gray-50 text-sm max-h-80 overflow-y-auto">
              {item.type === 'lesson' || item.type === 'summary' ? (
                <div
                  className="prose prose-sm max-w-none"
                  dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(item.content) }}
                />
              ) : item.type === 'quiz' && item.questions ? (
                <div className="space-y-4">
                  {item.questions.map((q, qi) => (
                    <div key={qi} className="space-y-1">
                      <p className="font-medium text-gray-900">
                        {qi + 1}. {q.prompt}
                      </p>
                      <ul className="ml-4 space-y-0.5">
                        {q.options.map((opt, oi) => (
                          <li
                            key={oi}
                            className={`text-sm ${oi === q.correctIndex ? 'text-green-700 font-medium' : 'text-gray-600'}`}
                          >
                            {String.fromCharCode(65 + oi)}. {opt}
                            {oi === q.correctIndex && ' (correct)'}
                          </li>
                        ))}
                      </ul>
                      {q.explanation && (
                        <p className="text-xs text-gray-500 ml-4 italic">{q.explanation}</p>
                      )}
                    </div>
                  ))}
                </div>
              ) : item.type === 'assignment' ? (
                <div className="space-y-3">
                  {item.instructions && (
                    <div>
                      <p className="font-medium text-gray-900 text-xs uppercase tracking-wide mb-1">Instructions</p>
                      <p className="text-gray-700 whitespace-pre-wrap">{item.instructions}</p>
                    </div>
                  )}
                  {item.rubric && (
                    <div>
                      <p className="font-medium text-gray-900 text-xs uppercase tracking-wide mb-1">Rubric</p>
                      <p className="text-gray-700 whitespace-pre-wrap">{item.rubric}</p>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-gray-600">{item.content}</p>
              )}
            </div>
          )}

          <div className="flex items-center gap-2">
            {item.added ? (
              <span className="rounded-lg bg-green-50 border border-green-200 text-green-700 px-4 py-2 text-sm font-medium cursor-default inline-flex items-center gap-1.5">
                <CheckIcon className="h-4 w-4" /> Added
              </span>
            ) : (
              <button
                type="button"
                onClick={onAdd}
                className="rounded-lg border border-primary-500 text-primary-600 px-4 py-2 text-sm font-medium hover:bg-primary-50 transition-colors"
              >
                Add to Module
              </button>
            )}
            <button
              type="button"
              onClick={onRegenerate}
              className="rounded-lg border border-gray-200 text-gray-600 px-3 py-2 text-sm hover:bg-gray-50 transition-colors inline-flex items-center gap-1.5"
              aria-label="Regenerate this item"
            >
              <ArrowPathIcon className="h-4 w-4" />
              Regenerate
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

export const AIGenerationPanel: React.FC<AIGenerationPanelProps> = ({
  courseId,
  modules,
  onContentAdded,
}) => {
  // ── State ────────────────────────────────────────────────────────────────
  const [generatorState, setGeneratorState] = useState<GeneratorState>('idle');
  const [selectedModuleId, setSelectedModuleId] = useState('');
  const [inputText, setInputText] = useState('');
  const [attachedFile, setAttachedFile] = useState<File | null>(null);
  const [parsedMaterial, setParsedMaterial] = useState<{ text: string; metadata: Record<string, unknown> } | null>(null);
  const [selectedTypes, setSelectedTypes] = useState<Set<ContentType>>(
    () => new Set(ALL_CONTENT_TYPES),
  );
  const [outline, setOutline] = useState<OutlineSection[]>([]);
  const [generatedItems, setGeneratedItems] = useState<GeneratedItem[]>([]);
  const [sectionProgress, setSectionProgress] = useState<SectionProgress[]>([]);
  const [error, setError] = useState('');
  const [isDragOver, setIsDragOver] = useState(false);
  const [lessonId, setLessonId] = useState<string | null>(null);
  const [lessonScenes, setLessonScenes] = useState<unknown[]>([]);
  const [lessonTitle, setLessonTitle] = useState('');

  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // ── Derived ──────────────────────────────────────────────────────────────
  const canGenerate = selectedModuleId !== '' && (inputText.trim() !== '' || attachedFile !== null);
  const selectedModule = modules.find((m) => m.id === selectedModuleId);

  // ── Handlers ─────────────────────────────────────────────────────────────

  const handleToggleType = useCallback((type: ContentType) => {
    setSelectedTypes((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }, []);

  const handleFileSelect = useCallback((file: File) => {
    setAttachedFile(file);
    setParsedMaterial(null);
  }, []);

  const handleFileDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) {
        handleFileSelect(file);
      }
    },
    [handleFileSelect],
  );

  const handleFileInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        handleFileSelect(file);
      }
      // Reset so same file can be re-selected
      e.target.value = '';
    },
    [handleFileSelect],
  );

  const openFilePicker = useCallback((accept?: string) => {
    if (fileInputRef.current) {
      fileInputRef.current.accept = accept || '*/*';
      fileInputRef.current.click();
    }
  }, []);

  const autoResizeTextarea = useCallback(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = 'auto';
      const newHeight = Math.min(Math.max(ta.scrollHeight, 120), 300);
      ta.style.height = `${newHeight}px`;
    }
  }, []);

  // ── Stage 1: Generate Outline ────────────────────────────────────────────

  const handleGenerate = useCallback(async () => {
    setError('');

    try {
      let materialText = '';

      // Parse file if attached
      if (attachedFile) {
        setGeneratorState('parsing');
        try {
          const result = await aiService.parseMaterial(attachedFile);
          materialText = result.text;
          setParsedMaterial(result);
        } catch (err) {
          setError(extractErrorMessage(err, 'Failed to parse the uploaded file. Please try a different file or enter a topic manually.'));
          setGeneratorState('idle');
          return;
        }
      }

      // Generate outline
      setGeneratorState('generating-outline');
      try {
        const outlineResult = await aiService.generateOutline({
          topic: inputText || 'Content from uploaded material',
          description: inputText,
          target_audience: 'Educators and teachers',
          num_modules: 3,
          ...(materialText ? { material_context: materialText } : {}),
        });

        // Transform outline into sections
        // The backend returns learning_objectives and key_points directly on modules (OpenMAIC style)
        const sections: OutlineSection[] = (outlineResult.modules || []).map((mod: any) => ({
          id: genId(),
          title: mod.title,
          description: mod.description,
          learningObjectives: Array.isArray(mod.learning_objectives)
            ? mod.learning_objectives.join('; ')
            : (mod.content_items || []).map((c: any) => c.description).join('; '),
          keyPoints: Array.isArray(mod.key_points)
            ? mod.key_points
            : (mod.content_items || []).map((c: any) => c.title),
          selectedTypes: new Set(selectedTypes),
        }));

        if (sections.length === 0) {
          // Create at least one default section
          sections.push({
            id: genId(),
            title: inputText || 'Section 1',
            description: inputText || '',
            learningObjectives: '',
            keyPoints: [''],
            selectedTypes: new Set(selectedTypes),
          });
        }

        setOutline(sections);
        setGeneratorState('outline-ready');
      } catch (err) {
        setError(extractErrorMessage(err, 'Failed to generate outline. Please try again.'));
        setGeneratorState('idle');
      }
    } catch (err) {
      setError(extractErrorMessage(err, 'An unexpected error occurred. Please try again.'));
      setGeneratorState('idle');
    }
  }, [attachedFile, inputText, selectedTypes]);

  // ── Stage 2: Generate Content ────────────────────────────────────────────

  const handleGenerateContent = useCallback(async () => {
    setError('');
    setGeneratorState('generating-content');

    // Initialize progress
    const progress: SectionProgress[] = outline.map((s) => ({
      sectionTitle: s.title,
      status: 'pending',
    }));
    setSectionProgress(progress);

    const allItems: GeneratedItem[] = [];

    for (let sIdx = 0; sIdx < outline.length; sIdx++) {
      const section = outline[sIdx];

      // Update progress
      setSectionProgress((prev) =>
        prev.map((p, i) => (i === sIdx ? { ...p, status: 'generating' } : p)),
      );

      const typesToGenerate = Array.from(section.selectedTypes);

      for (const type of typesToGenerate) {
        const itemId = genId();
        const item: GeneratedItem = {
          id: itemId,
          sectionIndex: sIdx,
          type,
          title: `${section.title} - ${TYPE_LABELS[type]}`,
          content: '',
          status: 'generating',
          added: false,
        };
        allItems.push(item);
        setGeneratedItems([...allItems]);

        try {
          if (type === 'lesson') {
            const result = await aiService.generateContent({
              module_title: section.title,
              module_description: section.description + '\n\nKey points: ' + section.keyPoints.join(', '),
              content_type: 'TEXT',
            });
            const raw = result.data as any;
            // Backend returns { content: { text_content, title, ... } }
            const nested = raw?.content;
            item.content = (typeof nested === 'object' ? nested?.text_content : nested) || raw?.text_content || '';
            item.title = (typeof nested === 'object' ? nested?.title : null) || section.title;
            item.status = 'done';
          } else if (type === 'quiz') {
            try {
              const result = await api.post(`/courses/${courseId}/assignments/ai-generate/`, {
                scope_type: 'MODULE',
                module_id: selectedModuleId,
                question_count: 3,
                title_hint: section.title,
              });
              const quizData = result.data as {
                title?: string;
                questions?: Array<{
                  prompt: string;
                  options: string[];
                  correct_answer: { option_index?: number; value?: boolean };
                  explanation?: string;
                }>;
              };
              item.title = quizData.title || `${section.title} Quiz`;
              item.questions = (quizData.questions || []).map((q) => ({
                prompt: q.prompt,
                options: q.options || [],
                correctIndex: q.correct_answer?.option_index ?? 0,
                explanation: q.explanation,
              }));
              item.status = 'done';
            } catch (e) {
              item.status = 'failed';
              item.error = extractErrorMessage(e, 'Quiz generation failed.');
            }
          } else if (type === 'assignment') {
            try {
              const result = await aiService.generateAssignment({
                topic: section.title,
                description: section.description + '\n\nKey points: ' + section.keyPoints.join(', '),
              });
              // Backend returns { assignment: { title, instructions, rubric, ... } }
              const assignData = (result as any)?.assignment || result || {};
              item.title = assignData.title || `${section.title} Assignment`;
              const instrText = assignData.instructions || '';
              item.instructions = instrText;
              item.rubric = Array.isArray(assignData.rubric)
                ? assignData.rubric.map((r: any) => `${r.level}: ${r.description}`).join('\n')
                : (assignData.rubric || '');
              item.content = instrText;
              item.status = 'done';
            } catch (e) {
              item.status = 'failed';
              item.error = extractErrorMessage(e, 'Assignment generation failed.');
            }
          } else if (type === 'summary') {
            try {
              const summaryText = section.description + '. ' + section.keyPoints.join('. ');
              const result = await aiService.summarize({ text: summaryText });
              const sumData = result.data as { summary?: string; content?: string };
              item.content = sumData.summary || sumData.content || '';
              item.title = `${section.title} - Summary`;
              item.status = 'done';
            } catch (e) {
              item.status = 'failed';
              item.error = extractErrorMessage(e, 'Summary generation failed.');
            }
          }
        } catch (e) {
          item.status = 'failed';
          item.error = extractErrorMessage(e, 'Content generation failed.');
        }

        setGeneratedItems([...allItems]);
      }

      // Update section progress
      const allSectionDone = allItems
        .filter((it) => it.sectionIndex === sIdx)
        .every((it) => it.status === 'done' || it.status === 'failed');
      const anyFailed = allItems
        .filter((it) => it.sectionIndex === sIdx)
        .some((it) => it.status === 'failed');

      setSectionProgress((prev) =>
        prev.map((p, i) =>
          i === sIdx ? { ...p, status: anyFailed ? 'failed' : allSectionDone ? 'done' : 'generating' } : p,
        ),
      );
    }

    setGeneratorState('content-ready');
  }, [outline, courseId, selectedModuleId]);

  // ── Add to Module ────────────────────────────────────────────────────────

  const handleAddToModule = useCallback(
    async (itemId: string) => {
      const item = generatedItems.find((i) => i.id === itemId);
      if (!item || item.added || !selectedModuleId) return;

      try {
        if (item.type === 'lesson' || item.type === 'summary') {
          const formData = new FormData();
          formData.append('title', item.title);
          formData.append('content_type', 'TEXT');
          formData.append('text_content', item.content);
          formData.append('is_mandatory', 'false');

          await createContent({
            courseId,
            moduleId: selectedModuleId,
            data: formData,
          });
        } else if (item.type === 'quiz' && item.questions) {
          await adminService.createCourseAssignment(courseId, {
            title: item.title,
            description: '',
            instructions: '',
            max_score: item.questions.length,
            passing_score: Math.ceil(item.questions.length * 0.7),
            is_mandatory: false,
            is_active: true,
            scope_type: 'MODULE',
            module_id: selectedModuleId,
            assignment_type: 'QUIZ',
            questions: item.questions.map((q, qi) => ({
              order: qi + 1,
              question_type: 'MCQ' as const,
              selection_mode: 'SINGLE' as const,
              prompt: q.prompt,
              options: q.options,
              correct_answer: { option_index: q.correctIndex },
              explanation: q.explanation || '',
              points: 1,
            })),
          });
        } else if (item.type === 'assignment') {
          await adminService.createCourseAssignment(courseId, {
            title: item.title,
            description: item.instructions || '',
            instructions: item.instructions || '',
            max_score: 100,
            passing_score: 70,
            is_mandatory: false,
            is_active: true,
            scope_type: 'MODULE',
            module_id: selectedModuleId,
            assignment_type: 'WRITTEN',
          });
        }

        setGeneratedItems((prev) =>
          prev.map((i) => (i.id === itemId ? { ...i, added: true } : i)),
        );
        onContentAdded();
      } catch (e) {
        setError(extractErrorMessage(e, `Failed to add "${item.title}" to module. Please try again.`));
      }
    },
    [generatedItems, selectedModuleId, courseId, onContentAdded],
  );

  const handleAddAllToModule = useCallback(async () => {
    const addableItems = generatedItems.filter((i) => i.status === 'done' && !i.added);
    for (const item of addableItems) {
      await handleAddToModule(item.id);
    }
  }, [generatedItems, handleAddToModule]);

  // ── Regenerate single item ───────────────────────────────────────────────

  const handleRegenerate = useCallback(
    async (itemId: string) => {
      const itemIndex = generatedItems.findIndex((i) => i.id === itemId);
      if (itemIndex === -1) return;

      const item = generatedItems[itemIndex];
      const section = outline[item.sectionIndex];
      if (!section) return;

      // Mark as generating
      setGeneratedItems((prev) =>
        prev.map((i) =>
          i.id === itemId ? { ...i, status: 'generating', error: undefined, added: false } : i,
        ),
      );

      try {
        if (item.type === 'lesson') {
          const result = await aiService.generateContent({
            module_title: section.title,
            module_description: section.description + '\n\nKey points: ' + section.keyPoints.join(', '),
            content_type: 'TEXT',
          });
          const raw = result.data as any;
          const nested = raw?.content;
          const lessonContent = (typeof nested === 'object' ? nested?.text_content : nested) || raw?.text_content || '';
          const lessonTitle = (typeof nested === 'object' ? nested?.title : null) || section.title;
          setGeneratedItems((prev) =>
            prev.map((i) =>
              i.id === itemId
                ? { ...i, content: lessonContent, title: lessonTitle, status: 'done' }
                : i,
            ),
          );
        } else if (item.type === 'quiz') {
          const result = await api.post(`/courses/${courseId}/assignments/ai-generate/`, {
            scope_type: 'MODULE',
            module_id: selectedModuleId,
            question_count: 3,
            title_hint: section.title,
          });
          const quizData = result.data as {
            title?: string;
            questions?: Array<{
              prompt: string;
              options: string[];
              correct_answer: { option_index?: number };
              explanation?: string;
            }>;
          };
          setGeneratedItems((prev) =>
            prev.map((i) =>
              i.id === itemId
                ? {
                    ...i,
                    title: quizData.title || i.title,
                    questions: (quizData.questions || []).map((q) => ({
                      prompt: q.prompt,
                      options: q.options || [],
                      correctIndex: q.correct_answer?.option_index ?? 0,
                      explanation: q.explanation,
                    })),
                    status: 'done',
                  }
                : i,
            ),
          );
        } else if (item.type === 'assignment') {
          const result = await aiService.generateAssignment({
            topic: section.title,
            description: section.description,
          });
          const assignData = (result as any)?.assignment || result || {};
          const rubricStr = Array.isArray(assignData.rubric)
            ? assignData.rubric.map((r: any) => `${r.level}: ${r.description}`).join('\n')
            : (assignData.rubric || '');
          setGeneratedItems((prev) =>
            prev.map((i) =>
              i.id === itemId
                ? {
                    ...i,
                    title: assignData.title || i.title,
                    instructions: assignData.instructions || '',
                    rubric: rubricStr,
                    content: assignData.instructions || '',
                    status: 'done',
                  }
                : i,
            ),
          );
        } else if (item.type === 'summary') {
          const summaryText = section.description + '. ' + section.keyPoints.join('. ');
          const result = await aiService.summarize({ text: summaryText });
          const sumData = result.data as { summary?: string; content?: string };
          setGeneratedItems((prev) =>
            prev.map((i) =>
              i.id === itemId
                ? { ...i, content: sumData.summary || sumData.content || '', status: 'done' }
                : i,
            ),
          );
        }
      } catch (e) {
        const msg = extractErrorMessage(e, 'Regeneration failed.');
        setGeneratedItems((prev) =>
          prev.map((i) =>
            i.id === itemId ? { ...i, status: 'failed', error: msg } : i,
          ),
        );
      }
    },
    [generatedItems, outline, courseId, selectedModuleId],
  );

  // ── Outline manipulation ─────────────────────────────────────────────────

  const updateSection = useCallback((index: number, updated: OutlineSection) => {
    setOutline((prev) => prev.map((s, i) => (i === index ? updated : s)));
  }, []);

  const moveSection = useCallback((from: number, direction: -1 | 1) => {
    setOutline((prev) => {
      const to = from + direction;
      if (to < 0 || to >= prev.length) return prev;
      const next = [...prev];
      [next[from], next[to]] = [next[to], next[from]];
      return next;
    });
  }, []);

  const deleteSection = useCallback((index: number) => {
    setOutline((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const addSection = useCallback(() => {
    setOutline((prev) => [
      ...prev,
      {
        id: genId(),
        title: '',
        description: '',
        learningObjectives: '',
        keyPoints: [''],
        selectedTypes: new Set(selectedTypes),
      },
    ]);
  }, [selectedTypes]);

  const handleBackToInput = useCallback(() => {
    setGeneratorState('idle');
    setOutline([]);
    setGeneratedItems([]);
    setSectionProgress([]);
    setError('');
  }, []);

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div data-tour="admin-course-assignment-builder-panel" className="space-y-6">
      {/* Module Selector */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm p-5">
        <ModuleSelector
          modules={modules}
          selectedId={selectedModuleId}
          onChange={setSelectedModuleId}
        />

        {modules.length === 0 && (
          <p className="mt-2 text-xs text-amber-600">
            No modules found. Create a module in the Content tab first.
          </p>
        )}
      </div>

      {/* Unified Input Area */}
      <div
        className={`rounded-2xl border bg-white shadow-sm transition-colors ${
          isDragOver ? 'border-primary-400 border-dashed bg-primary-50/30' : 'border-gray-200'
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleFileDrop}
      >
        <div className="p-4">
          <label htmlFor="ai-input-textarea" className="sr-only">
            Describe what you want to generate, or drop a file
          </label>
          <textarea
            ref={textareaRef}
            id="ai-input-textarea"
            value={inputText}
            onChange={(e) => {
              setInputText(e.target.value);
              autoResizeTextarea();
            }}
            placeholder="Describe what you want to generate, or drop a file..."
            className="w-full bg-transparent border-0 focus:ring-0 text-sm text-gray-900 placeholder-gray-400 resize-none"
            style={{ minHeight: '120px', maxHeight: '300px' }}
            disabled={generatorState !== 'idle' && generatorState !== 'lesson-config'}
            aria-label="Input text for AI generation"
          />

          {attachedFile && (
            <FilePreviewCard
              file={attachedFile}
              onRemove={() => {
                setAttachedFile(null);
                setParsedMaterial(null);
              }}
            />
          )}
        </div>

        {/* Bottom toolbar */}
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
          <div className="flex items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={handleFileInputChange}
              aria-hidden="true"
            />
            <button
              type="button"
              onClick={() => openFilePicker()}
              className="rounded-full px-3 py-1.5 text-xs font-medium border border-gray-200 text-gray-500 hover:border-gray-300 transition-colors inline-flex items-center gap-1.5"
              disabled={generatorState !== 'idle' && generatorState !== 'lesson-config'}
              aria-label="Upload a file"
            >
              <ArrowUpTrayIcon className="h-3.5 w-3.5" />
              Upload
            </button>
            <button
              type="button"
              onClick={() => openFilePicker('.pdf')}
              className="rounded-full px-3 py-1.5 text-xs font-medium border border-gray-200 text-gray-500 hover:border-gray-300 transition-colors"
              disabled={generatorState !== 'idle' && generatorState !== 'lesson-config'}
            >
              PDF
            </button>
            <button
              type="button"
              onClick={() => openFilePicker('video/*')}
              className="rounded-full px-3 py-1.5 text-xs font-medium border border-gray-200 text-gray-500 hover:border-gray-300 transition-colors"
              disabled={generatorState !== 'idle' && generatorState !== 'lesson-config'}
            >
              Video
            </button>
            <button
              type="button"
              onClick={() => openFilePicker('.docx,.doc')}
              className="rounded-full px-3 py-1.5 text-xs font-medium border border-gray-200 text-gray-500 hover:border-gray-300 transition-colors"
              disabled={generatorState !== 'idle' && generatorState !== 'lesson-config'}
            >
              DOCX
            </button>
          </div>
        </div>
      </div>

      {/* Content Type Pills */}
      {generatorState === 'idle' && (
        <ContentTypePills selected={selectedTypes} onToggle={handleToggleType} />
      )}

      {/* Link to Lesson Builder */}
      {generatorState === 'idle' && (
        <div className="mb-4 rounded-lg border border-indigo-100 bg-indigo-50 px-4 py-3 flex items-center justify-between">
          <div className="text-sm text-indigo-700">
            <span className="font-medium">Want interactive slides?</span>{' '}
            Use the Lesson Builder for slide-based lessons with quizzes and activities.
          </div>
          <a
            href="/admin/lesson-builder"
            className="ml-3 flex-shrink-0 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 transition-colors"
          >
            Open Lesson Builder
          </a>
        </div>
      )}

      {/* Generate Button */}
      {generatorState === 'idle' && (
        <button
          type="button"
          onClick={() => void handleGenerate()}
          disabled={!canGenerate}
          className="w-full rounded-lg bg-primary-600 text-white py-2.5 font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Generate
        </button>
      )}

      {/* Error Message */}
      {error && (
        <p className="text-sm text-red-600" role="alert">{error}</p>
      )}

      {/* Loading states */}
      {(generatorState === 'parsing' || generatorState === 'generating-outline') && (
        <div className="rounded-xl border border-gray-200 bg-white p-8 flex flex-col items-center gap-3">
          <div className="h-8 w-8 rounded-full border-2 border-primary-500 border-t-transparent animate-spin" />
          <p className="text-sm text-gray-600">
            {generatorState === 'parsing' ? 'Parsing uploaded file...' : 'Generating outline...'}
          </p>
        </div>
      )}

      {/* Stage 1: Outline Review */}
      {generatorState === 'outline-ready' && (
        <div className="border-t border-gray-100 pt-6 mt-6 space-y-4">
          <h3 className="text-base font-semibold text-gray-900">Review Outline</h3>
          <p className="text-sm text-gray-500">
            Edit section titles, descriptions, and key points. Toggle which content types to generate for each section.
          </p>

          <div className="space-y-3">
            {outline.map((section, idx) => (
              <OutlineCard
                key={section.id}
                section={section}
                index={idx}
                total={outline.length}
                onUpdate={(updated) => updateSection(idx, updated)}
                onMoveUp={() => moveSection(idx, -1)}
                onMoveDown={() => moveSection(idx, 1)}
                onDelete={() => deleteSection(idx)}
              />
            ))}
          </div>

          <button
            type="button"
            onClick={addSection}
            className="w-full rounded-lg border border-dashed border-gray-300 py-2.5 text-sm font-medium text-gray-500 hover:border-gray-400 hover:text-gray-600 transition-colors inline-flex items-center justify-center gap-1.5"
          >
            <PlusIcon className="h-4 w-4" />
            Add Section
          </button>

          <div className="flex items-center justify-between pt-4">
            <button
              type="button"
              onClick={handleBackToInput}
              className="rounded-lg border border-gray-200 text-gray-600 px-4 py-2 text-sm font-medium hover:bg-gray-50 transition-colors"
            >
              Back
            </button>
            <button
              type="button"
              onClick={() => void handleGenerateContent()}
              disabled={outline.length === 0}
              className="rounded-lg bg-primary-600 text-white px-6 py-2 text-sm font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Generate Content
            </button>
          </div>
        </div>
      )}

      {/* Stage 2: Generation Progress */}
      {generatorState === 'generating-content' && (
        <div className="border-t border-gray-100 pt-6 mt-6 space-y-4">
          <h3 className="text-base font-semibold text-gray-900">Generating Content</h3>
          <div className="rounded-xl border border-gray-200 bg-white p-5">
            <GenerationProgressView sections={sectionProgress} />
          </div>
        </div>
      )}

      {/* Stage 3: Content Preview */}
      {generatorState === 'content-ready' && (
        <div className="border-t border-gray-100 pt-6 mt-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-base font-semibold text-gray-900">Generated Content</h3>
            {selectedModule && (
              <span className="text-xs text-gray-500">
                Target: {selectedModule.order}. {selectedModule.title}
              </span>
            )}
          </div>

          <div className="space-y-3">
            {generatedItems.map((item) => (
              <ContentPreviewCard
                key={item.id}
                item={item}
                onAdd={() => void handleAddToModule(item.id)}
                onRegenerate={() => void handleRegenerate(item.id)}
              />
            ))}
          </div>

          {generatedItems.some((i) => i.status === 'done' && !i.added) && (
            <button
              type="button"
              onClick={() => void handleAddAllToModule()}
              className="w-full rounded-lg bg-primary-600 text-white py-2.5 font-medium hover:bg-primary-700 transition-colors"
            >
              Add All to Module
            </button>
          )}

          <div className="pt-4">
            <button
              type="button"
              onClick={handleBackToInput}
              className="rounded-lg border border-gray-200 text-gray-600 px-4 py-2 text-sm font-medium hover:bg-gray-50 transition-colors"
            >
              Start Over
            </button>
          </div>
        </div>
      )}

      {/* Interactive Lesson functionality moved to standalone Lesson Builder page */}
    </div>
  );
};
