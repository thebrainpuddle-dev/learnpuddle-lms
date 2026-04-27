// course-editor/useAssignmentValidation.ts
//
// Pure helpers for validating and sanitizing assignment/quiz forms
// before submission. Extracted from useAssignmentState to keep files < 400 lines.

import { useCallback } from 'react';
import type { AdminAssignmentPayload, AdminQuizQuestion } from './types';

export function useAssignmentValidation(assignmentForm: AdminAssignmentPayload) {
  const validateAssignmentForm = useCallback((): string | null => {
    if (!assignmentForm.title.trim()) return 'Assignment title is required.';
    if (assignmentForm.scope_type === 'MODULE' && !assignmentForm.module_id)
      return 'Select a module for module-scoped assignments.';
    if (assignmentForm.assignment_type === 'QUIZ') {
      if (!assignmentForm.questions || assignmentForm.questions.length === 0)
        return 'At least one question is required for quiz assignments.';
      for (let i = 0; i < assignmentForm.questions.length; i += 1) {
        const q = assignmentForm.questions[i];
        if (!q.prompt.trim()) return `Question ${i + 1} prompt is required.`;
        if (q.question_type === 'MCQ') {
          const options = (q.options || []).map((opt) => opt.trim()).filter(Boolean);
          if (options.length < 2) return `Question ${i + 1} needs at least 2 options.`;
          if (q.selection_mode === 'SINGLE') {
            const idx = Number(q.correct_answer?.option_index);
            if (!Number.isInteger(idx) || idx < 0 || idx >= options.length)
              return `Question ${i + 1} has an invalid correct option.`;
          } else {
            const indices = Array.isArray(q.correct_answer?.option_indices)
              ? q.correct_answer.option_indices
              : [];
            if (indices.length < 2)
              return `Question ${i + 1} needs at least 2 correct options for multi-select.`;
          }
        }
        if (q.question_type === 'TRUE_FALSE' && typeof q.correct_answer?.value !== 'boolean')
          return `Question ${i + 1} must set True or False as the correct answer.`;
      }
    }
    return null;
  }, [assignmentForm]);

  const sanitizeAssignmentQuestions = useCallback(
    (questions: AdminQuizQuestion[]) =>
      questions.map((question, index) => ({
        ...question,
        order: index + 1,
        prompt: question.prompt.trim(),
        options: (question.options || []).map((opt) => opt.trim()).filter(Boolean),
        points: Number(question.points || (question.question_type === 'SHORT_ANSWER' ? 2 : 1)),
        correct_answer:
          question.question_type === 'MCQ'
            ? question.selection_mode === 'MULTIPLE'
              ? {
                  option_indices: (
                    Array.isArray(question.correct_answer?.option_indices)
                      ? question.correct_answer.option_indices
                      : []
                  )
                    .map((value: number) => Number(value))
                    .filter((value: number) => Number.isInteger(value)),
                }
              : { option_index: Number(question.correct_answer?.option_index ?? 0) }
            : question.question_type === 'TRUE_FALSE'
            ? { value: Boolean(question.correct_answer?.value) }
            : {},
      })),
    [],
  );

  return { validateAssignmentForm, sanitizeAssignmentQuestions };
}
