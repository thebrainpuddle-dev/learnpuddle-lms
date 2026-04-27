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
import type { Course, AssignmentScopeFilter, AdminAssignment } from './types';
import { useAssignmentValidation } from './useAssignmentValidation';

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
  const [assignmentScopeFilter, setAssignmentScopeFilter] = useState<AssignmentScopeFilter>('ALL');
  const [selectedAssignmentId, setSelectedAssignmentId] = useState<string | null>(null);
  const [isCreatingNewAssignment, setIsCreatingNewAssignment] = useState(false);
  const [assignmentForm, setAssignmentForm] = useState<AdminAssignmentPayload>(buildEmptyAssignmentForm());
  const [aiQuestionCount, setAiQuestionCount] = useState(6);
  const [aiIncludeShortAnswer, setAiIncludeShortAnswer] = useState(true);
  const [aiTitleHint, setAiTitleHint] = useState('');
  const aiModelLabel = 'Ollama (backend-configured, default: mistral) with deterministic fallback';

  // Validation helpers
  const { validateAssignmentForm, sanitizeAssignmentQuestions } = useAssignmentValidation(assignmentForm);

  // ── Queries ─────────────────────────────────────────────────────────
  const { data: assignmentList = [], isLoading: assignmentListLoading } = useQuery({
    queryKey: ['courseAssignments', courseId, assignmentScopeFilter],
    queryFn: () => adminService.listCourseAssignments(courseId!, { scope: assignmentScopeFilter }),
    enabled: Boolean(courseId) && isEditing && canManageAssignments,
  });

  const { data: selectedAssignment, isLoading: selectedAssignmentLoading } = useQuery({
    queryKey: ['courseAssignment', courseId, selectedAssignmentId],
    queryFn: () => adminService.getCourseAssignment(courseId!, selectedAssignmentId!),
    enabled: Boolean(courseId && selectedAssignmentId),
  });

  // ── Mutations ───────────────────────────────────────────────────────
  const createAssignmentMutation = useMutation({
    mutationFn: (payload: AdminAssignmentPayload) => adminService.createCourseAssignment(courseId!, payload),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ['courseAssignments', courseId] });
      setIsCreatingNewAssignment(false);
      setSelectedAssignmentId(created.id);
      toast.success('Assignment created', 'Assignment builder item is ready to edit.');
    },
    onError: (error: any) => {
      toast.error('Failed to create assignment', error?.response?.data?.error || 'Please review inputs and try again.');
    },
  });

  const updateAssignmentMutation = useMutation({
    mutationFn: ({ assignmentId, payload }: { assignmentId: string; payload: Partial<AdminAssignmentPayload> }) =>
      adminService.updateCourseAssignment(courseId!, assignmentId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['courseAssignments', courseId] });
      await queryClient.invalidateQueries({ queryKey: ['courseAssignment', courseId, selectedAssignmentId] });
      toast.success('Assignment saved', 'Builder changes have been saved.');
    },
    onError: (error: any) => {
      toast.error('Failed to save assignment', error?.response?.data?.error || 'Please review inputs and try again.');
    },
  });

  const deleteAssignmentMutation = useMutation({
    mutationFn: (assignmentId: string) => adminService.deleteCourseAssignment(courseId!, assignmentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['courseAssignments', courseId] });
      setSelectedAssignmentId(null);
      setIsCreatingNewAssignment(false);
      setAssignmentForm(buildEmptyAssignmentForm());
      toast.success('Assignment deleted', 'The assignment was removed from this course.');
    },
    onError: (error: any) => {
      toast.error('Failed to delete assignment', error?.response?.data?.error || 'Please try again.');
    },
  });

  const aiGenerateMutation = useMutation({
    mutationFn: () =>
      adminService.aiGenerateCourseAssignment(courseId!, {
        scope_type: assignmentForm.scope_type,
        module_id: assignmentForm.scope_type === 'MODULE' ? assignmentForm.module_id : null,
        question_count: aiQuestionCount,
        include_short_answer: aiIncludeShortAnswer,
        title_hint: aiTitleHint || assignmentForm.title || undefined,
      }),
    onSuccess: async (assignment) => {
      await queryClient.invalidateQueries({ queryKey: ['courseAssignments', courseId] });
      setIsCreatingNewAssignment(false);
      setSelectedAssignmentId(assignment.id);
      toast.success('AI assignment generated', 'Review and save the generated questions.');
    },
    onError: (error: any) => {
      toast.error('AI generation failed', error?.response?.data?.error || 'Please try again.');
    },
  });

  // ── Sync selected assignment to form ────────────────────────────────
  useEffect(() => {
    if (!assignmentList.length) return;
    if (!selectedAssignmentId && !isCreatingNewAssignment) {
      setSelectedAssignmentId(assignmentList[0].id);
      return;
    }
    if (!assignmentList.find((item: AdminAssignment) => item.id === selectedAssignmentId)) {
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
        ? (course?.modules || []).find((module) => module.id === assignmentForm.module_id) || null
        : null;

    if (assignmentForm.scope_type === 'MODULE' && !selectedModule)
      return { enabled: false, reason: 'Select a module first.', summary: 'No module selected' };

    const scopedContents =
      assignmentForm.scope_type === 'MODULE'
        ? selectedModule?.contents || []
        : (course?.modules || []).flatMap((module) => module.contents || []);

    if (!scopedContents.length)
      return { enabled: false, reason: 'Add content first. AI needs text, documents, or a processed video transcript.', summary: 'No content available in selected scope' };

    const textCount = scopedContents.filter((c) => c.content_type === 'TEXT' && Boolean(c.text_content?.replace(/<[^>]+>/g, '').trim())).length;
    const documentCount = scopedContents.filter((c) => c.content_type === 'DOCUMENT' && Boolean(c.file_url)).length;
    const readyVideoCount = scopedContents.filter((c) => c.content_type === 'VIDEO' && (c.video_status === 'READY' || (!c.video_status && Boolean(c.file_url)))).length;
    const processingVideoCount = scopedContents.filter((c) => c.content_type === 'VIDEO' && c.video_status === 'PROCESSING').length;

    const enabled = textCount > 0 || documentCount > 0 || readyVideoCount > 0;
    if (!enabled && processingVideoCount > 0)
      return { enabled: false, reason: 'Video processing is in progress. AI generation unlocks once transcript is ready.', summary: `${processingVideoCount} video(s) processing` };
    if (!enabled)
      return { enabled: false, reason: 'Upload text, document, or a processed video to generate AI assignments.', summary: 'No eligible source material found' };

    const summaryParts: string[] = [];
    if (readyVideoCount) summaryParts.push(`${readyVideoCount} transcript-ready video`);
    if (documentCount) summaryParts.push(`${documentCount} document`);
    if (textCount) summaryParts.push(`${textCount} text block`);
    return { enabled: true, reason: '', summary: `Using ${summaryParts.join(', ')}` };
  }, [assignmentForm.module_id, assignmentForm.scope_type, course]);

  // ── Question helpers ────────────────────────────────────────────────
  const updateAssignmentQuestion = useCallback(
    (questionIndex: number, updater: (question: AdminQuizQuestion) => AdminQuizQuestion) => {
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
      return { ...prev, questions: questions.map((q, idx) => ({ ...q, order: idx + 1 })) };
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

  const handleSaveAssignmentBuilder = useCallback(() => {
    if (!courseId) return;
    const validationError = validateAssignmentForm();
    if (validationError) { toast.error('Assignment validation failed', validationError); return; }

    const payload: AdminAssignmentPayload = {
      ...assignmentForm,
      title: assignmentForm.title.trim(),
      description: assignmentForm.description || '',
      instructions: assignmentForm.instructions || '',
      module_id: assignmentForm.scope_type === 'MODULE' ? assignmentForm.module_id : null,
      questions: assignmentForm.assignment_type === 'QUIZ' ? sanitizeAssignmentQuestions(assignmentForm.questions || []) : [],
    };
    if (!payload.due_date) delete payload.due_date;

    if (selectedAssignmentId) {
      updateAssignmentMutation.mutate({ assignmentId: selectedAssignmentId, payload });
    } else {
      createAssignmentMutation.mutate(payload);
    }
  }, [courseId, assignmentForm, selectedAssignmentId, toast, validateAssignmentForm, sanitizeAssignmentQuestions, updateAssignmentMutation, createAssignmentMutation]);

  return {
    assignmentScopeFilter, setAssignmentScopeFilter,
    assignmentList, assignmentListLoading,
    selectedAssignmentId, setSelectedAssignmentId,
    selectedAssignment, selectedAssignmentLoading,
    isCreatingNewAssignment, setIsCreatingNewAssignment,
    assignmentForm, setAssignmentForm,
    aiQuestionCount, setAiQuestionCount,
    aiIncludeShortAnswer, setAiIncludeShortAnswer,
    aiTitleHint, setAiTitleHint,
    aiModelLabel, aiSourceState,
    createAssignmentMutation, updateAssignmentMutation, deleteAssignmentMutation, aiGenerateMutation,
    resetAssignmentBuilder, updateAssignmentQuestion, addAssignmentQuestion, removeAssignmentQuestion, handleSaveAssignmentBuilder,
  };
}
