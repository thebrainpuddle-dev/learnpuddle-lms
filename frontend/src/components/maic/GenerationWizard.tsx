// src/components/maic/GenerationWizard.tsx
//
// Multi-step wizard for creating a new AI classroom. Steps: topic input,
// outline review, generation progress, and completion with preview.

import React, { useState, useCallback } from 'react';
import {
  BookOpen,
  ChevronRight,
  ChevronLeft,
  Loader2,
  CheckCircle,
  AlertCircle,
  Sparkles,
  Play,
  Globe,
} from 'lucide-react';
import { useMAICGeneration, type GenerationStep } from '../../hooks/useMAICGeneration';
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

function stepFromGeneration(genStep: GenerationStep, currentWizardStep: WizardStep): WizardStep {
  // Once the user has advanced past "Topic & Settings", respect the wizard's
  // own step cursor. This keeps us on the new agent-picker step (2) while the
  // outline hook is still in 'outlining' or 'editing'.
  switch (genStep) {
    case 'idle':
      return 1;
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
  // Form state
  const [topic, setTopic] = useState('');
  const [pdfText, setPdfText] = useState<string | undefined>();
  const [language, setLanguage] = useState('en');
  const [agentCount, setAgentCount] = useState(3);
  const [sceneCount, setSceneCount] = useState(6);
  const [classroomId, setClassroomId] = useState<string | null>(null);
  const [wizardStep, setWizardStep] = useState<WizardStep>(1);
  // Agents chosen on the "Meet your classroom" step (WS-C) — become the
  // authoritative roster for outline + scene-content + scene-actions.
  const [agents, setAgents] = useState<MAICAgent[]>([]);

  // Web search state
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
    startOutlineGeneration,
    updateOutline,
    startContentGeneration,
    cancel,
    reset: resetGeneration,
  } = useMAICGeneration();

  // Derive effective step (sync wizard step with generation state)
  const effectiveStep = stepFromGeneration(genStep, wizardStep);

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
      setAgentCount(approvedAgents.length);

      // Combine PDF text and web search context for richer generation.
      const combinedContext =
        [pdfText, webSearchContext].filter(Boolean).join('\n\n---\n\n') || undefined;

      const config: MAICGenerationConfig = {
        topic: topic.trim(),
        pdfText: combinedContext,
        language,
        agentCount: approvedAgents.length,
        sceneCount,
        enableTTS: true,
        enableImages: true,
        courseId,
      };

      setWizardStep(3);
      await startOutlineGeneration(config, approvedAgents);
    },
    [topic, pdfText, webSearchContext, language, sceneCount, courseId, startOutlineGeneration],
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
        config: {
          agentCount,
          sceneCount: outline.scenes.length,
        },
      });

      const newId = res.data.id;
      setClassroomId(newId);
      setWizardStep(4);

      await startContentGeneration(newId);
    } catch (err) {
      // Error is handled inside useMAICGeneration
    }
  }, [outline, courseId, agentCount, startContentGeneration]);

  // ─── Step 4: Open classroom ───────────────────────────────────────────────

  const handleOpenClassroom = useCallback(() => {
    if (classroomId) {
      onComplete?.(classroomId);
    }
  }, [classroomId, onComplete]);

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
    setTopic('');
    setPdfText(undefined);
    setLanguage('en');
    setAgentCount(3);
    setSceneCount(6);
    setClassroomId(null);
    setAgents([]);
    setWizardStep(1);
    setShowWebSearch(false);
    setWebSearchContext(undefined);
  }, [resetGeneration]);

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

          {/* Web search toggle + panel */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="block text-sm font-medium text-gray-700">
                Enrich with web search <span className="text-xs text-gray-400">(optional)</span>
              </label>
              <button
                type="button"
                onClick={() => setShowWebSearch(!showWebSearch)}
                className={cn(
                  'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
                  showWebSearch ? 'bg-indigo-600' : 'bg-gray-200',
                )}
                role="switch"
                aria-checked={showWebSearch}
                aria-label="Toggle web search"
              >
                <span
                  className={cn(
                    'inline-block h-3.5 w-3.5 rounded-full bg-white shadow-sm transition-transform',
                    showWebSearch ? 'translate-x-4.5' : 'translate-x-0.5',
                  )}
                />
              </button>
            </div>

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

      {/* ─── Step 3: Outline Review ────────────────────────────────────────── */}
      {effectiveStep === 3 && (!outline || genStep === 'outlining') && (
        <div className="py-10 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100">
            <Loader2 className="h-6 w-6 animate-spin text-indigo-500" />
          </div>
          <h2 className="text-lg font-semibold text-gray-900">Building your outline…</h2>
          <p className="mt-1 text-sm text-gray-500">
            Arranging scenes for {agents.length} agent{agents.length === 1 ? '' : 's'}.
          </p>
          {progress > 0 && (
            <div className="mx-auto mt-5 w-56">
              <div className="w-full bg-indigo-100 rounded-full h-1 overflow-hidden">
                <div
                  className="h-1 rounded-full bg-gradient-to-r from-indigo-500 to-indigo-400 transition-all duration-700"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
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
          />

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
