// src/pages/student/QuizPage.tsx
//
// Student quiz — honor-code gate, answer all questions, submit, view results.

import React, { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  CheckCircle2,
  XCircle,
  ClipboardList,
  ShieldCheck,
  Send,
  Trophy,
  Clock,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';
import { studentService } from '../../services/studentService';
import { usePageTitle } from '../../hooks/usePageTitle';
import { Button, ConfirmDialog, useToast } from '../../components/common';

// ─── Types ───────────────────────────────────────────────────────────────────

type QuizData = Awaited<ReturnType<typeof studentService.getQuizDetail>>;
type Question = QuizData['questions'][number];

// ─── Honor Code Gate ─────────────────────────────────────────────────────────

function HonorCodeGate({ onAccept }: { onAccept: () => void }) {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm max-w-lg w-full p-6 sm:p-8 text-center">
        <div className="mx-auto h-14 w-14 rounded-2xl bg-indigo-50 flex items-center justify-center mb-5">
          <ShieldCheck className="h-7 w-7 text-indigo-600" />
        </div>

        <h2 className="text-[18px] font-bold text-tp-text tracking-tight mb-2">
          Academic Integrity Pledge
        </h2>

        <p className="text-[13px] text-gray-400 leading-relaxed mb-6">
          By starting this quiz you affirm that all work submitted will be your
          own. You will not give or receive unauthorized assistance, use
          prohibited resources, or misrepresent your understanding of the
          material.
        </p>

        <Button
          variant="primary"
          className="bg-indigo-600 hover:bg-indigo-700 focus:ring-indigo-500 w-full sm:w-auto"
          leftIcon={<ShieldCheck className="h-4 w-4" />}
          onClick={onAccept}
        >
          I agree — start quiz
        </Button>
      </div>
    </div>
  );
}

// ─── Question Card ───────────────────────────────────────────────────────────

function QuestionCard({
  question,
  index,
  total,
  answer,
  onChange,
  readOnly,
  submittedAnswer,
}: {
  question: Question;
  index: number;
  total: number;
  answer: any;
  onChange: (value: any) => void;
  readOnly: boolean;
  submittedAnswer?: any;
}) {
  const typeLabel =
    question.question_type === 'MCQ'
      ? question.selection_mode === 'MULTIPLE'
        ? 'Multiple select'
        : 'Multiple choice'
      : question.question_type === 'TRUE_FALSE'
        ? 'True / False'
        : 'Short answer';

  return (
    <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-4 sm:p-5">
      {/* Question header */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="min-w-0 flex-1">
          <p className="text-[11px] text-gray-400 font-medium mb-1">
            Q{index + 1} of {total} &middot; {typeLabel} &middot; {question.points}{' '}
            {question.points === 1 ? 'pt' : 'pts'}
          </p>
          <p className="text-[14px] font-semibold text-tp-text leading-snug">
            {question.prompt}
          </p>
        </div>

        {/* Answered indicator (active quiz) */}
        {!readOnly && answer != null && (
          <div className="flex-shrink-0">
            <CheckCircle2 className="h-5 w-5 text-indigo-500" />
          </div>
        )}
      </div>

      {/* ── MCQ SINGLE ──────────────────────────────────────── */}
      {question.question_type === 'MCQ' && question.selection_mode === 'SINGLE' && (
        <div className="space-y-2">
          {question.options.map((opt, idx) => {
            const selected = answer?.option_index === idx;
            const wasSubmitted = submittedAnswer?.option_index === idx;

            return (
              <label
                key={idx}
                className={cn(
                  'flex items-center gap-3 p-2.5 rounded-xl cursor-pointer transition-colors border',
                  readOnly
                    ? wasSubmitted
                      ? 'border-indigo-200 bg-indigo-50/50'
                      : 'border-transparent'
                    : selected
                      ? 'border-indigo-200 bg-indigo-50/60'
                      : 'border-transparent hover:bg-gray-50',
                  readOnly && 'cursor-default',
                )}
              >
                <input
                  type="radio"
                  name={`q-${question.id}`}
                  checked={selected}
                  disabled={readOnly}
                  onChange={() => onChange({ option_index: idx })}
                  className="h-4 w-4 text-indigo-600 focus:ring-indigo-500/20 border-gray-300"
                />
                <span className="text-[13px] text-gray-800 flex-1">{opt}</span>
                {readOnly && wasSubmitted && (
                  <CheckCircle2 className="h-4 w-4 text-indigo-500 flex-shrink-0" />
                )}
              </label>
            );
          })}
        </div>
      )}

      {/* ── MCQ MULTIPLE ────────────────────────────────────── */}
      {question.question_type === 'MCQ' && question.selection_mode === 'MULTIPLE' && (
        <div className="space-y-2">
          {question.options.map((opt, idx) => {
            const selectedIndices: number[] = Array.isArray(answer?.option_indices)
              ? answer.option_indices
              : [];
            const checked = selectedIndices.includes(idx);
            const wasSubmitted = Array.isArray(submittedAnswer?.option_indices) &&
              submittedAnswer.option_indices.includes(idx);

            return (
              <label
                key={idx}
                className={cn(
                  'flex items-center gap-3 p-2.5 rounded-xl cursor-pointer transition-colors border',
                  readOnly
                    ? wasSubmitted
                      ? 'border-indigo-200 bg-indigo-50/50'
                      : 'border-transparent'
                    : checked
                      ? 'border-indigo-200 bg-indigo-50/60'
                      : 'border-transparent hover:bg-gray-50',
                  readOnly && 'cursor-default',
                )}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={readOnly}
                  onChange={(e) => {
                    const next = e.target.checked
                      ? [...selectedIndices, idx]
                      : selectedIndices.filter((v) => v !== idx);
                    onChange({ option_indices: next });
                  }}
                  className="h-4 w-4 text-indigo-600 focus:ring-indigo-500/20 border-gray-300 rounded"
                />
                <span className="text-[13px] text-gray-800 flex-1">{opt}</span>
                {readOnly && wasSubmitted && (
                  <CheckCircle2 className="h-4 w-4 text-indigo-500 flex-shrink-0" />
                )}
              </label>
            );
          })}
        </div>
      )}

      {/* ── TRUE / FALSE ────────────────────────────────────── */}
      {question.question_type === 'TRUE_FALSE' && (
        <div className="flex flex-col gap-2.5 sm:flex-row">
          {[true, false].map((choice) => {
            const selected = answer?.value === choice;
            const wasSubmitted = submittedAnswer?.value === choice;

            return (
              <button
                key={String(choice)}
                type="button"
                disabled={readOnly}
                onClick={() => onChange({ value: choice })}
                className={cn(
                  'flex-1 flex items-center justify-center gap-2 px-4 py-3 rounded-xl border text-[13px] font-medium transition-all',
                  readOnly
                    ? wasSubmitted
                      ? 'border-indigo-300 bg-indigo-50 text-indigo-700'
                      : 'border-gray-100 text-gray-400'
                    : selected
                      ? 'border-indigo-300 bg-indigo-50 text-indigo-700 shadow-sm'
                      : 'border-gray-200 text-gray-600 hover:border-indigo-200 hover:bg-indigo-50/40',
                  readOnly && 'cursor-default',
                )}
              >
                {choice ? 'True' : 'False'}
              </button>
            );
          })}
        </div>
      )}

      {/* ── SHORT ANSWER ────────────────────────────────────── */}
      {question.question_type === 'SHORT_ANSWER' && (
        <div>
          <textarea
            rows={3}
            value={answer?.text ?? ''}
            disabled={readOnly}
            onChange={(e) => onChange({ text: e.target.value })}
            className={cn(
              'w-full px-3 py-2 border border-gray-200 rounded-xl text-[13px] focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-400 placeholder:text-gray-400 transition-colors resize-none',
              readOnly && 'bg-gray-50 cursor-default',
            )}
            placeholder="Type your answer..."
          />
        </div>
      )}
    </div>
  );
}

// ─── Results View ────────────────────────────────────────────────────────────

function ResultsView({
  data,
  onBack,
}: {
  data: QuizData;
  onBack: () => void;
}) {
  const submission = data.submission!;
  const totalPoints = data.questions.reduce((sum, q) => sum + q.points, 0);
  const score = submission.score ?? 0;
  const percentage = totalPoints > 0 ? Math.round((score / totalPoints) * 100) : 0;

  return (
    <div className="space-y-5">
      {/* Back */}
      <button
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-[13px] text-gray-400 hover:text-tp-text transition-colors"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to Assignments
      </button>

      {/* Score Card */}
      <div className="bg-white rounded-2xl border border-gray-100 shadow-sm p-6 text-center">
        <div className="mx-auto h-20 w-20 rounded-2xl bg-indigo-50 flex items-center justify-center mb-4">
          <Trophy className="h-10 w-10 text-indigo-600" />
        </div>

        <h2 className="text-[22px] font-bold text-tp-text tracking-tight mb-1">
          Quiz Completed
        </h2>

        <div className="mt-4 mb-2">
          <span className="text-[42px] font-extrabold text-indigo-600 tabular-nums leading-none">
            {percentage}%
          </span>
        </div>

        <p className="text-[13px] text-gray-400 font-medium">
          {score} / {totalPoints} points
        </p>

        {submission.graded_at && (
          <div className="flex items-center justify-center gap-1.5 mt-3 text-[11px] text-gray-400">
            <Clock className="h-3 w-3" />
            Graded{' '}
            {new Date(submission.graded_at).toLocaleDateString('en-US', {
              month: 'short',
              day: 'numeric',
              year: 'numeric',
            })}
          </div>
        )}

        <p className="text-[11px] text-gray-300 mt-1">
          Submitted{' '}
          {new Date(submission.submitted_at).toLocaleDateString('en-US', {
            month: 'short',
            day: 'numeric',
            year: 'numeric',
            hour: 'numeric',
            minute: '2-digit',
          })}
        </p>
      </div>

      {/* Questions Review */}
      <div className="space-y-3">
        <h3 className="text-[13px] font-semibold text-tp-text px-1">
          Your Answers
        </h3>
        {data.questions
          .sort((a, b) => a.order - b.order)
          .map((q, i) => (
            <QuestionCard
              key={q.id}
              question={q}
              index={i}
              total={data.questions.length}
              answer={submission.answers[q.id]}
              onChange={() => {}}
              readOnly
              submittedAnswer={submission.answers[q.id]}
            />
          ))}
      </div>

      {/* Back button */}
      <div className="flex justify-center pt-2">
        <Button
          variant="outline"
          className="border-indigo-200 text-indigo-600 hover:bg-indigo-50"
          leftIcon={<ArrowLeft className="h-4 w-4" />}
          onClick={onBack}
        >
          Back to Assignments
        </Button>
      </div>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export const QuizPage: React.FC = () => {
  usePageTitle('Quiz');
  const { assignmentId } = useParams<{ assignmentId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();

  // ── State ──────────────────────────────────────────────
  const [honorAccepted, setHonorAccepted] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  // ── Fetch quiz ─────────────────────────────────────────
  const { data, isLoading } = useQuery({
    queryKey: ['studentQuiz', assignmentId],
    queryFn: () => studentService.getQuizDetail(assignmentId as string),
    enabled: Boolean(assignmentId),
  });

  // ── Answers state (seeded from submission if already done)
  const initialAnswers = useMemo(
    () => data?.submission?.answers ?? {},
    [data?.submission?.answers],
  );
  const [answers, setAnswers] = useState<Record<string, any>>(initialAnswers);
  useEffect(() => {
    setAnswers(initialAnswers);
  }, [initialAnswers]);

  // ── Derived ────────────────────────────────────────────
  const questions = useMemo(
    () => (data?.questions ?? []).sort((a, b) => a.order - b.order),
    [data?.questions],
  );
  const answeredCount = questions.filter((q) => {
    const a = answers[q.id];
    if (a == null) return false;
    if (a.option_index != null) return true;
    if (Array.isArray(a.option_indices) && a.option_indices.length > 0) return true;
    if (a.value != null) return true;
    if (typeof a.text === 'string' && a.text.trim().length > 0) return true;
    return false;
  }).length;
  const progressPct = questions.length > 0
    ? Math.round((answeredCount / questions.length) * 100)
    : 0;
  const isSubmitted = data?.submission != null;

  // ── Submit mutation ────────────────────────────────────
  const submitMutation = useMutation({
    mutationFn: () =>
      studentService.submitQuiz(assignmentId as string, answers),
    onSuccess: () => {
      toast.success('Quiz submitted', 'Your answers have been recorded.');
      queryClient.invalidateQueries({ queryKey: ['studentQuiz', assignmentId] });
      queryClient.invalidateQueries({ queryKey: ['studentAssignments'] });
    },
    onError: (err: any) => {
      const msg =
        err?.response?.data?.detail ??
        err?.response?.data?.error ??
        'Something went wrong. Please try again.';
      toast.error('Submission failed', msg);
    },
  });

  // ── Loading ────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="space-y-5">
        <div className="h-8 w-48 tp-skeleton rounded-lg" />
        <div className="h-24 tp-skeleton rounded-2xl" />
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-40 tp-skeleton rounded-2xl" />
          ))}
        </div>
      </div>
    );
  }

  // ── Not found ──────────────────────────────────────────
  if (!data) {
    return (
      <div className="text-center py-20">
        <ClipboardList className="h-10 w-10 mx-auto text-gray-200 mb-3" />
        <h3 className="text-[15px] font-semibold text-tp-text mb-1">
          Quiz not found
        </h3>
        <p className="text-[13px] text-gray-400 mb-4">
          This quiz may have been removed or you don't have access.
        </p>
        <button
          onClick={() => navigate('/student/assignments')}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-[12px] font-medium bg-indigo-50 text-indigo-600 hover:bg-indigo-100 transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Assignments
        </button>
      </div>
    );
  }

  // ── Already submitted — show results ───────────────────
  if (isSubmitted) {
    return (
      <ResultsView
        data={data}
        onBack={() => navigate('/student/assignments')}
      />
    );
  }

  // ── Honor code gate ────────────────────────────────────
  if (!honorAccepted) {
    return <HonorCodeGate onAccept={() => setHonorAccepted(true)} />;
  }

  // ── Active quiz ────────────────────────────────────────
  return (
    <div className="space-y-5">
      {/* Back + title */}
      <div>
        <button
          onClick={() => navigate('/student/assignments')}
          className="inline-flex items-center gap-1.5 text-[13px] text-gray-400 hover:text-tp-text transition-colors mb-3"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to Assignments
        </button>

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h1 className="text-[18px] font-bold text-tp-text tracking-tight">
            Quiz
          </h1>
          <p className="text-[12px] text-gray-400 font-medium tabular-nums">
            {answeredCount} of {questions.length} answered
          </p>
        </div>
      </div>

      {/* Progress bar */}
      <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-3">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[11px] text-gray-400 font-medium">Progress</span>
          <span className="text-[11px] text-indigo-600 font-semibold tabular-nums">
            {progressPct}%
          </span>
        </div>
        <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-indigo-500 to-violet-400 rounded-full transition-all duration-500"
            style={{ width: `${progressPct}%` }}
          />
        </div>
      </div>

      {/* Questions (all at once, matching teacher pattern) */}
      <div className="space-y-3">
        {questions.map((q, i) => (
          <QuestionCard
            key={q.id}
            question={q}
            index={i}
            total={questions.length}
            answer={answers[q.id]}
            onChange={(value) =>
              setAnswers((prev) => ({ ...prev, [q.id]: value }))
            }
            readOnly={false}
          />
        ))}
      </div>

      {/* Submit */}
      <div className="flex items-center justify-end gap-3 pt-2">
        <p className="text-[11px] text-gray-400 mr-auto">
          {questions.length - answeredCount > 0 && (
            <>
              <XCircle className="inline h-3.5 w-3.5 text-amber-400 mr-1 -mt-0.5" />
              {questions.length - answeredCount} unanswered
            </>
          )}
        </p>
        <Button
          variant="primary"
          className="bg-indigo-600 hover:bg-indigo-700 focus:ring-indigo-500 w-full sm:w-auto"
          leftIcon={<Send className="h-4 w-4" />}
          loading={submitMutation.isPending}
          onClick={() => setShowConfirm(true)}
        >
          Submit Quiz
        </Button>
      </div>

      {/* Confirm dialog */}
      <ConfirmDialog
        isOpen={showConfirm}
        onClose={() => setShowConfirm(false)}
        onConfirm={() => submitMutation.mutate()}
        title="Submit Quiz"
        message="Are you sure? You cannot change your answers after submission."
        confirmLabel="Submit"
        cancelLabel="Keep editing"
        variant="warning"
        loading={submitMutation.isPending}
      />
    </div>
  );
};
