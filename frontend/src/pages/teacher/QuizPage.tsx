import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useMutation, useQuery } from '@tanstack/react-query';
import { teacherService } from '../../services/teacherService';
import { usePageTitle } from '../../hooks/usePageTitle';
import { ArrowLeftIcon } from '@heroicons/react/24/outline';
import { Button } from '../../components/common';

export const QuizPage: React.FC = () => {
  usePageTitle('Quiz');
  const { assignmentId } = useParams<{ assignmentId: string }>();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ['quiz', assignmentId],
    enabled: Boolean(assignmentId),
    queryFn: () => teacherService.getQuiz(assignmentId as string),
  });

  const initialAnswers = useMemo(() => data?.submission?.answers || {}, [data?.submission?.answers]);
  const [answers, setAnswers] = useState<Record<string, any>>(initialAnswers);
  useEffect(() => {
    setAnswers(initialAnswers);
  }, [initialAnswers]);

  const submitMutation = useMutation({
    mutationFn: () => teacherService.submitQuiz(assignmentId as string, answers),
    onSuccess: () => {
      // refetch by hard reload of query is fine; react-query will update
      navigate('/teacher/assignments');
    },
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600"></div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900">
          <ArrowLeftIcon className="h-4 w-4 mr-2" />
          Back
        </button>
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h1 className="text-lg font-semibold text-gray-900">Quiz not found</h1>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <button onClick={() => navigate('/teacher/assignments')} className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900">
          <ArrowLeftIcon className="h-4 w-4 mr-2" />
          Back to assignments
        </button>
        <div className="text-sm text-gray-600">Quiz</div>
      </div>

      <div className="space-y-6 rounded-xl border border-gray-200 bg-white p-4 sm:p-6">
        <h1 className="text-xl font-bold text-gray-900">Quiz</h1>

        {data.questions.map((q) => (
          <div key={q.id} className="rounded-xl border border-gray-200 p-4">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
              <div>
                <p className="text-sm text-gray-500 mb-1">
                  Q{q.order} • {
                    q.question_type === 'MCQ'
                      ? (q.selection_mode === 'MULTIPLE' ? 'Multiple select' : 'Multiple choice')
                      : q.question_type === 'TRUE_FALSE'
                      ? 'True / False'
                      : 'Short answer'
                  } • {q.points} pt
                </p>
                <p className="font-medium text-gray-900">{q.prompt}</p>
              </div>
            </div>

            {q.question_type === 'MCQ' && q.selection_mode === 'SINGLE' ? (
              <div className="mt-4 space-y-2">
                {q.options.map((opt, idx) => (
                  <label key={idx} className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                    <input
                      type="radio"
                      name={`q-${q.id}`}
                      checked={answers[q.id]?.option_index === idx}
                      onChange={() => setAnswers((prev) => ({ ...prev, [q.id]: { option_index: idx } }))}
                      className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300"
                    />
                    <span className="text-sm text-gray-800">{opt}</span>
                  </label>
                ))}
              </div>
            ) : q.question_type === 'MCQ' && q.selection_mode === 'MULTIPLE' ? (
              <div className="mt-4 space-y-2">
                {q.options.map((opt, idx) => {
                  const selected: number[] = Array.isArray(answers[q.id]?.option_indices)
                    ? answers[q.id].option_indices
                    : [];
                  const checked = selected.includes(idx);
                  return (
                    <label key={idx} className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={(e) => {
                          const next = e.target.checked
                            ? [...selected, idx]
                            : selected.filter((value) => value !== idx);
                          setAnswers((prev) => ({ ...prev, [q.id]: { option_indices: next } }));
                        }}
                        className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300 rounded"
                      />
                      <span className="text-sm text-gray-800">{opt}</span>
                    </label>
                  );
                })}
              </div>
            ) : q.question_type === 'TRUE_FALSE' ? (
              <div className="mt-4 flex flex-col gap-3 sm:flex-row">
                {[true, false].map((choice) => (
                  <label key={String(choice)} className="inline-flex items-center gap-2 rounded-lg border border-gray-200 px-3 py-2 cursor-pointer hover:bg-gray-50">
                    <input
                      type="radio"
                      name={`q-${q.id}`}
                      checked={answers[q.id]?.value === choice}
                      onChange={() => setAnswers((prev) => ({ ...prev, [q.id]: { value: choice } }))}
                      className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-gray-300"
                    />
                    <span className="text-sm text-gray-800">{choice ? 'True' : 'False'}</span>
                  </label>
                ))}
              </div>
            ) : (
              <div className="mt-4">
                <textarea
                  rows={3}
                  value={answers[q.id]?.text || ''}
                  onChange={(e) => setAnswers((prev) => ({ ...prev, [q.id]: { text: e.target.value } }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  placeholder="Type your answer..."
                />
              </div>
            )}
          </div>
        ))}

        <div className="flex items-center justify-end">
          <Button
            variant="primary"
            className="w-full sm:w-auto"
            onClick={() => submitMutation.mutate()}
            loading={submitMutation.isPending}
          >
            Submit quiz
          </Button>
        </div>
      </div>
    </div>
  );
};
