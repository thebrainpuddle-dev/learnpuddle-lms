// src/components/maic/GenerationWizard.tsx
//
// Multi-step wizard for creating a new AI classroom. Steps: topic input,
// outline review, generation progress, and completion with preview.

import React, { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { useToast } from '../common/Toast';
import { AnimatePresence, motion } from 'motion/react';
import {
  BookOpen,
  ChevronRight,
  ChevronLeft,
  Loader2,
  CheckCircle,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  Play,
  Globe,
} from 'lucide-react';
import { useMAICGeneration, type GenerationStep } from '../../hooks/useMAICGeneration';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useDraftCache } from '../../hooks/useDraftCache';
import { maicApi } from '../../services/openmaicService';
import type { MAICAgent, MAICGenerationConfig, MAICOutlineScene } from '../../types/maic';
import { AgentGenerationStep } from './AgentGenerationStep';
import { OutlineEditor } from './OutlineEditor';
import { PDFUploader } from './PDFUploader';
import { GenerationVisualizer } from './GenerationVisualizer';
import { WebSearchPanel } from './WebSearchPanel';
import { cn } from '../../lib/utils';

interface GenerationWizardProps {
  courseId?: string;
  onComplete?: (classroomId: string) => void;
}

/**
 * Wizard steps:
 *   1 = Topic & Settings
 *   2 = Meet your classroom (agent picker, added by WS-C)
 *   3 = Review outline
 *   4 = Generating content
 *   5 = Complete
 */
type WizardStep = 1 | 2 | 3 | 4 | 5;

const LANGUAGES = [
  { value: 'en', label: 'English' },
  { value: 'hi', label: 'Hindi' },
  { value: 'es', label: 'Spanish' },
  { value: 'fr', label: 'French' },
  { value: 'de', label: 'German' },
  { value: 'pt', label: 'Portuguese' },
  { value: 'zh', label: 'Chinese' },
  { value: 'ja', label: 'Japanese' },
  { value: 'ko', label: 'Korean' },
  { value: 'ar', label: 'Arabic' },
];

// FULL-1 — grade-aware prompt knobs. Backend `_extract_generation_context`
// at apps/courses/maic_views.py:84-113 only `.strip()`s these values, so
// the canonical lists below are pure UX hygiene; any string the user types
// in `subject` flows through verbatim.
const GRADE_LEVELS = [
  '',
  'KG',
  'Grade 1',
  'Grade 2',
  'Grade 3',
  'Grade 4',
  'Grade 5',
  'Grade 6',
  'Grade 7',
  'Grade 8',
  'Grade 9',
  'Grade 10',
  'Grade 11',
  'Grade 12',
  'Undergraduate',
  'Postgraduate',
  'Adult Learner',
];

const SYLLABUS_BOARDS = [
  'Generic',
  'CBSE',
  'ICSE',
  'IB MYP',
  'IB DP',
  'Cambridge IGCSE',
  'Cambridge A-Level',
  'State Board',
  'AP',
  'Common Core',
];

const SUBJECT_SUGGESTIONS = [
  'Mathematics',
  'Science',
  'Physics',
  'Chemistry',
  'Biology',
  'English',
  'History',
  'Geography',
  'Computer Science',
  'Economics',
  'Social Studies',
  'Art',
  'Music',
  'Physical Education',
];

function stepFromGeneration(genStep: GenerationStep, currentWizardStep: WizardStep): WizardStep {
  // The wizard's 5 steps are: 1 Topic & Settings, 2 Meet your classroom,
  // 3 Review Outline, 4 Generating, 5 Complete. The generation hook only
  // owns steps 3-5 (outline + content phases); steps 1-2 are pre-generation
  // UI owned by the wizard itself. The switch below maps hook state →
  // displayed step, respecting the wizard's own cursor for everything the
  // hook doesn't know about.
  switch (genStep) {
    case 'idle':
      // Hook hasn't started — user may be on Topic (1) or Agents (2).
      // Step 3+ without a hook phase is nonsense; snap back to Topic.
      return currentWizardStep <= 2 ? currentWizardStep : 1;
    case 'outlining':
      return currentWizardStep >= 2 ? currentWizardStep : 1;
    case 'editing':
      return currentWizardStep >= 3 ? currentWizardStep : 3;
    case 'generating':
      return 4;
    case 'complete':
      return 5;
    case 'error':
      return currentWizardStep;
    default:
      return currentWizardStep;
  }
}

const STEP_LABELS = [
  'Topic & Settings',
  'Meet your classroom',
  'Review Outline',
  'Generating',
  'Complete',
];

export const GenerationWizard: React.FC<GenerationWizardProps> = ({ courseId, onComplete }) => {
  // Form state. Topic persists to localStorage so a surprise refresh
  // during generation doesn't erase the typed prompt. Cleared on reset.
  const { value: topic, setValue: setTopic, clearDraft: clearTopicDraft } =
    useDraftCache<string>('maic.draft.topic', '');
  // FULL-1 — grade / subject / syllabus board persist alongside topic so a
  // refresh during generation doesn't wipe them. Cache key bumped to v2 to
  // avoid colliding with any pre-existing draft cache schema. Each field is
  // independent so dropping one doesn't invalidate the others.
  const { value: gradeLevel, setValue: setGradeLevel, clearDraft: clearGradeDraft } =
    useDraftCache<string>('maic.draft.gradeLevel.v2', '');
  const { value: subject, setValue: setSubject, clearDraft: clearSubjectDraft } =
    useDraftCache<string>('maic.draft.subject.v2', '');
  const { value: syllabusBoard, setValue: setSyllabusBoard, clearDraft: clearBoardDraft } =
    useDraftCache<string>('maic.draft.syllabusBoard.v2', 'Generic');
  const [pdfText, setPdfText] = useState<string | undefined>();
  const [language, setLanguage] = useState('en');
  const [agentCount, setAgentCount] = useState(3);
  const [sceneCount, setSceneCount] = useState(6);
  const [classroomId, setClassroomId] = useState<string | null>(null);
  const [wizardStep, setWizardStep] = useState<WizardStep>(1);
  // Agents chosen on the "Meet your classroom" step (WS-C) — become the
  // authoritative roster for outline + scene-content + scene-actions.
  const [agents, setAgents] = useState<MAICAgent[]>([]);

  // Web search state.
  // `webSearchEnabled` is the ON/OFF toggle (default ON, OpenMAIC parity) —
  // instructs the backend to auto-enrich the outline with search context.
  // `showWebSearch` opens the manual-search panel for power users who want
  // to curate context themselves; the manual context then rides along in
  // `webSearchContext`.
  const [webSearchEnabled, setWebSearchEnabled] = useState(true);
  const [showWebSearch, setShowWebSearch] = useState(false);
  const [webSearchContext, setWebSearchContext] = useState<string | undefined>();

  const {
    step: genStep,
    phase,
    currentSceneIdx,
    totalScenes,
    outline,
    progress,
    error,
    startedAt,
    isTabHidden,
    firstSceneReadyAt,
    startOutlineGeneration,
    updateOutline,
    startContentGeneration,
    retryScene,
    cancel,
    reset: resetGeneration,
  } = useMAICGeneration();

  // Derive effective step (sync wizard step with generation state)
  const effectiveStep = stepFromGeneration(genStep, wizardStep);

  // T4 — scenes whose generation failed. Rendered as a "Some scenes
  // need a retry" callout inside step 4 + 5 with per-scene retry buttons.
  const failedOutlineIds = useMAICStageStore((s) => s.failedOutlineIds);
  // CG-P1-4 (2026-04-27): mirror the approved agent roster into the
  // shared stage store so `Stage` (which renders during partial
  // generation per `MAICPlayerPage` resume flows) has agent metadata
  // immediately. Previously the store's `agents` stayed empty until
  // `useMAICGeneration.startContentGeneration`'s success path, which
  // meant any mid-generation partial scene rendered with no agent
  // identity. Both stores still own their data independently — this
  // is a write-through, not a unification.
  const setStoreAgents = useMAICStageStore((s) => s.setAgents);
  const failedScenes = useMemo(() => {
    if (!outline) return [];
    const failedSet = new Set(failedOutlineIds);
    return outline.scenes.filter((s) => failedSet.has(s.id));
  }, [outline, failedOutlineIds]);

  // Sprint 3 · C.6 — surface generation failures as toasts so an error
  // isn't only visible in the inline banner (easy to miss when the user
  // has tabbed away). Dedupe against `lastToastedError` so the same
  // error doesn't re-toast on every render.
  const toast = useToast();
  const lastToastedErrorRef = useRef<string | null>(null);
  useEffect(() => {
    if (error && error !== lastToastedErrorRef.current) {
      lastToastedErrorRef.current = error;
      toast.error('Generation failed', error);
    }
    if (!error) lastToastedErrorRef.current = null;
  }, [error, toast]);
  // Fire a success toast the first time we land on the complete step.
  const successToastedRef = useRef(false);
  useEffect(() => {
    if (genStep === 'complete' && !successToastedRef.current) {
      successToastedRef.current = true;
      toast.success('Classroom ready', outline?.topic);
    }
    if (genStep !== 'complete') successToastedRef.current = false;
  }, [genStep, outline?.topic, toast]);

  // ─── Step 1: Generate outline ─────────────────────────────────────────────

  // ─── Web search context insertion ──────────────────────────────────────────

  const handleInsertWebContext = useCallback((context: string) => {
    setWebSearchContext((prev) => (prev ? `${prev}\n\n${context}` : context));
  }, []);

  // Step 1 → Step 2 (agents). We defer outline generation until the user
  // approves the agent roster so the outline can use it.
  const handleGoToAgents = useCallback(() => {
    if (!topic.trim()) return;
    setWizardStep(2);
  }, [topic]);

  // Step 2 → Step 3 (outline). Starts outline generation using the approved
  // agents[] as input, then moves the wizard to the outline-review step.
  const handleAgentsComplete = useCallback(
    async (approvedAgents: MAICAgent[]) => {
      setAgents(approvedAgents);
      // CG-P1-4: write-through to the shared store so Stage renders
      // partial scenes with proper agent identity from the moment
      // generation starts. See the setStoreAgents declaration comment.
      setStoreAgents(approvedAgents);
      setAgentCount(approvedAgents.length);

      // Combine PDF text and web search context for richer generation.
      const combinedContext =
        [pdfText, webSearchContext].filter(Boolean).join('\n\n---\n\n') || undefined;

      const config: MAICGenerationConfig = {
        topic: topic.trim(),
        pdfText: combinedContext,
        enableWebSearch: webSearchEnabled,
        language,
        agentCount: approvedAgents.length,
        sceneCount,
        enableTTS: true,
        enableImages: true,
        courseId,
        // FULL-1 — only thread non-empty values; backend defaults handle
        // the rest. Empty strings would land as a garbage grade hint.
        gradeLevel: gradeLevel.trim() || undefined,
        subject: subject.trim() || undefined,
        syllabusBoard: syllabusBoard.trim() || undefined,
      };

      setWizardStep(3);
      await startOutlineGeneration(config, approvedAgents);
    },
    [
      topic,
      pdfText,
      webSearchContext,
      webSearchEnabled,
      language,
      sceneCount,
      courseId,
      gradeLevel,
      subject,
      syllabusBoard,
      startOutlineGeneration,
      setStoreAgents,
    ],
  );

  // ─── Step 2: Start full generation ────────────────────────────────────────

  const handleStartGeneration = useCallback(async () => {
    if (!outline) return;

    try {
      // Create classroom record in backend
      const res = await maicApi.createClassroom({
        title: outline.topic,
        topic: outline.topic,
        language: outline.language,
        course_id: courseId,
        // FULL-1 — also send grade-aware fields at top level (snake_case)
        // so the create endpoint can stamp them on the Classroom record
        // and downstream regenerations/exports keep the same audience.
        ...(gradeLevel.trim() ? { grade_level: gradeLevel.trim() } : {}),
        ...(subject.trim() ? { subject: subject.trim() } : {}),
        ...(syllabusBoard.trim() ? { syllabus_board: syllabusBoard.trim() } : {}),
        config: {
          agentCount,
          sceneCount: outline.scenes.length,
          ...(gradeLevel.trim() ? { grade_level: gradeLevel.trim() } : {}),
          ...(subject.trim() ? { subject: subject.trim() } : {}),
          ...(syllabusBoard.trim() ? { syllabus_board: syllabusBoard.trim() } : {}),
        },
      });

      const newId = res.data.id;
      setClassroomId(newId);
      setWizardStep(4);

      await startContentGeneration(newId);
    } catch (err) {
      // Error is handled inside useMAICGeneration
    }
  }, [outline, courseId, agentCount, gradeLevel, subject, syllabusBoard, startContentGeneration]);

  // ─── Step 4: Open classroom ───────────────────────────────────────────────

  const handleOpenClassroom = useCallback(() => {
    if (classroomId) {
      // Successful submission — drop the cached draft so the next
      // classroom starts on a clean slate.
      clearTopicDraft();
      clearGradeDraft();
      clearSubjectDraft();
      clearBoardDraft();
      onComplete?.(classroomId);
    }
  }, [classroomId, onComplete, clearTopicDraft, clearGradeDraft, clearSubjectDraft, clearBoardDraft]);

  // ─── Outline change handler ───────────────────────────────────────────────

  const handleOutlineChange = useCallback(
    (scenes: MAICOutlineScene[]) => {
      updateOutline(scenes);
    },
    [updateOutline],
  );

  // ─── Reset ────────────────────────────────────────────────────────────────

  const handleReset = useCallback(() => {
    resetGeneration();
    clearTopicDraft();
    clearGradeDraft();
    clearSubjectDraft();
    clearBoardDraft();
    setPdfText(undefined);
    setLanguage('en');
    setAgentCount(3);
    setSceneCount(6);
    setClassroomId(null);
    setAgents([]);
    setWizardStep(1);
    setShowWebSearch(false);
    setWebSearchContext(undefined);
  }, [resetGeneration, clearTopicDraft, clearGradeDraft, clearSubjectDraft, clearBoardDraft]);

  return (
    <div className="max-w-2xl mx-auto">
      {/* Progress steps */}
      <nav className="mb-8" aria-label="Wizard progress">
        <ol className="flex items-center">
          {STEP_LABELS.map((label, i) => {
            const stepNum = (i + 1) as WizardStep;
            const isActive = effectiveStep === stepNum;
            const isCompleted = effectiveStep > stepNum;

            return (
              <li key={label} className="flex-1 flex items-center">
                <div className="flex items-center gap-2 w-full">
                  <span
                    className={cn(
                      'shrink-0 flex items-center justify-center h-7 w-7 rounded-full text-xs font-medium transition-colors',
                      isCompleted && 'bg-green-500 text-white',
                      isActive && 'bg-primary-600 text-white',
                      !isActive && !isCompleted && 'bg-gray-200 text-gray-500',
                    )}
                  >
                    {isCompleted ? (
                      <CheckCircle className="h-4 w-4" />
                    ) : (
                      stepNum
                    )}
                  </span>
                  <span
                    className={cn(
                      'text-xs font-medium hidden sm:inline',
                      isActive ? 'text-gray-900' : 'text-gray-400',
                    )}
                  >
                    {label}
                  </span>
                </div>
                {i < STEP_LABELS.length - 1 && (
                  <div
                    className={cn(
                      'flex-1 h-0.5 mx-2',
                      isCompleted ? 'bg-green-400' : 'bg-gray-200',
                    )}
                    aria-hidden="true"
                  />
                )}
              </li>
            );
          })}
        </ol>
      </nav>

      {/* Error banner */}
      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 flex items-start gap-2" role="alert">
          <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
          <div className="min-w-0">
            <p className="text-sm text-red-700">{error}</p>
            <button
              type="button"
              onClick={handleReset}
              className="text-xs text-red-500 underline hover:text-red-700 mt-1"
            >
              Start over
            </button>
          </div>
        </div>
      )}

      {/* ─── Step 1: Topic Input ───────────────────────────────────────────── */}
      {effectiveStep === 1 && (
        <div className="space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 mb-1">Create AI Classroom</h2>
            <p className="text-sm text-gray-500">Enter a topic and configure your classroom settings.</p>
          </div>

          {/* Topic */}
          <div>
            <label htmlFor="maic-topic" className="block text-sm font-medium text-gray-700 mb-1">
              Topic <span className="text-red-500">*</span>
            </label>
            <input
              id="maic-topic"
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g., Introduction to Machine Learning"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              autoFocus
            />
          </div>

          {/* PDF upload (optional) */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Reference PDF <span className="text-xs text-gray-400">(optional)</span>
            </label>
            <PDFUploader onExtract={setPdfText} />
          </div>

          {/* Web search enrichment */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm font-medium text-gray-700 flex items-center gap-1.5">
                <Globe className={cn('h-4 w-4', webSearchEnabled ? 'text-indigo-600' : 'text-gray-400')} />
                Enrich with web search
                <span className="text-xs text-gray-400 font-normal">
                  ({webSearchEnabled ? 'ON — grounds the outline with live context' : 'OFF'})
                </span>
              </label>
              <button
                type="button"
                onClick={() => setWebSearchEnabled((v) => !v)}
                className={cn(
                  'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
                  webSearchEnabled ? 'bg-indigo-600' : 'bg-gray-200',
                )}
                role="switch"
                aria-checked={webSearchEnabled}
                aria-label="Toggle web search enrichment"
              >
                <span
                  className={cn(
                    'inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform',
                    webSearchEnabled ? 'translate-x-4.5' : 'translate-x-0.5',
                  )}
                />
              </button>
            </div>

            <button
              type="button"
              onClick={() => setShowWebSearch((v) => !v)}
              className="text-[11px] text-indigo-600 hover:text-indigo-700 underline-offset-2 hover:underline"
            >
              {showWebSearch ? 'Hide manual search panel' : 'Curate search context manually (advanced)'}
            </button>

            {showWebSearch && (
              <div className="mt-2">
                <WebSearchPanel onInsertContext={handleInsertWebContext} role="teacher" />
                {webSearchContext && (
                  <div className="mt-2 rounded-lg bg-indigo-50 border border-indigo-100 px-3 py-2">
                    <div className="flex items-center justify-between">
                      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-indigo-700">
                        <Globe className="h-3 w-3" />
                        Web context added
                      </span>
                      <button
                        type="button"
                        onClick={() => setWebSearchContext(undefined)}
                        className="text-[10px] text-indigo-400 hover:text-indigo-600 transition-colors"
                      >
                        Clear
                      </button>
                    </div>
                    <p className="text-[11px] text-indigo-600 mt-1 line-clamp-2">
                      {webSearchContext.slice(0, 150)}
                      {webSearchContext.length > 150 && '...'}
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Language */}
          <div>
            <label htmlFor="maic-language" className="block text-sm font-medium text-gray-700 mb-1">
              Language
            </label>
            <select
              id="maic-language"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            >
              {LANGUAGES.map((lang) => (
                <option key={lang.value} value={lang.value}>
                  {lang.label}
                </option>
              ))}
            </select>
          </div>

          {/* FULL-1 — Audience shaping (all optional). Backend defaults to
              Generic syllabus / no grade hint when omitted; values flow into
              the grade-aware prompt builder via _extract_generation_context. */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <label htmlFor="maic-grade-level" className="block text-sm font-medium text-gray-700 mb-1">
                Grade level <span className="text-xs text-gray-400 font-normal">(optional)</span>
              </label>
              <select
                id="maic-grade-level"
                value={gradeLevel}
                onChange={(e) => setGradeLevel(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              >
                {GRADE_LEVELS.map((g) => (
                  <option key={g || 'none'} value={g}>
                    {g || 'No preference'}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="maic-subject" className="block text-sm font-medium text-gray-700 mb-1">
                Subject <span className="text-xs text-gray-400 font-normal">(optional)</span>
              </label>
              <input
                id="maic-subject"
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="e.g., Mathematics"
                list="maic-subject-suggestions"
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              />
              <datalist id="maic-subject-suggestions">
                {SUBJECT_SUGGESTIONS.map((s) => (
                  <option key={s} value={s} />
                ))}
              </datalist>
            </div>

            <div>
              <label htmlFor="maic-syllabus-board" className="block text-sm font-medium text-gray-700 mb-1">
                Syllabus board
              </label>
              <select
                id="maic-syllabus-board"
                value={syllabusBoard}
                onChange={(e) => setSyllabusBoard(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              >
                {SYLLABUS_BOARDS.map((b) => (
                  <option key={b} value={b}>
                    {b}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Agent count slider */}
          <div>
            <label htmlFor="maic-agents" className="flex items-center justify-between text-sm font-medium text-gray-700 mb-1">
              <span>AI Agents</span>
              <span className="text-gray-500 font-normal">{agentCount}</span>
            </label>
            <input
              id="maic-agents"
              type="range"
              min={2}
              max={5}
              value={agentCount}
              onChange={(e) => setAgentCount(parseInt(e.target.value, 10))}
              className="w-full h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-primary-600"
            />
            <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
              <span>2</span>
              <span>5</span>
            </div>
          </div>

          {/* Scene count slider */}
          <div>
            <label htmlFor="maic-scenes" className="flex items-center justify-between text-sm font-medium text-gray-700 mb-1">
              <span>Number of Scenes</span>
              <span className="text-gray-500 font-normal">{sceneCount}</span>
            </label>
            <input
              id="maic-scenes"
              type="range"
              min={3}
              max={15}
              value={sceneCount}
              onChange={(e) => setSceneCount(parseInt(e.target.value, 10))}
              className="w-full h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-primary-600"
            />
            <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
              <span>3</span>
              <span>15</span>
            </div>
          </div>

          {/* Actions */}
          <div className="flex justify-end pt-2">
            <button
              type="button"
              onClick={handleGoToAgents}
              disabled={!topic.trim()}
              className={cn(
                'inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium',
                'bg-primary-600 text-white hover:bg-primary-700',
                'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                'transition-colors',
              )}
            >
              <Sparkles className="h-4 w-4" />
              Meet your classroom
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* ─── Step 2: Meet your classroom (agent picker) ───────────────────── */}
      {effectiveStep === 2 && (
        <AgentGenerationStep
          topic={topic}
          language={language}
          role="teacher"
          initialAgents={agents.length > 0 ? agents : undefined}
          onBack={() => setWizardStep(1)}
          onComplete={(approvedAgents) => void handleAgentsComplete(approvedAgents)}
        />
      )}

      {/* ─── Step 3: Outline streaming — Sprint 2 · A.2 ──────────────────────
          Each SSE `outline` event grows the scene list; we render the
          latest snapshot as a growing checklist so the student can watch
          their outline materialize instead of staring at a spinner. */}
      {effectiveStep === 3 && (!outline || genStep === 'outlining') && (
        <div className="py-8">
          <div className="text-center mb-6">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100">
              <Loader2 className="h-6 w-6 animate-spin text-indigo-500" />
            </div>
            <h2 className="text-lg font-semibold text-gray-900">Building your outline…</h2>
            <p className="mt-1 text-sm text-gray-500">
              Arranging scenes for {agents.length} agent{agents.length === 1 ? '' : 's'}.
            </p>
            {progress > 0 && (
              <div className="mx-auto mt-4 w-56">
                <div className="w-full bg-indigo-100 rounded-full h-1 overflow-hidden">
                  <div
                    className="h-1 rounded-full bg-gradient-to-r from-indigo-500 to-indigo-400 transition-all duration-700"
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </div>
            )}
          </div>

          {outline && outline.scenes.length > 0 && (
            <ol className="mx-auto max-w-lg space-y-2">
              <AnimatePresence initial={false}>
                {outline.scenes.map((scene, i) => (
                  <motion.li
                    key={`${scene.title || 'scene'}-${i}`}
                    layout
                    initial={{ opacity: 0, x: -16 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.25, ease: [0.21, 1, 0.36, 1] }}
                    className="flex items-start gap-3 rounded-lg border border-indigo-100 bg-white px-3 py-2 shadow-sm"
                  >
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-indigo-500" />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-gray-800 truncate">
                        {scene.title || `Scene ${i + 1}`}
                      </p>
                      {scene.description && (
                        <p className="text-xs text-gray-500 line-clamp-2 mt-0.5">
                          {scene.description}
                        </p>
                      )}
                    </div>
                    <span className="text-[10px] font-medium tabular-nums text-gray-400">
                      {i + 1}
                    </span>
                  </motion.li>
                ))}
              </AnimatePresence>
            </ol>
          )}
        </div>
      )}

      {effectiveStep === 3 && outline && genStep !== 'outlining' && (
        <div className="space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 mb-1">Review Outline</h2>
            <p className="text-sm text-gray-500">
              Edit the scene order, titles, and descriptions. Add or remove scenes as needed.
            </p>
          </div>

          <OutlineEditor outline={outline} onChange={handleOutlineChange} />

          {/* Actions */}
          <div className="flex justify-between pt-2">
            <button
              type="button"
              onClick={() => {
                // Back from outline-review → agent picker. Keep the approved
                // roster so the user can tweak it without losing their edits.
                resetGeneration();
                setWizardStep(2);
              }}
              className={cn(
                'inline-flex items-center gap-1 rounded-lg px-4 py-2 text-sm font-medium',
                'text-gray-600 hover:bg-gray-100',
                'focus:outline-none focus:ring-2 focus:ring-primary-500',
                'transition-colors',
              )}
            >
              <ChevronLeft className="h-4 w-4" />
              Back
            </button>
            <button
              type="button"
              onClick={handleStartGeneration}
              className={cn(
                'inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium',
                'bg-primary-600 text-white hover:bg-primary-700',
                'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
                'transition-colors',
              )}
            >
              <BookOpen className="h-4 w-4" />
              Generate Classroom
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* ─── Step 4: Generation Progress ───────────────────────────────────── */}
      {effectiveStep === 4 && (
        <div className="py-6 space-y-6">
          <GenerationVisualizer
            phase={phase}
            currentSceneIdx={currentSceneIdx}
            totalScenes={totalScenes}
            progress={progress}
            topic={outline?.topic}
            startedAt={startedAt ?? undefined}
            isTabHidden={isTabHidden}
          />

          {/* T4 — failed-scene callout. Lists any scenes whose content
              or actions failed to generate and exposes per-scene retry.
              Non-blocking: remaining scenes keep going via per-iteration
              try/catch so one flaky LLM call doesn't abort the pipeline. */}
          {failedScenes.length > 0 && (
            <div className="mx-auto max-w-md rounded-lg border border-red-200 bg-red-50 px-3 py-2 space-y-1.5">
              <div className="flex items-start gap-2">
                <AlertCircle className="h-4 w-4 shrink-0 text-red-500 mt-0.5" />
                <p className="text-xs font-medium text-red-800">
                  {failedScenes.length} scene{failedScenes.length === 1 ? '' : 's'} need retry
                </p>
              </div>
              <ul className="pl-6 space-y-1">
                {failedScenes.map((s) => (
                  <li key={s.id} className="flex items-center justify-between gap-2">
                    <span className="text-[11px] text-red-700 truncate">
                      {s.title || s.id}
                    </span>
                    <button
                      type="button"
                      onClick={() => void retryScene(s.id)}
                      className="shrink-0 text-[10px] font-semibold text-red-700 hover:text-red-900 bg-white border border-red-200 rounded px-1.5 py-0.5 hover:bg-red-50 transition-colors"
                    >
                      Retry
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Scene 1 ready notice — informational only. The "Open classroom"
              button was removed here: user feedback said early-open produced
              broken/incomplete playback (audio lag, partial content). The
              classroom only opens once generation fully completes (step 5).
              Partial-state streaming into the store is kept (live scenes
              render as they arrive if the teacher watches the wizard). */}
          {firstSceneReadyAt && totalScenes > 1 && classroomId && (
            <div className="mx-auto max-w-md rounded-lg border border-emerald-100 bg-emerald-50 px-3 py-3 flex items-start gap-2">
              <CheckCircle className="h-4 w-4 shrink-0 text-emerald-500 mt-0.5" />
              <div className="min-w-0">
                <p className="text-xs font-medium text-emerald-800">
                  Scene 1 is ready
                </p>
                <p className="text-[11px] text-emerald-700/80 mt-0.5">
                  Preparing the rest of the class. The classroom will open automatically when all scenes finish.
                </p>
              </div>
            </div>
          )}

          <div className="text-center">
            <button
              type="button"
              onClick={cancel}
              className="text-sm text-gray-400 hover:text-red-500 transition-colors"
            >
              Cancel generation
            </button>
          </div>
        </div>
      )}

      {/* ─── Step 5: Complete ──────────────────────────────────────────────── */}
      {effectiveStep === 5 && (
        <div className="space-y-6 text-center py-8 animate-scale-in">
          <div className="relative inline-flex items-center justify-center mx-auto">
            <div className="absolute h-20 w-20 rounded-full bg-green-100 animate-ping opacity-20" />
            <div className="relative h-16 w-16 rounded-full bg-gradient-to-br from-green-50 to-green-100 flex items-center justify-center shadow-sm border border-green-200">
              <CheckCircle className="h-8 w-8 text-green-500" />
            </div>
          </div>

          <div>
            <h2 className="text-lg font-semibold text-gray-900 mb-1">Classroom Ready!</h2>
            <p className="text-sm text-gray-500">
              Your AI classroom has been generated successfully.
            </p>
            {outline && (
              <div className="flex items-center justify-center gap-3 mt-2">
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-50 text-[11px] font-medium text-indigo-600">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6Z" />
                  </svg>
                  {outline.scenes.length} scenes
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 text-[11px] font-medium text-amber-600">
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
                  </svg>
                  ~{outline.totalMinutes} min
                </span>
                {outline.agents?.length > 0 && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-50 text-[11px] font-medium text-purple-600">
                    <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z" />
                    </svg>
                    {outline.agents.length} agents
                  </span>
                )}
              </div>
            )}
          </div>

          <div className="flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={handleReset}
              className={cn(
                'inline-flex items-center gap-1 rounded-lg px-4 py-2 text-sm font-medium',
                'text-gray-600 hover:bg-gray-100 border border-gray-200',
                'focus:outline-none focus:ring-2 focus:ring-primary-500',
                'transition-colors',
              )}
            >
              Create Another
            </button>
            <button
              type="button"
              onClick={handleOpenClassroom}
              className={cn(
                'inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium',
                'bg-primary-600 text-white hover:bg-primary-700',
                'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
                'transition-colors',
              )}
            >
              <Play className="h-4 w-4" />
              Open Classroom
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
