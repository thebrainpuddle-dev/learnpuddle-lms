// src/components/maic/StudentGenerationWizard.tsx
//
// Student version of GenerationWizard with guardrail validation.
// Topic/PDF is validated through content guardrails before outline generation.
// Caps: max 4 agents, max 8 scenes.

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
  ShieldCheck,
} from 'lucide-react';
import { useStudentMAICGeneration, type StudentGenerationStep } from '../../hooks/useStudentMAICGeneration';
import type { GenerationPhase } from '../../hooks/useMAICGeneration';
import { maicStudentApi } from '../../services/openmaicService';
import type { MAICAgent, MAICGenerationConfig, MAICOutlineScene } from '../../types/maic';
import { AgentGenerationStep } from './AgentGenerationStep';
import { OutlineEditor } from './OutlineEditor';
import { PDFUploader } from './PDFUploader';
import { GenerationVisualizer } from './GenerationVisualizer';
import { cn } from '../../lib/utils';

interface StudentGenerationWizardProps {
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

function stepFromGeneration(genStep: StudentGenerationStep, currentWizardStep: WizardStep): WizardStep {
  // Steps 1 (Topic) and 2 (Agents) are pre-generation — the hook is still
  // 'idle' at those points. Steps 3-5 are driven by the generation hook
  // phase. The 'idle' branch must respect wizardStep up to 2, otherwise
  // clicking "Meet your classroom" silently resets back to Topic.
  switch (genStep) {
    case 'idle':
      return currentWizardStep <= 2 ? currentWizardStep : 1;
    case 'validating':
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

export const StudentGenerationWizard: React.FC<StudentGenerationWizardProps> = ({ onComplete }) => {
  const [topic, setTopic] = useState('');
  const [pdfText, setPdfText] = useState<string | undefined>();
  const [language, setLanguage] = useState('en');
  const [agentCount, setAgentCount] = useState(3);
  const [sceneCount, setSceneCount] = useState(5);
  const [classroomId, setClassroomId] = useState<string | null>(null);
  const [wizardStep, setWizardStep] = useState<WizardStep>(1);
  // Agents chosen in the "Meet your classroom" wizard step (WS-C).
  const [agents, setAgents] = useState<MAICAgent[]>([]);

  const {
    step: genStep,
    phase,
    currentSceneIdx,
    totalScenes,
    outline,
    progress,
    error,
    guardrailResult,
    validateAndStartOutline,
    updateOutline,
    startContentGeneration,
    cancel,
    reset: resetGeneration,
  } = useStudentMAICGeneration();

  const effectiveStep = stepFromGeneration(genStep, wizardStep);

  // Step 1 → Step 2 (agents). Outline generation runs once the roster is
  // approved so the backend can condition scenes on the chosen personas.
  const handleGoToAgents = useCallback(() => {
    if (!topic.trim()) return;
    setWizardStep(2);
  }, [topic]);

  // Step 2 → Step 3 (outline). Validates the topic (student guardrail) and
  // starts outline generation using the wizard-approved roster.
  const handleAgentsComplete = useCallback(
    async (approvedAgents: MAICAgent[]) => {
      setAgents(approvedAgents);
      setAgentCount(approvedAgents.length);

      const config: MAICGenerationConfig = {
        topic: topic.trim(),
        pdfText,
        language,
        agentCount: Math.min(approvedAgents.length, 4),
        sceneCount: Math.min(sceneCount, 8),
        enableTTS: true,
        enableImages: true,
        // Student flow: web-search enrichment ON by default (OpenMAIC parity).
        enableWebSearch: true,
      };

      setWizardStep(3);
      const result = await validateAndStartOutline(config, approvedAgents);
      // If validation rejected the topic, snap the wizard back to Step 1 so
      // the error banner surfaces. We use the direct return value rather than
      // reading `genStep` from the closure (which is stale here).
      if (result && result.rejected) {
        setWizardStep(1);
      }
    },
    [topic, pdfText, language, sceneCount, validateAndStartOutline],
  );

  const handleStartGeneration = useCallback(async () => {
    if (!outline) return;

    try {
      const res = await maicStudentApi.createClassroom({
        title: outline.topic,
        topic: outline.topic,
        language: outline.language,
        config: {
          agentCount,
          sceneCount: outline.scenes.length,
        },
      });

      const newId = res.data.id;
      setClassroomId(newId);
      setWizardStep(4);

      await startContentGeneration(newId);
    } catch {
      // Error handled inside hook
    }
  }, [outline, agentCount, startContentGeneration]);

  const handleOpenClassroom = useCallback(() => {
    if (classroomId) {
      onComplete?.(classroomId);
    }
  }, [classroomId, onComplete]);

  const handleOutlineChange = useCallback(
    (scenes: MAICOutlineScene[]) => {
      updateOutline(scenes);
    },
    [updateOutline],
  );

  const handleReset = useCallback(() => {
    resetGeneration();
    setTopic('');
    setPdfText(undefined);
    setLanguage('en');
    setAgentCount(3);
    setSceneCount(5);
    setClassroomId(null);
    setAgents([]);
    setWizardStep(1);
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
                    {isCompleted ? <CheckCircle className="h-4 w-4" /> : stepNum}
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
            {guardrailResult && !guardrailResult.allowed && (
              <p className="text-xs text-red-500 mt-1">
                Please enter an educational topic related to your IB subjects or other academic areas.
              </p>
            )}
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

      {/* Guardrail success badge */}
      {guardrailResult?.allowed && genStep !== 'idle' && genStep !== 'error' && effectiveStep <= 2 && (
        <div className="mb-4 rounded-lg border border-green-200 bg-green-50 p-2.5 flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-green-600 shrink-0" />
          <span className="text-xs text-green-700">
            Topic validated: <span className="font-medium">{guardrailResult.subject_area}</span>
          </span>
        </div>
      )}

      {/* ─── Step 1: Topic Input ─────────────────────────────────────────── */}
      {effectiveStep === 1 && (
        <div className="space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 mb-1">Create AI Classroom</h2>
            <p className="text-sm text-gray-500">
              Enter an educational topic to generate an interactive AI classroom.
              Your topic will be reviewed to ensure it's appropriate for learning.
            </p>
          </div>

          {/* Topic */}
          <div>
            <label htmlFor="student-maic-topic" className="block text-sm font-medium text-gray-700 mb-1">
              Topic <span className="text-red-500">*</span>
            </label>
            <input
              id="student-maic-topic"
              type="text"
              value={topic}
              onChange={(e) => setTopic(e.target.value)}
              placeholder="e.g., Photosynthesis in IB Biology, Calculus Integration Techniques"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
              autoFocus
            />
            <p className="mt-1 text-xs text-gray-400">
              Academic topics, IB subjects, study revision — any educational topic works.
            </p>
          </div>

          {/* PDF upload */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Study Material <span className="text-xs text-gray-400">(optional PDF)</span>
            </label>
            <PDFUploader onExtract={setPdfText} />
          </div>

          {/* Language */}
          <div>
            <label htmlFor="student-maic-language" className="block text-sm font-medium text-gray-700 mb-1">
              Language
            </label>
            <select
              id="student-maic-language"
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            >
              {LANGUAGES.map((lang) => (
                <option key={lang.value} value={lang.value}>{lang.label}</option>
              ))}
            </select>
          </div>

          {/* Agent count (capped at 4) */}
          <div>
            <label htmlFor="student-maic-agents" className="flex items-center justify-between text-sm font-medium text-gray-700 mb-1">
              <span>AI Agents</span>
              <span className="text-gray-500 font-normal">{agentCount}</span>
            </label>
            <input
              id="student-maic-agents"
              type="range"
              min={2}
              max={4}
              value={agentCount}
              onChange={(e) => setAgentCount(parseInt(e.target.value, 10))}
              className="w-full h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-primary-600"
            />
            <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
              <span>2</span>
              <span>4</span>
            </div>
          </div>

          {/* Scene count (capped at 8) */}
          <div>
            <label htmlFor="student-maic-scenes" className="flex items-center justify-between text-sm font-medium text-gray-700 mb-1">
              <span>Number of Scenes</span>
              <span className="text-gray-500 font-normal">{sceneCount}</span>
            </label>
            <input
              id="student-maic-scenes"
              type="range"
              min={3}
              max={8}
              value={sceneCount}
              onChange={(e) => setSceneCount(parseInt(e.target.value, 10))}
              className="w-full h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-primary-600"
            />
            <div className="flex justify-between text-[10px] text-gray-400 mt-0.5">
              <span>3</span>
              <span>8</span>
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

      {/* ─── Step 2: Meet your classroom (agent picker) ──────────────────── */}
      {effectiveStep === 2 && (
        <AgentGenerationStep
          topic={topic}
          language={language}
          role="student"
          initialAgents={agents.length > 0 ? agents : undefined}
          onBack={() => setWizardStep(1)}
          onComplete={(approvedAgents) => void handleAgentsComplete(approvedAgents)}
        />
      )}

      {/* ─── Step 3: Outline Review ──────────────────────────────────────── */}
      {effectiveStep === 3 && !outline && (genStep === 'validating' || genStep === 'outlining') && (
        <div className="py-10 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100">
            {genStep === 'validating' ? (
              <ShieldCheck className="h-6 w-6 animate-pulse text-indigo-500" />
            ) : (
              <Loader2 className="h-6 w-6 animate-spin text-indigo-500" />
            )}
          </div>
          <h2 className="text-lg font-semibold text-gray-900">
            {genStep === 'validating' ? 'Validating your topic…' : 'Building your outline…'}
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            {genStep === 'validating'
              ? 'Checking that the topic is appropriate for learning.'
              : `Arranging scenes for ${agents.length} agent${agents.length === 1 ? '' : 's'}.`}
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

      {effectiveStep === 3 && outline && (
        <div className="space-y-5">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 mb-1">Review Outline</h2>
            <p className="text-sm text-gray-500">
              Edit the scene order, titles, and descriptions. Add or remove scenes as needed.
            </p>
          </div>

          <OutlineEditor outline={outline} onChange={handleOutlineChange} />

          <div className="flex justify-between pt-2">
            <button
              type="button"
              onClick={() => {
                // Back from outline-review → agent picker. Keep the roster.
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

      {/* ─── Step 4: Generation Progress ─────────────────────────────────── */}
      {effectiveStep === 4 && (
        <div className="py-6 space-y-6">
          <GenerationVisualizer
            phase={phase as GenerationPhase}
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

      {/* ─── Step 5: Complete ────────────────────────────────────────────── */}
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
                  {outline.scenes.length} scenes
                </span>
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 text-[11px] font-medium text-amber-600">
                  ~{outline.totalMinutes} min
                </span>
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
