import React, { useMemo, useState } from 'react';
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
      <div className="flex items-center justify-between">
        <button onClick={() => navigate('/teacher/assignments')} className="inline-flex items-center text-sm text-gray-600 hover:text-gray-900">
          <ArrowLeftIcon className="h-4 w-4 mr-2" />
          Back to assignments
        </button>
        <div className="text-sm text-gray-600">Quiz</div>
      </div>

      <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-6">
        <h1 className="text-xl font-bold text-gray-900">Quiz</h1>

        {data.questions.map((q) => (
          <div key={q.id} className="border border-gray-200 rounded-xl p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm text-gray-500 mb-1">
                  Q{q.order} • {q.question_type === 'MCQ' ? 'Multiple choice' : 'Short answer'} • {q.points} pt
                </p>
                <p className="font-medium text-gray-900">{q.prompt}</p>
              </div>
            </div>

            {q.question_type === 'MCQ' ? (
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
          <Button variant="primary" onClick={() => submitMutation.mutate()} loading={submitMutation.isPending}>
            Submit quiz
          </Button>
        </div>
      </div>
    </div>
  );
};

