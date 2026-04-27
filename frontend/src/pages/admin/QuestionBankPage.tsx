// src/pages/admin/QuestionBankPage.tsx
//
// Admin Question Bank management UI — list banks, view their questions,
// create/edit/delete banks and questions via RHF + Zod modals.

import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { useFieldArray, Controller } from 'react-hook-form';
import { format, parseISO, isValid } from 'date-fns';
import type { ColumnDef } from '@tanstack/react-table';
import { DataTable, DataTableColumnHeader } from '../../components/ui/data-table';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/common/Button';
import { FormField } from '../../components/common/FormField';
import { Input } from '../../components/common/Input';
import { Loading, useToast, ConfirmDialog } from '../../components/common';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
} from '../../components/ui/dialog';
import { useZodForm } from '../../hooks/useZodForm';
import {
  adminQuestionBankService,
  type QuestionBank,
  type Question,
  type QuestionType,
  type Difficulty,
} from '../../services/adminQuestionBankService';
import {
  BookOpenIcon,
  PlusIcon,
  PencilIcon,
  TrashIcon,
  ArrowLeftIcon,
  CheckCircleIcon,
  XCircleIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';

// ── Constants ─────────────────────────────────────────────────────────────────

const QUESTION_TYPE_LABELS: Record<QuestionType, string> = {
  MCQ:        'Single Choice',
  MULTI:      'Multi Choice',
  SHORT:      'Short Answer',
  TRUE_FALSE: 'True / False',
  ESSAY:      'Essay',
};

const DIFFICULTY_LABELS: Record<Difficulty, string> = {
  EASY:   'Easy',
  MEDIUM: 'Medium',
  HARD:   'Hard',
};

const DIFFICULTY_VARIANTS: Record<Difficulty, 'success' | 'warning' | 'destructive'> = {
  EASY:   'success',
  MEDIUM: 'warning',
  HARD:   'destructive',
};

const CHOICE_TYPES: QuestionType[] = ['MCQ', 'MULTI', 'TRUE_FALSE'];

function fmtDate(raw: string): string {
  try {
    const d = parseISO(raw);
    return isValid(d) ? format(d, 'dd MMM yyyy') : '—';
  } catch {
    return '—';
  }
}

// ── Zod Schemas ───────────────────────────────────────────────────────────────

const BankSchema = z.object({
  title:       z.string().min(1, 'Title is required').max(200),
  description: z.string().max(2000).optional().or(z.literal('')),
  is_active:   z.boolean().default(true),
});
type BankData = z.infer<typeof BankSchema>;

const ChoiceSchema = z.object({
  text:       z.string().min(1, 'Choice text is required'),
  is_correct: z.boolean().default(false),
  order:      z.number().default(0),
});

const QuestionSchema = z
  .object({
    question_type: z.enum(['MCQ', 'MULTI', 'SHORT', 'TRUE_FALSE', 'ESSAY']),
    prompt:        z.string().min(1, 'Question prompt is required').max(4000),
    points:        z.coerce.number().min(0).max(100).default(1),
    difficulty:    z.enum(['EASY', 'MEDIUM', 'HARD']).default('MEDIUM'),
    explanation:   z.string().max(2000).optional().or(z.literal('')),
    choices:       z.array(ChoiceSchema).default([]),
  })
  .superRefine((data, ctx) => {
    const { question_type, choices } = data;

    // Only validate shape for choice-bearing question types.
    if (!CHOICE_TYPES.includes(question_type as QuestionType)) return;

    // All choice text must be non-empty after trim.
    const hasEmptyText = choices.some((c) => !c.text.trim());
    if (hasEmptyText) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['choices'],
        message: 'All choices must have non-empty text.',
      });
      return;
    }

    // Minimum 2 choices for all choice-bearing types.
    if (choices.length < 2) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['choices'],
        message: `${question_type} requires at least 2 choices.`,
      });
      return;
    }

    const correctCount = choices.filter((c) => c.is_correct).length;

    if (question_type === 'MCQ' || question_type === 'TRUE_FALSE') {
      if (correctCount !== 1) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['choices'],
          message: `${question_type} requires exactly 1 correct choice.`,
        });
      }
    } else if (question_type === 'MULTI') {
      if (correctCount < 2) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['choices'],
          message: 'MULTI requires at least 2 correct choices.',
        });
      }
    }
  });
type QuestionFormData = z.infer<typeof QuestionSchema>;

// ── Bank Form Modal ───────────────────────────────────────────────────────────

interface BankModalProps {
  open:        boolean;
  onClose:     () => void;
  editingBank: QuestionBank | null;
  onSaved:     () => void;
}

function BankModal({ open, onClose, editingBank, onSaved }: BankModalProps) {
  const toast = useToast();
  const form = useZodForm({
    schema: BankSchema,
    defaultValues: editingBank
      ? { title: editingBank.title, description: editingBank.description, is_active: editingBank.is_active }
      : { title: '', description: '', is_active: true },
  });

  // Reset when editingBank changes
  React.useEffect(() => {
    form.reset(
      editingBank
        ? { title: editingBank.title, description: editingBank.description, is_active: editingBank.is_active }
        : { title: '', description: '', is_active: true },
    );
  }, [editingBank, form]);

  const handleClose = () => { form.reset(); onClose(); };

  const onSubmit = form.handleSubmit(async (data: BankData) => {
    try {
      if (editingBank) {
        await adminQuestionBankService.updateBank(editingBank.id, data);
        toast.success('Bank updated', `"${data.title}" has been updated.`);
      } else {
        await adminQuestionBankService.createBank(data);
        toast.success('Bank created', `"${data.title}" is ready.`);
      }
      onSaved();
      handleClose();
    } catch {
      toast.error('Failed', 'Could not save the question bank.');
    }
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent onClose={handleClose} className="sm:max-w-md">
        <form onSubmit={onSubmit} noValidate>
          <DialogHeader className="mb-5">
            <DialogTitle>{editingBank ? 'Edit Question Bank' : 'New Question Bank'}</DialogTitle>
          </DialogHeader>

          <div className="space-y-4">
            <FormField
              control={form.control}
              name="title"
              label="Bank Name"
              placeholder="e.g. Grade 10 Mathematics"
            />

            <Controller
              control={form.control}
              name="description"
              render={({ field }) => (
                <div>
                  <label className="block text-[13px] font-medium text-slate-700 mb-1">
                    Description <span className="text-slate-400 font-normal">(optional)</span>
                  </label>
                  <textarea
                    {...field}
                    rows={3}
                    className="w-full px-3 py-2 border border-slate-200/80 rounded-xl text-sm focus:ring-2 focus:ring-primary-200 focus:border-primary-400 focus:outline-none"
                    placeholder="A brief description of this question bank..."
                  />
                </div>
              )}
            />

            <Controller
              control={form.control}
              name="is_active"
              render={({ field }) => (
                <label className="flex items-center gap-3 cursor-pointer">
                  <div className="relative">
                    <input
                      type="checkbox"
                      checked={field.value}
                      onChange={(e) => field.onChange(e.target.checked)}
                      className="sr-only peer"
                    />
                    <div className="w-11 h-6 bg-slate-200 peer-focus:ring-4 peer-focus:ring-primary-200 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600" />
                  </div>
                  <span className="text-[13px] font-medium text-slate-700">Active</span>
                </label>
              )}
            />
          </div>

          <DialogFooter className="mt-6">
            <Button type="button" variant="outline" onClick={handleClose}>Cancel</Button>
            <Button type="submit" loading={form.formState.isSubmitting}>
              {editingBank ? 'Save Changes' : 'Create Bank'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Question Form Modal ───────────────────────────────────────────────────────

interface QuestionModalProps {
  open:            boolean;
  onClose:         () => void;
  bankId:          string;
  editingQuestion: Question | null;
  onSaved:         () => void;
}

function QuestionModal({ open, onClose, bankId, editingQuestion, onSaved }: QuestionModalProps) {
  const toast = useToast();
  const form = useZodForm({
    schema: QuestionSchema,
    defaultValues: editingQuestion
      ? {
          question_type: editingQuestion.question_type,
          prompt:        editingQuestion.prompt,
          points:        editingQuestion.points,
          difficulty:    editingQuestion.difficulty,
          explanation:   editingQuestion.explanation,
          choices:       editingQuestion.choices.map((c) => ({
            text:       c.text,
            is_correct: c.is_correct,
            order:      c.order,
          })),
        }
      : { question_type: 'MCQ', prompt: '', points: 1, difficulty: 'MEDIUM', explanation: '', choices: [
          { text: '', is_correct: false, order: 0 },
          { text: '', is_correct: false, order: 1 },
        ]},
  });

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: 'choices',
  });

  const questionType = form.watch('question_type') as QuestionType;
  const needsChoices = CHOICE_TYPES.includes(questionType);

  // Seed TRUE_FALSE choices when type changes — only when creating a new question,
  // not when editing an existing one (would clobber loaded choice data).
  React.useEffect(() => {
    if (editingQuestion) return;
    if (questionType === 'TRUE_FALSE') {
      form.setValue('choices', [
        { text: 'True',  is_correct: true,  order: 0 },
        { text: 'False', is_correct: false, order: 1 },
      ]);
    } else if (!CHOICE_TYPES.includes(questionType)) {
      form.setValue('choices', []);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [questionType]);

  React.useEffect(() => {
    form.reset(
      editingQuestion
        ? {
            question_type: editingQuestion.question_type,
            prompt:        editingQuestion.prompt,
            points:        editingQuestion.points,
            difficulty:    editingQuestion.difficulty,
            explanation:   editingQuestion.explanation,
            choices:       editingQuestion.choices.map((c) => ({
              text: c.text, is_correct: c.is_correct, order: c.order,
            })),
          }
        : { question_type: 'MCQ', prompt: '', points: 1, difficulty: 'MEDIUM', explanation: '', choices: [
            { text: '', is_correct: false, order: 0 },
            { text: '', is_correct: false, order: 1 },
          ]},
    );
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingQuestion]);

  const handleClose = () => { form.reset(); onClose(); };

  const onSubmit = form.handleSubmit(async (data: QuestionFormData) => {
    try {
      const payload = {
        ...data,
        choices: needsChoices ? data.choices.map((c, i) => ({ ...c, order: i })) : [],
      };
      if (editingQuestion) {
        await adminQuestionBankService.updateQuestion(editingQuestion.id, payload);
        toast.success('Question updated', 'Changes saved.');
      } else {
        await adminQuestionBankService.createQuestion(bankId, payload);
        toast.success('Question added', 'New question added to bank.');
      }
      onSaved();
      handleClose();
    } catch {
      toast.error('Failed', 'Could not save the question.');
    }
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !v && handleClose()}>
      <DialogContent onClose={handleClose} className="sm:max-w-xl max-h-[90vh]">
        <form onSubmit={onSubmit} noValidate>
          <DialogHeader className="mb-5">
            <DialogTitle>{editingQuestion ? 'Edit Question' : 'Add Question'}</DialogTitle>
          </DialogHeader>

          <div className="space-y-4 overflow-y-auto pr-1">
            {/* Question type + difficulty row */}
            <div className="grid grid-cols-2 gap-4">
              <Controller
                control={form.control}
                name="question_type"
                render={({ field }) => (
                  <div>
                    <label className="block text-[13px] font-medium text-slate-700 mb-1">Type</label>
                    <select
                      {...field}
                      className="w-full cursor-pointer px-3 py-2 border border-slate-200/80 rounded-xl text-sm focus:ring-2 focus:ring-primary-200 focus:border-primary-400 focus:outline-none"
                    >
                      {(Object.keys(QUESTION_TYPE_LABELS) as QuestionType[]).map((t) => (
                        <option key={t} value={t}>{QUESTION_TYPE_LABELS[t]}</option>
                      ))}
                    </select>
                  </div>
                )}
              />

              <Controller
                control={form.control}
                name="difficulty"
                render={({ field }) => (
                  <div>
                    <label className="block text-[13px] font-medium text-slate-700 mb-1">Difficulty</label>
                    <select
                      {...field}
                      className="w-full cursor-pointer px-3 py-2 border border-slate-200/80 rounded-xl text-sm focus:ring-2 focus:ring-primary-200 focus:border-primary-400 focus:outline-none"
                    >
                      {(Object.keys(DIFFICULTY_LABELS) as Difficulty[]).map((d) => (
                        <option key={d} value={d}>{DIFFICULTY_LABELS[d]}</option>
                      ))}
                    </select>
                  </div>
                )}
              />
            </div>

            {/* Prompt */}
            <Controller
              control={form.control}
              name="prompt"
              render={({ field, fieldState }) => (
                <div>
                  <label className="block text-[13px] font-medium text-slate-700 mb-1">
                    Question Prompt <span className="text-red-500">*</span>
                  </label>
                  <textarea
                    {...field}
                    rows={3}
                    className="w-full px-3 py-2 border border-slate-200/80 rounded-xl text-sm focus:ring-2 focus:ring-primary-200 focus:border-primary-400 focus:outline-none"
                    placeholder="Enter the question text..."
                  />
                  {fieldState.error && (
                    <p className="mt-1 text-xs text-red-500">{fieldState.error.message}</p>
                  )}
                </div>
              )}
            />

            {/* Points */}
            <FormField
              control={form.control}
              name="points"
              label="Points"
              type="number"
              className="w-28"
            />

            {/* Choices (MCQ / MULTI / TRUE_FALSE) */}
            {needsChoices && (
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="text-[13px] font-medium text-slate-700">
                    Answer Choices
                    {questionType === 'MULTI' && (
                      <span className="ml-1 text-xs text-slate-500 font-normal">(select all correct)</span>
                    )}
                  </label>
                  {questionType !== 'TRUE_FALSE' && (
                    <button
                      type="button"
                      onClick={() => append({ text: '', is_correct: false, order: fields.length })}
                      className="text-xs text-primary-600 hover:text-primary-700 font-medium cursor-pointer flex items-center gap-1"
                    >
                      <PlusIcon className="h-3.5 w-3.5" />
                      Add choice
                    </button>
                  )}
                </div>

                <div className="space-y-2">
                  {fields.map((field, index) => (
                    <div key={field.id} className="flex items-center gap-2">
                      {/* Correct toggle */}
                      <Controller
                        control={form.control}
                        name={`choices.${index}.is_correct`}
                        render={({ field: f }) => (
                          <button
                            type="button"
                            onClick={() => {
                              if (questionType === 'MCQ' || questionType === 'TRUE_FALSE') {
                                // Only one can be correct for single-select
                                fields.forEach((_, i) => {
                                  form.setValue(`choices.${i}.is_correct`, i === index);
                                });
                              } else {
                                f.onChange(!f.value);
                              }
                            }}
                            className="cursor-pointer shrink-0"
                            title={f.value ? 'Mark as incorrect' : 'Mark as correct'}
                          >
                            {f.value ? (
                              <CheckCircleIcon className="h-5 w-5 text-emerald-500" />
                            ) : (
                              <XCircleIcon className="h-5 w-5 text-slate-300 hover:text-slate-400" />
                            )}
                          </button>
                        )}
                      />

                      {/* Text input */}
                      <Controller
                        control={form.control}
                        name={`choices.${index}.text`}
                        render={({ field: f }) => (
                          <input
                            {...f}
                            disabled={questionType === 'TRUE_FALSE'}
                            className="flex-1 px-3 py-2 border border-slate-200/80 rounded-lg text-sm focus:ring-2 focus:ring-primary-200 focus:border-primary-400 focus:outline-none disabled:bg-slate-50 disabled:text-slate-500"
                            placeholder={`Choice ${index + 1}`}
                          />
                        )}
                      />

                      {/* Remove (not for TRUE_FALSE) */}
                      {questionType !== 'TRUE_FALSE' && fields.length > 2 && (
                        <button
                          type="button"
                          onClick={() => remove(index)}
                          className="shrink-0 text-slate-400 hover:text-red-500 cursor-pointer transition-colors"
                          title="Remove choice"
                        >
                          <TrashIcon className="h-4 w-4" />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
                <p className="mt-2 text-xs text-slate-400">
                  {questionType === 'MULTI'
                    ? 'Click the circle to mark one or more correct answers.'
                    : 'Click the circle to mark the correct answer.'}
                </p>
                {/* Zod superRefine error at the choices array level (e.g. no correct choice selected).
                    RHF v7 stores FieldArray-level errors at errors.choices.root (not .message). */}
                {form.formState.errors.choices?.root?.message && (
                  <p className="mt-1.5 text-xs text-red-500" role="alert">
                    {form.formState.errors.choices.root.message}
                  </p>
                )}
              </div>
            )}

            {/* Explanation */}
            <Controller
              control={form.control}
              name="explanation"
              render={({ field }) => (
                <div>
                  <label className="block text-[13px] font-medium text-slate-700 mb-1">
                    Explanation <span className="text-slate-400 font-normal">(shown after submission)</span>
                  </label>
                  <textarea
                    {...field}
                    rows={2}
                    className="w-full px-3 py-2 border border-slate-200/80 rounded-xl text-sm focus:ring-2 focus:ring-primary-200 focus:border-primary-400 focus:outline-none"
                    placeholder="Optional: explain why this is the correct answer..."
                  />
                </div>
              )}
            />
          </div>

          <DialogFooter className="mt-6">
            <Button type="button" variant="outline" onClick={handleClose}>Cancel</Button>
            <Button type="submit" loading={form.formState.isSubmitting}>
              {editingQuestion ? 'Save Changes' : 'Add Question'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Question list in a bank ───────────────────────────────────────────────────

interface BankQuestionsViewProps {
  bank:    QuestionBank;
  onBack:  () => void;
}

function BankQuestionsView({ bank, onBack }: BankQuestionsViewProps) {
  const toast = useToast();
  const qc = useQueryClient();
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingQ, setEditingQ] = useState<Question | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Question | null>(null);
  const [typeFilter, setTypeFilter] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['bankQuestions', bank.id, typeFilter],
    queryFn: () =>
      adminQuestionBankService.listQuestions(bank.id, (typeFilter as QuestionType) || undefined),
  });

  const deleteMut = useMutation({
    mutationFn: (q: Question) => adminQuestionBankService.deleteQuestion(q.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bankQuestions', bank.id] });
      qc.invalidateQueries({ queryKey: ['questionBanks'] });
      toast.success('Deleted', 'Question removed from bank.');
    },
    onError: () => toast.error('Failed', 'Could not delete question.'),
  });

  const rows = data?.results ?? [];

  const columns: ColumnDef<Question>[] = [
    {
      accessorKey: 'question_type',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Type" />,
      cell: ({ getValue }) => {
        const t = getValue() as QuestionType;
        return <Badge variant="default">{QUESTION_TYPE_LABELS[t] ?? t}</Badge>;
      },
    },
    {
      accessorKey: 'prompt',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Question" />,
      cell: ({ getValue }) => (
        <p className="text-sm text-slate-700 line-clamp-2 max-w-sm">{getValue() as string}</p>
      ),
    },
    {
      accessorKey: 'difficulty',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Difficulty" />,
      cell: ({ getValue }) => {
        const d = getValue() as Difficulty;
        return <Badge variant={DIFFICULTY_VARIANTS[d] ?? 'secondary'}>{DIFFICULTY_LABELS[d] ?? d}</Badge>;
      },
    },
    {
      accessorKey: 'points',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Pts" />,
      cell: ({ getValue }) => (
        <span className="text-sm font-medium text-slate-700">{getValue() as number}</span>
      ),
    },
    {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setEditingQ(row.original)}
            className="cursor-pointer rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
            title="Edit question"
          >
            <PencilIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setDeleteTarget(row.original)}
            className="cursor-pointer rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors"
            title="Delete question"
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <button
            type="button"
            onClick={onBack}
            className="cursor-pointer flex items-center gap-1.5 text-[13px] text-slate-500 hover:text-slate-700 mb-2"
          >
            <ArrowLeftIcon className="h-4 w-4" />
            All Question Banks
          </button>
          <h2 className="text-[20px] font-bold text-slate-900">{bank.title}</h2>
          {bank.description && (
            <p className="mt-0.5 text-[13px] text-slate-500">{bank.description}</p>
          )}
        </div>
        <Button
          onClick={() => { setEditingQ(null); setShowAddModal(true); }}
          className="flex items-center gap-2 shrink-0"
        >
          <PlusIcon className="h-4 w-4" />
          Add Question
        </Button>
      </div>

      {/* Stats + filter */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="inline-flex items-center rounded-full bg-primary-50 px-3 py-1 text-xs font-medium text-primary-700">
          {bank.question_count} question{bank.question_count !== 1 ? 's' : ''}
        </span>
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-[13px] text-slate-700 focus:border-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-200 cursor-pointer"
        >
          <option value="">All Types</option>
          {(Object.keys(QUESTION_TYPE_LABELS) as QuestionType[]).map((t) => (
            <option key={t} value={t}>{QUESTION_TYPE_LABELS[t]}</option>
          ))}
        </select>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-slate-200/80 bg-white shadow-sm p-4">
        {isLoading ? (
          <div className="flex justify-center py-10"><Loading /></div>
        ) : (
          <DataTable
            columns={columns}
            data={rows}
            filterColumn="prompt"
            filterPlaceholder="Search questions…"
            pageSize={20}
            emptyMessage="No questions yet. Click 'Add Question' to create your first question."
          />
        )}
      </div>

      {/* Modals */}
      <QuestionModal
        open={showAddModal || !!editingQ}
        onClose={() => { setShowAddModal(false); setEditingQ(null); }}
        bankId={bank.id}
        editingQuestion={editingQ}
        onSaved={() => qc.invalidateQueries({ queryKey: ['bankQuestions', bank.id] })}
      />
      <ConfirmDialog
        isOpen={!!deleteTarget}
        title="Delete Question"
        message={`Are you sure you want to delete this question? This cannot be undone.`}
        confirmLabel="Delete"
        variant="danger"
        onConfirm={() => { if (deleteTarget) deleteMut.mutate(deleteTarget); setDeleteTarget(null); }}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
}

// ── Bank List (main view) ─────────────────────────────────────────────────────

export const QuestionBankPage: React.FC = () => {
  usePageTitle('Question Banks');
  const toast = useToast();
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [showBankModal, setShowBankModal] = useState(false);
  const [editingBank, setEditingBank] = useState<QuestionBank | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<QuestionBank | null>(null);
  const [selectedBank, setSelectedBank] = useState<QuestionBank | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['questionBanks', search],
    queryFn: () => adminQuestionBankService.listBanks(search || undefined),
  });

  const deleteMut = useMutation({
    mutationFn: (b: QuestionBank) => adminQuestionBankService.deleteBank(b.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['questionBanks'] });
      toast.success('Deleted', 'Question bank removed.');
    },
    onError: () => toast.error('Failed', 'Could not delete the question bank.'),
  });

  const banks = data?.results ?? [];

  const columns: ColumnDef<QuestionBank>[] = [
    {
      accessorKey: 'title',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Bank Name" />,
      cell: ({ row }) => (
        <button
          type="button"
          onClick={() => setSelectedBank(row.original)}
          className="cursor-pointer text-left group"
        >
          <p className="font-medium text-primary-700 group-hover:text-primary-800 group-hover:underline">
            {row.original.title}
          </p>
          {row.original.description && (
            <p className="text-xs text-slate-400 mt-0.5 line-clamp-1">{row.original.description}</p>
          )}
        </button>
      ),
    },
    {
      accessorKey: 'question_count',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Questions" />,
      cell: ({ getValue }) => (
        <span className="text-sm font-medium text-slate-700">{getValue() as number}</span>
      ),
    },
    {
      accessorKey: 'is_active',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
      cell: ({ getValue }) =>
        (getValue() as boolean) ? (
          <Badge variant="success">Active</Badge>
        ) : (
          <Badge variant="secondary">Inactive</Badge>
        ),
    },
    {
      accessorKey: 'created_at',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
      cell: ({ getValue }) => (
        <span className="text-sm text-slate-500">{fmtDate(getValue() as string)}</span>
      ),
    },
    {
      id: 'actions',
      header: () => <span className="sr-only">Actions</span>,
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setSelectedBank(row.original)}
            className="cursor-pointer rounded px-2.5 py-1.5 text-xs font-medium text-primary-600 border border-primary-200 hover:bg-primary-50 transition-colors"
          >
            View Questions
          </button>
          <button
            type="button"
            onClick={() => { setEditingBank(row.original); setShowBankModal(true); }}
            className="cursor-pointer rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
            title="Edit bank"
          >
            <PencilIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => setDeleteTarget(row.original)}
            className="cursor-pointer rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors"
            title="Delete bank"
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>
      ),
    },
  ];

  // ── If a bank is selected, show its questions ─────────────────────────
  if (selectedBank) {
    return (
      <BankQuestionsView
        bank={selectedBank}
        onBack={() => setSelectedBank(null)}
      />
    );
  }

  // ── Bank list view ─────────────────────────────────────────────────────
  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <BookOpenIcon className="h-6 w-6 text-primary-600" />
            Question Banks
          </h1>
          <p className="mt-1 text-[13px] text-slate-500">
            Manage reusable question banks for quizzes and assignments.
          </p>
        </div>
        <Button
          onClick={() => { setEditingBank(null); setShowBankModal(true); }}
          className="flex items-center gap-2 shrink-0"
        >
          <PlusIcon className="h-4 w-4" />
          New Question Bank
        </Button>
      </div>

      {/* Search */}
      <div className="relative max-w-sm">
        <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400 pointer-events-none" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search question banks…"
          className="w-full pl-9 pr-3 py-2 border border-slate-200 rounded-lg text-[13px] text-slate-700 focus:ring-2 focus:ring-primary-200 focus:border-primary-400 focus:outline-none"
        />
      </div>

      {/* Table */}
      <div className="rounded-xl border border-slate-200/80 bg-white shadow-sm p-4">
        {isLoading ? (
          <div className="flex justify-center py-10"><Loading /></div>
        ) : (
          <DataTable
            columns={columns}
            data={banks}
            hideFilter
            pageSize={15}
            emptyMessage={
              search
                ? 'No question banks match your search.'
                : "No question banks yet. Click 'New Question Bank' to create your first one."
            }
          />
        )}
      </div>

      {/* Modals */}
      <BankModal
        open={showBankModal}
        onClose={() => { setShowBankModal(false); setEditingBank(null); }}
        editingBank={editingBank}
        onSaved={() => qc.invalidateQueries({ queryKey: ['questionBanks'] })}
      />
      <ConfirmDialog
        isOpen={!!deleteTarget}
        title="Delete Question Bank"
        message={`Are you sure you want to delete "${deleteTarget?.title}"? This will also delete all ${deleteTarget?.question_count} questions in it.`}
        confirmLabel="Delete Bank"
        variant="danger"
        onConfirm={() => { if (deleteTarget) deleteMut.mutate(deleteTarget); setDeleteTarget(null); }}
        onClose={() => setDeleteTarget(null)}
      />
    </div>
  );
};
