// course-editor/useAssignmentState.ts
//
// Sub-hook: assignment/quiz CRUD, question management, AI generation.

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  adminService,
  type AdminAssignmentPayload,
  type AdminQuizQuestion,
} from '../../../services/adminService';
import type {
  Course,
  AssignmentScopeFilter,
  AdminAssignment,
} from './types';

export const buildEmptyQuestion = (order: number): AdminQuizQuestion => ({
  order,
  question_type: 'MCQ',
  selection_mode: 'SINGLE',
  prompt: '',
  options: ['Option 1', 'Option 2'],
  correct_answer: { option_index: 0 },
  explanation: '',
  points: 1,
});

const buildEmptyAssignmentForm = (): AdminAssignmentPayload => ({
  title: '',
  description: '',
  instructions: '',
  due_date: null,
  max_score: 100,
  passing_score: 70,
  is_mandatory: true,
  is_active: true,
  scope_type: 'COURSE',
  module_id: null,
  assignment_type: 'QUIZ',
  questions: [buildEmptyQuestion(1)],
});

export interface UseAssignmentStateParams {
  courseId: string | undefined;
  isEditing: boolean;
  canManageAssignments: boolean;
  course: Course | undefined;
  toast: {
    success: (title: string, message: string) => void;
    error: (title: string, message: string) => void;
  };
}

export function useAssignmentState({
  courseId,
  isEditing,
  canManageAssignments,
  course,
  toast,
}: UseAssignmentStateParams) {
  const queryClient = useQueryClient();

  // ── State ───────────────────────────────────────────────────────────
  const [assignmentScopeFilter, setAssignmentScopeFilter] =
    useState<AssignmentScopeFilter>('ALL');
  const [selectedAssignmentId, setSelectedAssignmentId] = useState<
    string | null
  >(null);
  const [isCreatingNewAssignment, setIsCreatingNewAssignment] = useState(false);
  const [assignmentForm, setAssignmentForm] =
    useState<AdminAssignmentPayload>(buildEmptyAssignmentForm());
  const [aiQuestionCount, setAiQuestionCount] = useState(6);
  const [aiIncludeShortAnswer, setAiIncludeShortAnswer] = useState(true);
  const [aiTitleHint, setAiTitleHint] = useState('');
  const aiModelLabel =
    'Ollama (backend-configured, default: mistral) with deterministic fallback';

  // ── Queries ─────────────────────────────────────────────────────────
  const { data: assignmentList = [], isLoading: assignmentListLoading } =
    useQuery({
      queryKey: ['courseAssignments', courseId, assignmentScopeFilter],
      queryFn: () =>
        adminService.listCourseAssignments(courseId!, {
          scope: assignmentScopeFilter,
        }),
      enabled: Boolean(courseId) && isEditing && canManageAssignments,
    });

  const { data: selectedAssignment, isLoading: selectedAssignmentLoading } =
    useQuery({
      queryKey: ['courseAssignment', courseId, selectedAssignmentId],
      queryFn: () =>
        adminService.getCourseAssignment(courseId!, selectedAssignmentId!),
      enabled: Boolean(courseId && selectedAssignmentId),
    });

  // ── Mutations ───────────────────────────────────────────────────────
  const createAssignmentMutation = useMutation({
    mutationFn: (payload: AdminAssignmentPayload) =>
      adminService.createCourseAssignment(courseId!, payload),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({
        queryKey: ['courseAssignments', courseId],
      });
      setIsCreatingNewAssignment(false);
      setSelectedAssignmentId(created.id);
      toast.success(
        'Assignment created',
        'Assignment builder item is ready to edit.',
      );
    },
    onError: (error: any) => {
      const msg =
        error?.response?.data?.error || 'Please review inputs and try again.';
      toast.error('Failed to create assignment', msg);
    },
  });

  const updateAssignmentMutation = useMutation({
    mutationFn: ({
      assignmentId,
      payload,
    }: {
      assignmentId: string;
      payload: Partial<AdminAssignmentPayload>;
    }) =>
      adminService.updateCourseAssignment(courseId!, assignmentId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['courseAssignments', courseId],
      });
      await queryClient.invalidateQueries({
        queryKey: ['courseAssignment', courseId, selectedAssignmentId],
      });
      toast.success('Assignment saved', 'Builder changes have been saved.');
    },
    onError: (error: any) => {
      const msg =
        error?.response?.data?.error || 'Please review inputs and try again.';
      toast.error('Failed to save assignment', msg);
    },
  });

  const deleteAssignmentMutation = useMutation({
    mutationFn: (assignmentId: string) =>
      adminService.deleteCourseAssignment(courseId!, assignmentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['courseAssignments', courseId],
      });
      setSelectedAssignmentId(null);
      setIsCreatingNewAssignment(false);
      setAssignmentForm(buildEmptyAssignmentForm());
      toast.success(
        'Assignment deleted',
        'The assignment was removed from this course.',
      );
    },
    onError: (error: any) => {
      const msg = error?.response?.data?.error || 'Please try again.';
      toast.error('Failed to delete assignment', msg);
    },
  });

  const aiGenerateMutation = useMutation({
    mutationFn: () =>
      adminService.aiGenerateCourseAssignment(courseId!, {
        scope_type: assignmentForm.scope_type,
        module_id:
          assignmentForm.scope_type === 'MODULE'
            ? assignmentForm.module_id
            : null,
        question_count: aiQuestionCount,
        include_short_answer: aiIncludeShortAnswer,
        title_hint: aiTitleHint || assignmentForm.title || undefined,
      }),
    onSuccess: async (assignment) => {
      await queryClient.invalidateQueries({
        queryKey: ['courseAssignments', courseId],
      });
      setIsCreatingNewAssignment(false);
      setSelectedAssignmentId(assignment.id);
      toast.success(
        'AI assignment generated',
        'Review and save the generated questions.',
      );
    },
    onError: (error: any) => {
      const msg = error?.response?.data?.error || 'Please try again.';
      toast.error('AI generation failed', msg);
    },
  });

  // ── Sync selected assignment to form ────────────────────────────────
  useEffect(() => {
    if (!assignmentList.length) return;
    if (!selectedAssignmentId && !isCreatingNewAssignment) {
      setSelectedAssignmentId(assignmentList[0].id);
      return;
    }
    if (
      !assignmentList.find(
        (item: AdminAssignment) => item.id === selectedAssignmentId,
      )
    ) {
      setSelectedAssignmentId(assignmentList[0].id);
    }
  }, [assignmentList, selectedAssignmentId, isCreatingNewAssignment]);

  useEffect(() => {
    if (!selectedAssignment) return;
    setAssignmentForm({
      title: selectedAssignment.title,
      description: selectedAssignment.description || '',
      instructions: selectedAssignment.instructions || '',
      due_date: selectedAssignment.due_date || null,
      max_score: Number(selectedAssignment.max_score || 100),
      passing_score: Number(selectedAssignment.passing_score || 70),
      is_mandatory: selectedAssignment.is_mandatory,
      is_active: selectedAssignment.is_active,
      scope_type: selectedAssignment.scope_type,
      module_id: selectedAssignment.module_id,
      assignment_type: selectedAssignment.assignment_type,
      questions: selectedAssignment.questions?.length
        ? selectedAssignment.questions.map((q: AdminQuizQuestion) => ({
            ...q,
            selection_mode: q.selection_mode || 'SINGLE',
            options: q.options || [],
            correct_answer: q.correct_answer || {},
          }))
        : [],
    });
  }, [selectedAssignment]);

  // ── AI source state ─────────────────────────────────────────────────
  const aiSourceState = useMemo(() => {
    const selectedModule =
      assignmentForm.scope_type === 'MODULE'
        ? (course?.modules || []).find(
            (module) => module.id === assignmentForm.module_id,
          ) || null
        : null;

    if (assignmentForm.scope_type === 'MODULE' && !selectedModule) {
      return {
        enabled: false,
        reason: 'Select a module first.',
        summary: 'No module selected',
      };
    }

    const scopedContents =
      assignmentForm.scope_type === 'MODULE'
        ? selectedModule?.contents || []
        : (course?.modules || []).flatMap((module) => module.contents || []);

    if (!scopedContents.length) {
      return {
        enabled: false,
        reason:
          'Add content first. AI needs text, documents, or a processed video transcript.',
        summary: 'No content available in selected scope',
      };
    }

    const textCount = scopedContents.filter(
      (content) =>
        content.content_type === 'TEXT' &&
        Boolean(content.text_content?.replace(/<[^>]+>/g, '').trim()),
    ).length;
    const documentCount = scopedContents.filter(
      (content) =>
        content.content_type === 'DOCUMENT' && Boolean(content.file_url),
    ).length;
    const readyVideoCount = scopedContents.filter(
      (content) =>
        content.content_type === 'VIDEO' &&
        (content.video_status === 'READY' ||
          (!content.video_status && Boolean(content.file_url))),
    ).length;
    const processingVideoCount = scopedContents.filter(
      (content) =>
        content.content_type === 'VIDEO' &&
        content.video_status === 'PROCESSING',
    ).length;

    const enabled = textCount > 0 || documentCount > 0 || readyVideoCount > 0;
    if (!enabled && processingVideoCount > 0) {
      return {
        enabled: false,
        reason:
          'Video processing is in progress. AI generation unlocks once transcript is ready.',
        summary: `${processingVideoCount} video(s) processing`,
      };
    }
    if (!enabled) {
      return {
        enabled: false,
        reason:
          'Upload text, document, or a processed video to generate AI assignments.',
        summary: 'No eligible source material found',
      };
    }

    const summaryParts: string[] = [];
    if (readyVideoCount)
      summaryParts.push(`${readyVideoCount} transcript-ready video`);
    if (documentCount) summaryParts.push(`${documentCount} document`);
    if (textCount) summaryParts.push(`${textCount} text block`);

    return {
      enabled: true,
      reason: '',
      summary: `Using ${summaryParts.join(', ')}`,
    };
  }, [assignmentForm.module_id, assignmentForm.scope_type, course]);

  // ── Question helpers ────────────────────────────────────────────────
  const updateAssignmentQuestion = useCallback(
    (
      questionIndex: number,
      updater: (question: AdminQuizQuestion) => AdminQuizQuestion,
    ) => {
      setAssignmentForm((prev) => {
        const questions = [...(prev.questions || [])];
        questions[questionIndex] = updater(questions[questionIndex]);
        return { ...prev, questions };
      });
    },
    [],
  );

  const addAssignmentQuestion = useCallback(() => {
    setAssignmentForm((prev) => {
      const questions = [...(prev.questions || [])];
      questions.push(buildEmptyQuestion(questions.length + 1));
      return { ...prev, questions };
    });
  }, []);

  const removeAssignmentQuestion = useCallback((questionIndex: number) => {
    setAssignmentForm((prev) => {
      const questions = [...(prev.questions || [])];
      questions.splice(questionIndex, 1);
      const reordered = questions.map((q, idx) => ({
        ...q,
        order: idx + 1,
      }));
      return { ...prev, questions: reordered };
    });
  }, []);

  const resetAssignmentBuilder = useCallback(() => {
    setIsCreatingNewAssignment(true);
    setSelectedAssignmentId(null);
    setAssignmentForm(buildEmptyAssignmentForm());
    setAiTitleHint('');
    setAiQuestionCount(6);
    setAiIncludeShortAnswer(true);
  }, []);

  // ── Validation & sanitization ───────────────────────────────────────
  const validateAssignmentForm = useCallback((): string | null => {
    if (!assignmentForm.title.trim())
      return 'Assignment title is required.';
    if (
      assignmentForm.scope_type === 'MODULE' &&
      !assignmentForm.module_id
    )
      return 'Select a module for module-scoped assignments.';
    if (assignmentForm.assignment_type === 'QUIZ') {
      if (
        !assignmentForm.questions ||
        assignmentForm.questions.length === 0
      )
        return 'At least one question is required for quiz assignments.';
      for (let i = 0; i < assignmentForm.questions.length; i += 1) {
        const q = assignmentForm.questions[i];
        if (!q.prompt.trim())
          return `Question ${i + 1} prompt is required.`;
        if (q.question_type === 'MCQ') {
          const options = (q.options || [])
            .map((opt) => opt.trim())
            .filter(Boolean);
          if (options.length < 2)
            return `Question ${i + 1} needs at least 2 options.`;
          if (q.selection_mode === 'SINGLE') {
            const idx = Number(q.correct_answer?.option_index);
            if (!Number.isInteger(idx) || idx < 0 || idx >= options.length)
              return `Question ${i + 1} has an invalid correct option.`;
          } else {
            const indices = Array.isArray(
              q.correct_answer?.option_indices,
            )
              ? q.correct_answer.option_indices
              : [];
            if (indices.length < 2)
              return `Question ${i + 1} needs at least 2 correct options for multi-select.`;
          }
        }
        if (
          q.question_type === 'TRUE_FALSE' &&
          typeof q.correct_answer?.value !== 'boolean'
        ) {
          return `Question ${i + 1} must set True or False as the correct answer.`;
        }
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
        options: (question.options || [])
          .map((opt) => opt.trim())
          .filter(Boolean),
        points: Number(
          question.points ||
            (question.question_type === 'SHORT_ANSWER' ? 2 : 1),
        ),
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
              : {
                  option_index: Number(
                    question.correct_answer?.option_index ?? 0,
                  ),
                }
            : question.question_type === 'TRUE_FALSE'
            ? { value: Boolean(question.correct_answer?.value) }
            : {},
      })),
    [],
  );

  const handleSaveAssignmentBuilder = useCallback(() => {
    if (!courseId) return;
    const validationError = validateAssignmentForm();
    if (validationError) {
      toast.error('Assignment validation failed', validationError);
      return;
    }

    const payload: AdminAssignmentPayload = {
      ...assignmentForm,
      title: assignmentForm.title.trim(),
      description: assignmentForm.description || '',
      instructions: assignmentForm.instructions || '',
      module_id:
        assignmentForm.scope_type === 'MODULE'
          ? assignmentForm.module_id
          : null,
      questions:
        assignmentForm.assignment_type === 'QUIZ'
          ? sanitizeAssignmentQuestions(assignmentForm.questions || [])
          : [],
    };
    if (!payload.due_date) {
      delete payload.due_date;
    }

    if (selectedAssignmentId) {
      updateAssignmentMutation.mutate({
        assignmentId: selectedAssignmentId,
        payload,
      });
    } else {
      createAssignmentMutation.mutate(payload);
    }
  }, [
    courseId,
    assignmentForm,
    selectedAssignmentId,
    toast,
    validateAssignmentForm,
    sanitizeAssignmentQuestions,
    updateAssignmentMutation,
    createAssignmentMutation,
  ]);

  return {
    // State
    assignmentScopeFilter,
    setAssignmentScopeFilter,
    assignmentList,
    assignmentListLoading,
    selectedAssignmentId,
    setSelectedAssignmentId,
    selectedAssignment,
    selectedAssignmentLoading,
    isCreatingNewAssignment,
    setIsCreatingNewAssignment,
    assignmentForm,
    setAssignmentForm,

    // AI
    aiQuestionCount,
    setAiQuestionCount,
    aiIncludeShortAnswer,
    setAiIncludeShortAnswer,
    aiTitleHint,
    setAiTitleHint,
    aiModelLabel,
    aiSourceState,

    // Mutations
    createAssignmentMutation,
    updateAssignmentMutation,
    deleteAssignmentMutation,
    aiGenerateMutation,

    // Handlers
    resetAssignmentBuilder,
    updateAssignmentQuestion,
    addAssignmentQuestion,
    removeAssignmentQuestion,
    handleSaveAssignmentBuilder,
  };
}
