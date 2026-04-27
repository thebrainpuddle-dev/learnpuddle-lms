// src/pages/teacher/QuizPlayerPage.tsx
//
// Teacher timed-quiz player for the TASK-043 assessment system.
//
// Lifecycle:
//   1. mount         → POST /teacher/quizzes/:contentId/start  (create attempt)
//   2. live          → answer + navigate; store persists to sessionStorage so
//                      a refresh does not lose work
//   3. timer ticks   → re-render every second; when ≤0 auto-submit
//   4. submit        → single POST /teacher/quiz-attempts/:id/submit
//   5. result screen → show score + passed/failed + (optionally) correct
//                      answers if `show_correct_answers_after` is enabled
//
// Navigation guards: `beforeunload` listener warns the teacher while the
// attempt is IN_PROGRESS so a stray tab-close does not lose answers.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeftIcon,
  ArrowRightIcon,
  ClockIcon,
  CheckCircleIcon,
  XCircleIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline';
import { Button, Loading, useToast } from '../../components/common';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  assessmentService,
  type AttemptQuestion,
  type QuizAttemptStartResponse,
  type QuizAttemptSubmitResponse,
} from '../../services/assessmentService';
import { useQuizAttemptStore } from '../../stores/quizAttemptStore';

// ── Helpers ─────────────────────────────────────────────────────────────────

function fmtClock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const m = Math.floor(s / 60);
  const ss = s % 60;
  const mm = String(m).padStart(2, '0');
  const sec = String(ss).padStart(2, '0');
  return `${mm}:${sec}`;
}

/** Shape of the answer payload the backend expects (see `_is_answer_correct`). */
type BackendAnswer = string | string[] | { text: string };

function toBackendAnswer(q: AttemptQuestion, raw: unknown): BackendAnswer | null {
  if (raw === undefined || raw === null) return null;
  switch (q.type) {
    case 'MCQ':
    case 'TRUE_FALSE':
      return typeof raw === 'string' ? raw : null;
    case 'MULTI':
      return Array.isArray(raw) ? raw.map(String) : null;
    case 'SHORT':
    case 'ESSAY':
      return { text: typeof raw === 'string' ? raw : String(raw ?? '') };
    default:
      return null;
  }
}

// ── Page ────────────────────────────────────────────────────────────────────

export const QuizPlayerPage: React.FC = () => {
  usePageTitle('Quiz');
  const { contentId } = useParams<{ contentId: string }>();
  const navigate = useNavigate();
  const toast = useToast();

  // Store
  const store = useQuizAttemptStore();

  // Component-local state
  const [bootstrapping, setBootstrapping] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<QuizAttemptSubmitResponse | null>(null);
  const [, forceTick] = useState(0);
  const submitGuardRef = useRef(false); // prevents double auto-submit

  // ── Bootstrap: reuse existing attempt if it matches, else start new ──
  useEffect(() => {
    if (!contentId) return;
    const reuse =
      store.attemptId &&
      store.contentId === contentId &&
      store.questions.length > 0;
    if (reuse) {
      setBootstrapping(false);
      return;
    }
    (async () => {
      try {
        const data: QuizAttemptStartResponse =
          await assessmentService.startAttempt(contentId);
        store.start({
          attemptId: data.id,
          contentId,
          questions: data.questions,
          timeLimitSeconds: data.time_limit_seconds,
          startedAt: data.started_at,
          maxScore: data.max_score,
        });
      } catch (err) {
        // Common errors: MAX_ATTEMPTS_REACHED, no config, no questions
        const message =
          (err as { response?: { data?: { error?: string; detail?: string } } })
            .response?.data?.error
          ?? (err as { response?: { data?: { detail?: string } } }).response?.data
            ?.detail
          ?? 'Could not start the quiz.';
        toast.error('Unable to start quiz', message);
        navigate(-1);
      } finally {
        setBootstrapping(false);
      }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [contentId]);

  // ── Countdown ticker (1s) ───────────────────────────────────────────
  useEffect(() => {
    if (result) return; // stop after submit
    if (store.endAtMs === null) return; // unlimited
    const id = window.setInterval(() => forceTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [store.endAtMs, result]);

  // ── Submit handler ─────────────────────────────────────────────────
  const handleSubmit = useCallback(
    async (auto = false): Promise<void> => {
      if (submitGuardRef.current) return;
      if (!store.attemptId) return;
      submitGuardRef.current = true;
      setSubmitting(true);
      try {
        // Build payload keyed by question id
        const payload: Record<string, BackendAnswer> = {};
        for (const q of store.questions) {
          const raw = store.answers[q.id];
          const norm = toBackendAnswer(q, raw);
          if (norm !== null) payload[q.id] = norm;
        }
        const elapsed = store.elapsedSeconds();
        const res = await assessmentService.submitAttempt(
          store.attemptId,
          payload,
          elapsed,
        );
        setResult(res);
        if (auto) {
          toast.info('Time expired', 'Your quiz was submitted automatically.');
        } else {
          toast.success('Submitted', 'Your answers were recorded.');
        }
        // Keep attempt in store so refresh on result screen stays stable;
        // store is cleared when the teacher clicks "Done".
      } catch {
        toast.error('Submission failed', 'Please try again.');
        submitGuardRef.current = false;
      } finally {
        setSubmitting(false);
      }
    },
    [store, toast],
  );

  // ── Auto-submit when time runs out ─────────────────────────────────
  useEffect(() => {
    if (result) return;
    if (store.endAtMs === null) return;
    const remaining = store.remainingSeconds();
    if (remaining !== null && remaining <= 0 && !submitGuardRef.current) {
      void handleSubmit(true);
    }
  // Re-evaluate each tick (forceTick increment triggers re-render which runs this).
  });

  // ── Warn on unload while in progress ──────────────────────────────
  useEffect(() => {
    if (result) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = '';
      return '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [result]);

  // ── Unmount cleanup note: we DO NOT call store.clear() automatically
  //    because React strict-mode / HMR can unmount & remount, and the user
  //    may also briefly navigate within the same tab. Clearing is explicit:
  //    user clicks "Done" on the result screen.

  // ── Derived ────────────────────────────────────────────────────────
  const total = store.questions.length;
  const current: AttemptQuestion | undefined = store.questions[store.currentIndex];
  const remaining = store.remainingSeconds();
  const timerCritical = remaining !== null && remaining <= 30;
  const answered = useMemo(() => {
    let count = 0;
    for (const q of store.questions) {
      const v = store.answers[q.id];
      if (
        v !== undefined &&
        v !== null &&
        !(Array.isArray(v) && v.length === 0) &&
        !(typeof v === 'string' && v.trim() === '')
      ) {
        count += 1;
      }
    }
    return count;
  }, [store.answers, store.questions]);

  // ── Loading / error / result gates ─────────────────────────────────
  if (bootstrapping) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loading />
      </div>
    );
  }

  if (result) {
    return (
      <ResultView
        result={result}
        onDone={() => {
          store.clear();
          submitGuardRef.current = false;
          navigate('/teacher/assignments');
        }}
      />
    );
  }

  if (!current) {
    return (
      <div className="rounded-2xl border border-slate-200/80 bg-white p-6 text-center">
        <p className="text-sm text-slate-600">No questions available.</p>
      </div>
    );
  }

  // ── Render live quiz ───────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Header bar */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between rounded-2xl border border-slate-200/80 bg-white px-4 py-3 shadow-sm">
        <div className="flex items-center gap-3">
          <span className="text-[12px] font-medium text-slate-500">
            Question {store.currentIndex + 1} of {total}
          </span>
          <span className="h-4 w-px bg-slate-200" />
          <span className="text-[12px] text-slate-500">
            {answered} answered
          </span>
        </div>
        {remaining !== null && (
          <div
            className={`inline-flex items-center gap-2 rounded-xl px-3 py-1.5 text-[13px] font-mono font-semibold tabular-nums ${
              timerCritical
                ? 'bg-red-50 text-red-700 border border-red-200'
                : 'bg-slate-100 text-slate-700'
            }`}
            aria-live="polite"
          >
            <ClockIcon className="h-4 w-4" />
            {fmtClock(remaining)}
          </div>
        )}
      </div>

      {/* Question jump pad */}
      <div className="flex flex-wrap gap-2">
        {store.questions.map((q, idx) => {
          const isActive = idx === store.currentIndex;
          const isAnswered =
            store.answers[q.id] !== undefined &&
            store.answers[q.id] !== null &&
            !(Array.isArray(store.answers[q.id]) && (store.answers[q.id] as unknown[]).length === 0) &&
            !(typeof store.answers[q.id] === 'string' && (store.answers[q.id] as string).trim() === '');
          return (
            <button
              key={q.id}
              type="button"
              onClick={() => store.setCurrentIndex(idx)}
              className={`h-8 w-8 rounded-lg text-[12px] font-semibold transition-colors cursor-pointer ${
                isActive
                  ? 'bg-primary-600 text-white shadow-sm'
                  : isAnswered
                  ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
              aria-label={`Go to question ${idx + 1}${isAnswered ? ' (answered)' : ''}`}
            >
              {idx + 1}
            </button>
          );
        })}
      </div>

      {/* Question card */}
      <QuestionRenderer
        question={current}
        value={store.answers[current.id]}
        onChange={(v) => store.setAnswer(current.id, v)}
      />

      {/* Footer nav */}
      <div className="flex items-center justify-between gap-3 rounded-2xl border border-slate-200/80 bg-white px-4 py-3 shadow-sm">
        <Button
          type="button"
          variant="outline"
          onClick={() => store.prev()}
          disabled={store.currentIndex === 0}
        >
          <ArrowLeftIcon className="h-4 w-4 mr-1" />
          Previous
        </Button>

        {store.currentIndex < total - 1 ? (
          <Button type="button" onClick={() => store.next()}>
            Next
            <ArrowRightIcon className="h-4 w-4 ml-1" />
          </Button>
        ) : (
          <Button
            type="button"
            onClick={() => void handleSubmit(false)}
            loading={submitting}
          >
            Submit Quiz
          </Button>
        )}
      </div>
    </div>
  );
};

// ── QuestionRenderer ────────────────────────────────────────────────────────

interface QuestionRendererProps {
  question: AttemptQuestion;
  value: unknown;
  onChange: (v: unknown) => void;
}

const QuestionRenderer: React.FC<QuestionRendererProps> = ({
  question,
  value,
  onChange,
}) => {
  const choices = question.choices ?? [];

  return (
    <div className="rounded-2xl border border-slate-200/80 bg-white p-5 sm:p-6 shadow-sm">
      <p className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-2">
        {question.type === 'MCQ' && 'Single Choice'}
        {question.type === 'MULTI' && 'Multi Select'}
        {question.type === 'TRUE_FALSE' && 'True / False'}
        {question.type === 'SHORT' && 'Short Answer'}
        {question.type === 'ESSAY' && 'Essay'}
        <span className="ml-2 text-slate-400 normal-case">
          · {question.points} point{question.points === 1 ? '' : 's'}
        </span>
      </p>
      <div
        className="text-[15px] font-medium text-slate-900 whitespace-pre-wrap"
        data-testid="quiz-prompt"
      >
        {question.prompt}
      </div>

      <div className="mt-5">
        {question.type === 'MCQ' || question.type === 'TRUE_FALSE' ? (
          <div className="space-y-2">
            {choices.map((c) => {
              const checked = value === c.id;
              return (
                <label
                  key={c.id}
                  className={`flex items-center gap-3 rounded-xl border px-4 py-3 cursor-pointer transition-colors ${
                    checked
                      ? 'border-primary-400 bg-primary-50/60'
                      : 'border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  <input
                    type="radio"
                    name={`q-${question.id}`}
                    checked={checked}
                    onChange={() => onChange(c.id)}
                    className="h-4 w-4 text-primary-600 focus:ring-primary-400 border-slate-300"
                  />
                  <span className="text-[13px] text-slate-800">{c.text}</span>
                </label>
              );
            })}
          </div>
        ) : question.type === 'MULTI' ? (
          <div className="space-y-2">
            {choices.map((c) => {
              const arr = Array.isArray(value) ? (value as string[]) : [];
              const checked = arr.includes(c.id);
              return (
                <label
                  key={c.id}
                  className={`flex items-center gap-3 rounded-xl border px-4 py-3 cursor-pointer transition-colors ${
                    checked
                      ? 'border-primary-400 bg-primary-50/60'
                      : 'border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => {
                      const next = e.target.checked
                        ? [...arr, c.id]
                        : arr.filter((id) => id !== c.id);
                      onChange(next);
                    }}
                    className="h-4 w-4 rounded text-primary-600 focus:ring-primary-400 border-slate-300"
                  />
                  <span className="text-[13px] text-slate-800">{c.text}</span>
                </label>
              );
            })}
          </div>
        ) : (
          <textarea
            value={typeof value === 'string' ? value : ''}
            onChange={(e) => onChange(e.target.value)}
            rows={question.type === 'ESSAY' ? 8 : 4}
            placeholder={
              question.type === 'ESSAY'
                ? 'Write your response…'
                : 'Type your answer…'
            }
            className="w-full px-3 py-2 border border-slate-200 rounded-xl text-[14px] focus:ring-2 focus:ring-primary-200 focus:border-primary-400 focus:outline-none"
          />
        )}
      </div>
    </div>
  );
};

// ── ResultView ──────────────────────────────────────────────────────────────

interface ResultViewProps {
  result: QuizAttemptSubmitResponse;
  onDone: () => void;
}

const ResultView: React.FC<ResultViewProps> = ({ result, onDone }) => {
  const pct = Math.round(result.score_percent ?? 0);
  const showAnswers = result.questions.some((q) =>
    (q.choices ?? []).some((c) => 'is_correct' in c),
  );

  return (
    <div className="space-y-6">
      {/* Summary card */}
      <div
        className={`rounded-2xl border p-6 text-center shadow-sm ${
          result.passed
            ? 'bg-emerald-50 border-emerald-200'
            : 'bg-red-50 border-red-200'
        }`}
      >
        {result.passed ? (
          <CheckCircleIcon className="h-12 w-12 text-emerald-500 mx-auto" />
        ) : result.status === 'EXPIRED' ? (
          <ExclamationTriangleIcon className="h-12 w-12 text-amber-500 mx-auto" />
        ) : (
          <XCircleIcon className="h-12 w-12 text-red-500 mx-auto" />
        )}
        <h2 className="mt-3 text-[20px] font-bold text-slate-900">
          {result.passed ? 'You passed!' : result.status === 'EXPIRED' ? 'Time expired' : 'Not quite there'}
        </h2>
        <p className="mt-1 text-[13px] text-slate-600">
          Score: <strong>{Number(result.score).toFixed(0)}</strong>{' / '}
          <strong>{Number(result.max_score).toFixed(0)}</strong>{' '}
          <span className="text-slate-400">({pct}%)</span>
        </p>
      </div>

      {/* Per-question review (only when backend leaks `is_correct` = configured on) */}
      {showAnswers && (
        <div className="space-y-3">
          {result.questions.map((q, i) => (
            <ReviewCard
              key={q.id}
              index={i}
              question={q}
              answer={result.answers[q.id]}
            />
          ))}
        </div>
      )}

      <div className="flex justify-end">
        <Button onClick={onDone}>Done</Button>
      </div>
    </div>
  );
};

interface ReviewCardProps {
  index: number;
  question: AttemptQuestion;
  answer: unknown;
}

const ReviewCard: React.FC<ReviewCardProps> = ({ index, question, answer }) => {
  const choices = (question.choices ?? []) as Array<
    AttemptQuestion['choices'][number] & { is_correct?: boolean }
  >;
  const correctIds = choices.filter((c) => c.is_correct).map((c) => c.id);

  return (
    <div className="rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm">
      <p className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-1">
        Q{index + 1} · {question.type}
      </p>
      <p className="text-[14px] font-medium text-slate-900 whitespace-pre-wrap">
        {question.prompt}
      </p>

      {choices.length > 0 ? (
        <ul className="mt-3 space-y-1.5 text-[13px]">
          {choices.map((c) => {
            const isCorrect = !!c.is_correct;
            const chosen = Array.isArray(answer)
              ? (answer as string[]).includes(c.id)
              : answer === c.id;
            return (
              <li
                key={c.id}
                className={`flex items-center gap-2 rounded-lg px-2 py-1 ${
                  isCorrect
                    ? 'bg-emerald-50 text-emerald-800'
                    : chosen
                    ? 'bg-red-50 text-red-800'
                    : 'text-slate-600'
                }`}
              >
                {isCorrect ? (
                  <CheckCircleIcon className="h-4 w-4 text-emerald-500" />
                ) : chosen ? (
                  <XCircleIcon className="h-4 w-4 text-red-500" />
                ) : (
                  <span className="h-4 w-4 inline-block" />
                )}
                <span>{c.text}</span>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="mt-2 text-[13px] text-slate-600 whitespace-pre-wrap">
          Your answer:{' '}
          <span className="font-medium text-slate-900">
            {typeof answer === 'object' && answer !== null && 'text' in (answer as Record<string, unknown>)
              ? String((answer as { text?: string }).text ?? '')
              : String(answer ?? '—')}
          </span>
        </p>
      )}

      {correctIds.length === 0 && question.type !== 'SHORT' && question.type !== 'ESSAY' ? null : null}
    </div>
  );
};

export default QuizPlayerPage;
