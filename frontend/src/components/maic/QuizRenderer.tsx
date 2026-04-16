// src/components/maic/QuizRenderer.tsx
//
// Interactive quiz component for MAIC classrooms. Renders single-choice,
// multiple-choice, true/false, and short_answer questions. Short answer
// questions are graded by AI via the quiz-grade endpoint.
//
// Phase 3C additions: countdown timer, review mode with question navigation.

import React, { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import {
  CheckCircle,
  XCircle,
  Send,
  Loader2,
  MessageSquare,
  Clock,
  RotateCcw,
} from 'lucide-react';
import type { MAICQuizQuestion as LegacyQuizQuestion } from '../../types/maic';
import type { MAICQuizQuestion as SceneQuizQuestion } from '../../types/maic-scenes';
import { maicApi } from '../../services/openmaicService';
import { cn } from '../../lib/utils';

// Support both legacy and new question formats
type QuizQuestion = LegacyQuizQuestion | SceneQuizQuestion;

interface QuizRendererProps {
  questions: QuizQuestion[];
  onComplete?: (score: number, total: number) => void;
  /** Enable a countdown timer for the quiz */
  timerEnabled?: boolean;
  /** Time limit in seconds (default 300 = 5 minutes). Only used when timerEnabled is true. */
  timeLimitSeconds?: number;
}

interface GradeResult {
  score: number;
  feedback: string;
  isCorrect: boolean;
}

interface QuizState {
  answers: Record<string, string | string[]>; // questionId -> selected value(s) or text
  submitted: boolean;
  grading: Record<string, boolean>; // questionId -> is grading in progress
  gradeResults: Record<string, GradeResult>; // questionId -> AI grade result
}

// Type guard: check if question uses the new scene format
function isSceneQuestion(q: QuizQuestion): q is SceneQuizQuestion {
  return q.type === 'single' || q.type === 'multiple' || q.type === 'short_answer';
}

/** Format seconds as MM:SS */
function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export const QuizRenderer = React.memo<QuizRendererProps>(function QuizRenderer({
  questions,
  onComplete,
  timerEnabled = false,
  timeLimitSeconds = 300,
}) {
  const [state, setState] = useState<QuizState>({
    answers: {},
    submitted: false,
    grading: {},
    gradeResults: {},
  });

  // ─── Timer state ────────────────────────────────────────────────────────
  const [timeRemaining, setTimeRemaining] = useState(timeLimitSeconds);
  const [timerExpired, setTimerExpired] = useState(false);

  // ─── Review mode state ──────────────────────────────────────────────────
  const [reviewMode, setReviewMode] = useState(false);
  const questionRefs = useRef<Record<string, HTMLFieldSetElement | null>>({});

  const allAnswered = questions.every((q) => {
    const answer = state.answers[q.id];
    if (!answer) return false;
    if (Array.isArray(answer)) return answer.length > 0;
    return typeof answer === 'string' && answer.trim().length > 0;
  });

  // Handle single-choice selection (legacy or new 'single' type)
  const handleSelect = useCallback((questionId: string, value: string) => {
    if (state.submitted) return;
    setState((prev) => ({
      ...prev,
      answers: { ...prev.answers, [questionId]: value },
    }));
  }, [state.submitted]);

  // Handle multiple-choice toggle (new 'multiple' type)
  const handleToggleMultiple = useCallback((questionId: string, value: string) => {
    if (state.submitted) return;
    setState((prev) => {
      const current = (prev.answers[questionId] as string[]) || [];
      const next = current.includes(value)
        ? current.filter((v) => v !== value)
        : [...current, value];
      return {
        ...prev,
        answers: { ...prev.answers, [questionId]: next },
      };
    });
  }, [state.submitted]);

  // Handle short answer text input
  const handleTextChange = useCallback((questionId: string, text: string) => {
    if (state.submitted) return;
    setState((prev) => ({
      ...prev,
      answers: { ...prev.answers, [questionId]: text },
    }));
  }, [state.submitted]);

  // Grade a short-answer question via AI
  const gradeShortAnswer = useCallback(async (q: SceneQuizQuestion) => {
    const answer = state.answers[q.id] as string;
    if (!answer?.trim()) return;

    setState((prev) => ({
      ...prev,
      grading: { ...prev.grading, [q.id]: true },
    }));

    try {
      const response = await maicApi.quizGrade({
        question: q.question,
        answer: answer.trim(),
        commentPrompt: q.commentPrompt,
      });

      const result: GradeResult = response.data as GradeResult;
      setState((prev) => ({
        ...prev,
        grading: { ...prev.grading, [q.id]: false },
        gradeResults: { ...prev.gradeResults, [q.id]: result },
      }));
    } catch {
      setState((prev) => ({
        ...prev,
        grading: { ...prev.grading, [q.id]: false },
        gradeResults: {
          ...prev.gradeResults,
          [q.id]: { score: 0, feedback: 'Failed to grade. Please try again.', isCorrect: false },
        },
      }));
    }
  }, [state.answers]);

  const handleSubmit = useCallback(async () => {
    if (state.submitted) return;
    // Allow submit even if not all answered when timer expires
    if (!allAnswered && !timerExpired) return;

    setState((prev) => ({ ...prev, submitted: true }));

    // Grade short-answer questions via AI
    const shortAnswerQuestions = questions.filter(
      (q) => isSceneQuestion(q) && q.type === 'short_answer',
    ) as SceneQuizQuestion[];

    for (const q of shortAnswerQuestions) {
      await gradeShortAnswer(q);
    }

    // Calculate score for non-short-answer questions
    let totalPoints = 0;
    let earnedPoints = 0;

    for (const q of questions) {
      if (isSceneQuestion(q)) {
        const points = q.points || 1;
        totalPoints += points;

        if (q.type === 'short_answer') {
          // Score will come from AI grading
          continue;
        }

        const userAnswer = state.answers[q.id];
        const correctAnswers = q.answer || [];

        if (q.type === 'single') {
          if (correctAnswers.includes(userAnswer as string)) {
            earnedPoints += points;
          }
        } else if (q.type === 'multiple') {
          const selected = (userAnswer as string[]) || [];
          const isCorrect =
            selected.length === correctAnswers.length &&
            selected.every((v) => correctAnswers.includes(v));
          if (isCorrect) {
            earnedPoints += points;
          }
        }
      } else {
        // Legacy format
        totalPoints += 1;
        const selectedId = state.answers[q.id] as string;
        const selectedOption = q.options.find((o) => o.id === selectedId);
        if (selectedOption?.isCorrect) {
          earnedPoints += 1;
        }
      }
    }

    // Enter review mode after submission
    setReviewMode(true);

    onComplete?.(earnedPoints, totalPoints);
  }, [allAnswered, state.submitted, state.answers, questions, onComplete, gradeShortAnswer, timerExpired]);

  // ─── Timer countdown effect ─────────────────────────────────────────────
  useEffect(() => {
    if (!timerEnabled || state.submitted || timerExpired) return;

    const interval = setInterval(() => {
      setTimeRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [timerEnabled, state.submitted, timerExpired]);

  // Auto-submit when timer hits 0
  useEffect(() => {
    if (timerEnabled && timeRemaining === 0 && !timerExpired && !state.submitted) {
      setTimerExpired(true);
      handleSubmit();
    }
  }, [timerEnabled, timeRemaining, timerExpired, state.submitted, handleSubmit]);

  // ─── Retake quiz handler ────────────────────────────────────────────────
  const handleRetake = useCallback(() => {
    setState({
      answers: {},
      submitted: false,
      grading: {},
      gradeResults: {},
    });
    setReviewMode(false);
    setTimerExpired(false);
    setTimeRemaining(timeLimitSeconds);
  }, [timeLimitSeconds]);

  // ─── Scroll to question ─────────────────────────────────────────────────
  const scrollToQuestion = useCallback((questionId: string) => {
    const el = questionRefs.current[questionId];
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, []);

  // Calculate display score
  const computeScore = (): { earned: number; total: number } => {
    if (!state.submitted) return { earned: 0, total: 0 };

    let total = 0;
    let earned = 0;

    for (const q of questions) {
      if (isSceneQuestion(q)) {
        const points = q.points || 1;
        total += points;

        if (q.type === 'short_answer') {
          const result = state.gradeResults[q.id];
          if (result) {
            earned += result.score * points;
          }
        } else {
          const userAnswer = state.answers[q.id];
          const correctAnswers = q.answer || [];
          if (q.type === 'single' && correctAnswers.includes(userAnswer as string)) {
            earned += points;
          } else if (q.type === 'multiple') {
            const selected = (userAnswer as string[]) || [];
            const correct = selected.length === correctAnswers.length &&
              selected.every((v) => correctAnswers.includes(v));
            if (correct) earned += points;
          }
        }
      } else {
        total += 1;
        const selectedId = state.answers[q.id] as string;
        const selectedOption = q.options.find((o) => o.id === selectedId);
        if (selectedOption?.isCorrect) earned += 1;
      }
    }

    return { earned, total };
  };

  const { earned: score, total: totalQ } = computeScore();

  // ─── Per-question correctness for review navigation ─────────────────────
  const questionCorrectness = useMemo(() => {
    if (!state.submitted) return {};

    const result: Record<string, 'correct' | 'incorrect' | 'unanswered'> = {};

    for (const q of questions) {
      const answer = state.answers[q.id];
      const hasAnswer = answer !== undefined &&
        (Array.isArray(answer) ? answer.length > 0 : typeof answer === 'string' && answer.trim().length > 0);

      if (!hasAnswer) {
        result[q.id] = 'unanswered';
        continue;
      }

      if (isSceneQuestion(q)) {
        if (q.type === 'short_answer') {
          const gradeResult = state.gradeResults[q.id];
          if (gradeResult) {
            result[q.id] = gradeResult.isCorrect ? 'correct' : 'incorrect';
          } else {
            // Still grading
            result[q.id] = 'unanswered';
          }
        } else {
          const correctAnswers = q.answer || [];
          if (q.type === 'single') {
            result[q.id] = correctAnswers.includes(answer as string) ? 'correct' : 'incorrect';
          } else {
            const selected = (answer as string[]) || [];
            const isCorrect =
              selected.length === correctAnswers.length &&
              selected.every((v) => correctAnswers.includes(v));
            result[q.id] = isCorrect ? 'correct' : 'incorrect';
          }
        }
      } else {
        const selectedOption = q.options.find((o) => o.id === (answer as string));
        result[q.id] = selectedOption?.isCorrect ? 'correct' : 'incorrect';
      }
    }

    return result;
  }, [state.submitted, state.answers, state.gradeResults, questions]);

  // ─── Timer display helpers ──────────────────────────────────────────────
  const timerPercentage = timeLimitSeconds > 0 ? (timeRemaining / timeLimitSeconds) * 100 : 0;

  const timerColorClass = (() => {
    if (timerPercentage > 50) return 'bg-green-500';
    if (timerPercentage > 25) return 'bg-yellow-500';
    return 'bg-red-500';
  })();

  const timerTextColorClass = (() => {
    if (timerPercentage > 50) return 'text-green-700';
    if (timerPercentage > 25) return 'text-yellow-700';
    return 'text-red-700';
  })();

  const isTimerFlashing = timerEnabled && !state.submitted && timeRemaining > 0 && timerPercentage < 10;
  const isTimerPulsing = timerEnabled && !state.submitted && timeRemaining > 0 && timeRemaining <= 30;

  if (questions.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400 text-sm">
        No quiz questions available.
      </div>
    );
  }

  return (
    <div className="space-y-6 p-4 overflow-y-auto max-h-full" role="form" aria-label="Quiz">
      {/* Timer bar */}
      {timerEnabled && (
        <div
          className={cn(
            'rounded-lg border px-4 py-3',
            state.submitted
              ? 'border-gray-200 bg-gray-50'
              : timerPercentage > 50
                ? 'border-green-200 bg-green-50'
                : timerPercentage > 25
                  ? 'border-yellow-200 bg-yellow-50'
                  : 'border-red-200 bg-red-50',
            isTimerFlashing && 'animate-pulse',
          )}
        >
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Clock className={cn('h-4 w-4', state.submitted ? 'text-gray-400' : timerTextColorClass)} />
              <span className={cn(
                'text-sm font-semibold tabular-nums',
                state.submitted ? 'text-gray-500' : timerTextColorClass,
              )}>
                {state.submitted
                  ? (timerExpired ? 'Time expired' : `Finished with ${formatTime(timeRemaining)} left`)
                  : formatTime(timeRemaining)
                }
              </span>
            </div>
            {isTimerPulsing && !state.submitted && (
              <span className="text-xs font-medium text-red-600 animate-pulse">
                Hurry up!
              </span>
            )}
          </div>
          <div className="h-1.5 bg-gray-200 rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full transition-all duration-1000 ease-linear',
                state.submitted ? 'bg-gray-400' : timerColorClass,
              )}
              style={{ width: `${state.submitted ? (timerExpired ? 0 : timerPercentage) : timerPercentage}%` }}
            />
          </div>
        </div>
      )}

      {/* Timer expired banner */}
      {timerExpired && state.submitted && (
        <div className="rounded-lg px-4 py-3 text-center font-medium bg-red-50 text-red-700 border border-red-200" role="alert">
          Time&apos;s up! Your quiz has been auto-submitted.
        </div>
      )}

      {/* Score banner */}
      {state.submitted && totalQ > 0 && !timerExpired && (
        <div
          className={cn(
            'rounded-lg px-4 py-3 text-center font-medium',
            score === totalQ
              ? 'bg-green-50 text-green-700 border border-green-200'
              : score >= totalQ / 2
                ? 'bg-yellow-50 text-yellow-700 border border-yellow-200'
                : 'bg-red-50 text-red-700 border border-red-200',
          )}
          role="status"
        >
          You scored {Math.round(score)} out of {totalQ} ({Math.round((score / totalQ) * 100)}%)
        </div>
      )}

      {/* Score banner for timer-expired case */}
      {state.submitted && totalQ > 0 && timerExpired && (
        <div
          className={cn(
            'rounded-lg px-4 py-3 text-center font-medium',
            score === totalQ
              ? 'bg-green-50 text-green-700 border border-green-200'
              : score >= totalQ / 2
                ? 'bg-yellow-50 text-yellow-700 border border-yellow-200'
                : 'bg-red-50 text-red-700 border border-red-200',
          )}
          role="status"
        >
          You scored {Math.round(score)} out of {totalQ} ({Math.round((score / totalQ) * 100)}%)
        </div>
      )}

      {/* Review mode header */}
      {reviewMode && state.submitted && (
        <div className="space-y-3">
          {/* Question navigation bar */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-gray-500 mr-1">Questions:</span>
            {questions.map((q, qi) => {
              const status = questionCorrectness[q.id];
              return (
                <button
                  key={q.id}
                  type="button"
                  onClick={() => scrollToQuestion(q.id)}
                  className={cn(
                    'h-7 w-7 rounded-full text-xs font-semibold flex items-center justify-center',
                    'transition-colors focus:outline-none focus:ring-2 focus:ring-offset-1',
                    status === 'correct' && 'bg-green-500 text-white hover:bg-green-600 focus:ring-green-400',
                    status === 'incorrect' && 'bg-red-500 text-white hover:bg-red-600 focus:ring-red-400',
                    status === 'unanswered' && 'bg-gray-300 text-gray-700 hover:bg-gray-400 focus:ring-gray-400',
                    !status && 'bg-gray-300 text-gray-700 hover:bg-gray-400 focus:ring-gray-400',
                  )}
                  aria-label={`Go to question ${qi + 1} (${status || 'pending'})`}
                >
                  {qi + 1}
                </button>
              );
            })}
          </div>

          {/* Review summary */}
          <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-900">
                  {Object.values(questionCorrectness).filter((v) => v === 'correct').length} of{' '}
                  {questions.length} correct
                  {totalQ > 0 && (
                    <span className="text-gray-500 ml-1">
                      ({Math.round((score / totalQ) * 100)}%)
                    </span>
                  )}
                </p>
                <p className="text-xs text-gray-500 mt-0.5">Review your answers below</p>
              </div>
              <button
                type="button"
                onClick={handleRetake}
                className={cn(
                  'inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium',
                  'bg-white border border-gray-200 text-gray-700',
                  'hover:bg-gray-50 hover:border-gray-300',
                  'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1',
                  'transition-colors',
                )}
              >
                <RotateCcw className="h-3.5 w-3.5" />
                Retake Quiz
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Questions */}
      {questions.map((q, qi) => {
        if (isSceneQuestion(q)) {
          return renderSceneQuestion(
            q, qi, state, handleSelect, handleToggleMultiple, handleTextChange,
            reviewMode, questionRefs,
          );
        }
        return renderLegacyQuestion(q, qi, state, handleSelect, reviewMode, questionRefs);
      })}

      {/* Submit button */}
      {!state.submitted && (
        <div className="flex justify-end">
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!allAnswered}
            className={cn(
              'inline-flex items-center gap-2 rounded-lg px-5 py-2.5 text-sm font-medium',
              'bg-primary-600 text-white hover:bg-primary-700',
              'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'transition-colors',
            )}
          >
            <Send className="h-4 w-4" />
            Submit Answers
          </button>
        </div>
      )}
    </div>
  );
});

// ─── Legacy question renderer (multiple_choice / true_false) ─────────────────

function renderLegacyQuestion(
  q: LegacyQuizQuestion,
  qi: number,
  state: QuizState,
  handleSelect: (qid: string, val: string) => void,
  reviewMode: boolean,
  questionRefs: React.MutableRefObject<Record<string, HTMLFieldSetElement | null>>,
): React.ReactNode {
  const selectedId = state.answers[q.id] as string;
  const selectedOption = q.options.find((o) => o.id === selectedId);
  const isCorrect = selectedOption?.isCorrect;

  // For true/false, present exactly two options if none provided
  const options = q.type === 'true_false' && q.options.length === 0
    ? [
        { id: 'true', text: 'True', isCorrect: undefined },
        { id: 'false', text: 'False', isCorrect: undefined },
      ]
    : q.options;

  return (
    <fieldset
      key={q.id}
      ref={(el) => { questionRefs.current[q.id] = el; }}
      className="rounded-lg border border-gray-200 p-4"
    >
      <legend className="sr-only">Question {qi + 1}</legend>
      <p className="text-sm font-medium text-gray-900 mb-3">
        <span className="text-gray-400 mr-1.5">{qi + 1}.</span>
        {q.question}
      </p>

      {/* Review: points earned */}
      {reviewMode && state.submitted && (
        <div className="mb-2 text-xs text-gray-500">
          {isCorrect ? '1' : '0'} / 1 point
        </div>
      )}

      <div className="space-y-2" role="radiogroup" aria-label={`Question ${qi + 1}`}>
        {options.map((opt) => {
          const isSelected = selectedId === opt.id;
          const showResult = state.submitted;
          const optIsCorrect = opt.isCorrect;

          return (
            <label
              key={opt.id}
              className={cn(
                'flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm cursor-pointer transition-colors',
                !showResult && !isSelected && 'border-gray-200 hover:bg-gray-50',
                !showResult && isSelected && 'border-primary-500 bg-primary-50',
                showResult && optIsCorrect && 'border-green-300 bg-green-50',
                showResult && isSelected && !optIsCorrect && 'border-red-300 bg-red-50',
                showResult && !isSelected && !optIsCorrect && 'border-gray-200 opacity-60',
                state.submitted && 'cursor-default',
              )}
            >
              <input
                type="radio"
                name={q.id}
                value={opt.id}
                checked={isSelected}
                onChange={() => handleSelect(q.id, opt.id)}
                disabled={state.submitted}
                className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300"
              />
              <span className="flex-1">{opt.text}</span>
              {showResult && optIsCorrect && (
                <CheckCircle className="h-4 w-4 text-green-600 shrink-0" aria-label="Correct answer" />
              )}
              {showResult && isSelected && !optIsCorrect && (
                <XCircle className="h-4 w-4 text-red-500 shrink-0" aria-label="Incorrect" />
              )}
            </label>
          );
        })}
      </div>

      {/* Explanation — always visible in review mode */}
      {state.submitted && q.explanation && (
        <div className={cn(
          'mt-3 rounded-md px-3 py-2 text-xs',
          isCorrect ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700',
        )}>
          <span className="font-medium">Explanation:</span> {q.explanation}
        </div>
      )}
    </fieldset>
  );
}

// ─── Scene question renderer (single / multiple / short_answer) ──────────────

function renderSceneQuestion(
  q: SceneQuizQuestion,
  qi: number,
  state: QuizState,
  handleSelect: (qid: string, val: string) => void,
  handleToggleMultiple: (qid: string, val: string) => void,
  handleTextChange: (qid: string, text: string) => void,
  reviewMode: boolean,
  questionRefs: React.MutableRefObject<Record<string, HTMLFieldSetElement | null>>,
): React.ReactNode {
  const correctAnswers = q.answer || [];
  const gradeResult = state.gradeResults[q.id];
  const isGrading = state.grading[q.id];
  const points = q.points || 1;

  if (q.type === 'short_answer') {
    const textAnswer = (state.answers[q.id] as string) || '';

    // Compute earned points for review
    const earnedPts = gradeResult ? Math.round(gradeResult.score * points) : 0;

    return (
      <fieldset
        key={q.id}
        ref={(el) => { questionRefs.current[q.id] = el; }}
        className="rounded-lg border border-gray-200 p-4"
      >
        <legend className="sr-only">Question {qi + 1}</legend>
        <div className="flex items-start justify-between gap-2 mb-3">
          <p className="text-sm font-medium text-gray-900">
            <span className="text-gray-400 mr-1.5">{qi + 1}.</span>
            {q.question}
          </p>
          {points > 1 && (
            <span className="shrink-0 text-xs text-gray-400 bg-gray-100 rounded-full px-2 py-0.5">
              {points} pts
            </span>
          )}
        </div>

        {/* Review: points earned */}
        {reviewMode && state.submitted && gradeResult && (
          <div className="mb-2 text-xs text-gray-500">
            {earnedPts} / {points} point{points !== 1 ? 's' : ''}
          </div>
        )}

        <textarea
          value={textAnswer}
          onChange={(e) => handleTextChange(q.id, e.target.value)}
          disabled={state.submitted}
          placeholder="Type your answer here..."
          rows={4}
          className={cn(
            'w-full resize-none rounded-lg border border-gray-200 px-3 py-2 text-sm',
            'placeholder:text-gray-400',
            'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent',
            'disabled:opacity-60 disabled:bg-gray-50',
          )}
          aria-label={`Answer for question ${qi + 1}`}
        />

        {/* AI Grading result */}
        {isGrading && (
          <div className="mt-3 flex items-center gap-2 text-xs text-gray-500">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            AI is grading your answer...
          </div>
        )}

        {gradeResult && (
          <div className={cn(
            'mt-3 rounded-md px-3 py-2.5 text-xs space-y-1.5',
            gradeResult.isCorrect ? 'bg-green-50 border border-green-200' : 'bg-amber-50 border border-amber-200',
          )}>
            <div className="flex items-center gap-2">
              {gradeResult.isCorrect ? (
                <CheckCircle className="h-4 w-4 text-green-600 shrink-0" />
              ) : (
                <XCircle className="h-4 w-4 text-amber-600 shrink-0" />
              )}
              <span className={cn(
                'font-medium',
                gradeResult.isCorrect ? 'text-green-700' : 'text-amber-700',
              )}>
                Score: {Math.round(gradeResult.score * 100)}%
              </span>
            </div>
            <div className="flex items-start gap-2">
              <MessageSquare className="h-3.5 w-3.5 text-gray-400 shrink-0 mt-0.5" />
              <p className={gradeResult.isCorrect ? 'text-green-700' : 'text-amber-700'}>
                {gradeResult.feedback}
              </p>
            </div>
          </div>
        )}

        {/* Analysis / explanation — always visible in review mode */}
        {state.submitted && q.analysis && !isGrading && (
          <div className="mt-2 rounded-md px-3 py-2 text-xs bg-blue-50 text-blue-700">
            <span className="font-medium">Analysis:</span> {q.analysis}
          </div>
        )}
      </fieldset>
    );
  }

  // Single or multiple choice (new format)
  const options = q.options || [];
  const isSingle = q.type === 'single';

  // Compute correctness for review
  const userAnswer = state.answers[q.id];
  const isQuestionCorrect = (() => {
    if (!state.submitted) return false;
    if (isSingle) return correctAnswers.includes(userAnswer as string);
    const selected = (userAnswer as string[]) || [];
    return selected.length === correctAnswers.length && selected.every((v) => correctAnswers.includes(v));
  })();
  const earnedPts = isQuestionCorrect ? points : 0;

  return (
    <fieldset
      key={q.id}
      ref={(el) => { questionRefs.current[q.id] = el; }}
      className="rounded-lg border border-gray-200 p-4"
    >
      <legend className="sr-only">Question {qi + 1}</legend>
      <div className="flex items-start justify-between gap-2 mb-3">
        <p className="text-sm font-medium text-gray-900">
          <span className="text-gray-400 mr-1.5">{qi + 1}.</span>
          {q.question}
        </p>
        <div className="flex items-center gap-2 shrink-0">
          {!isSingle && (
            <span className="text-xs text-gray-400 bg-gray-100 rounded-full px-2 py-0.5">
              Select all
            </span>
          )}
          {points > 1 && (
            <span className="text-xs text-gray-400 bg-gray-100 rounded-full px-2 py-0.5">
              {points} pts
            </span>
          )}
        </div>
      </div>

      {/* Review: points earned */}
      {reviewMode && state.submitted && (
        <div className="mb-2 text-xs text-gray-500">
          {earnedPts} / {points} point{points !== 1 ? 's' : ''}
        </div>
      )}

      <div
        className="space-y-2"
        role={isSingle ? 'radiogroup' : 'group'}
        aria-label={`Question ${qi + 1}`}
      >
        {options.map((opt) => {
          const isSelected = isSingle
            ? (state.answers[q.id] as string) === opt.value
            : ((state.answers[q.id] as string[]) || []).includes(opt.value);
          const showResult = state.submitted;
          const optIsCorrect = correctAnswers.includes(opt.value);

          return (
            <label
              key={opt.value}
              className={cn(
                'flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm cursor-pointer transition-colors',
                !showResult && !isSelected && 'border-gray-200 hover:bg-gray-50',
                !showResult && isSelected && 'border-primary-500 bg-primary-50',
                showResult && optIsCorrect && 'border-green-300 bg-green-50',
                showResult && isSelected && !optIsCorrect && 'border-red-300 bg-red-50',
                showResult && !isSelected && !optIsCorrect && 'border-gray-200 opacity-60',
                state.submitted && 'cursor-default',
              )}
            >
              <input
                type={isSingle ? 'radio' : 'checkbox'}
                name={q.id}
                value={opt.value}
                checked={isSelected}
                onChange={() =>
                  isSingle
                    ? handleSelect(q.id, opt.value)
                    : handleToggleMultiple(q.id, opt.value)
                }
                disabled={state.submitted}
                className={cn(
                  'h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300',
                  !isSingle && 'rounded',
                )}
              />
              <span className="flex-1">{opt.label}</span>
              {showResult && optIsCorrect && (
                <CheckCircle className="h-4 w-4 text-green-600 shrink-0" aria-label="Correct answer" />
              )}
              {showResult && isSelected && !optIsCorrect && (
                <XCircle className="h-4 w-4 text-red-500 shrink-0" aria-label="Incorrect" />
              )}
            </label>
          );
        })}
      </div>

      {/* Analysis / explanation — always visible in review mode */}
      {state.submitted && q.analysis && (
        <div className={cn(
          'mt-3 rounded-md px-3 py-2 text-xs',
          isQuestionCorrect ? 'bg-green-50 text-green-700' : 'bg-amber-50 text-amber-700',
        )}>
          <span className="font-medium">Analysis:</span> {q.analysis}
        </div>
      )}
    </fieldset>
  );
}
