// src/components/courses/QuizConfigPanel.tsx
//
// Admin panel for per-Content quiz configuration (QUIZ-type content only).
// Embedded inside the Course Editor's content settings. Loads the existing
// QuizConfig via GET; saves via PATCH. Renders a time-limit field (minutes),
// max-attempts, pass threshold %, shuffle toggles, "show answers after",
// random selection count, and a multi-select for source question banks.

import React, { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Controller } from 'react-hook-form';
import { z } from 'zod';
import { useZodForm } from '../../hooks/useZodForm';
import {
  assessmentService,
  type QuizConfig,
  type QuizConfigPayload,
} from '../../services/assessmentService';
import { adminQuestionBankService } from '../../services/adminQuestionBankService';
import { Button, Loading, useToast, FormField } from '../common';
import {
  ClockIcon,
  ArrowPathRoundedSquareIcon,
  CheckCircleIcon,
  AcademicCapIcon,
} from '@heroicons/react/24/outline';

// ── Schema ────────────────────────────────────────────────────────────────────
// Note: the backend stores `time_limit_seconds` but admins think in minutes, so
// the form collects minutes and converts on save.

const QuizConfigSchema = z.object({
  time_limit_minutes: z.coerce.number().int().min(0).max(600).default(0),
  max_attempts: z.coerce.number().int().min(0).max(100).default(1),
  pass_threshold_percent: z.coerce.number().min(0).max(100).default(70),
  shuffle_questions: z.boolean().default(false),
  shuffle_choices: z.boolean().default(false),
  show_correct_answers_after: z.boolean().default(true),
  random_selection_count: z
    .union([z.coerce.number().int().positive(), z.literal('')])
    .optional(),
  source_question_banks: z.array(z.string()).default([]),
});
type QuizConfigFormData = z.infer<typeof QuizConfigSchema>;

const toFormData = (cfg: QuizConfig): QuizConfigFormData => ({
  time_limit_minutes: Math.round((cfg.time_limit_seconds ?? 0) / 60),
  max_attempts: cfg.max_attempts ?? 1,
  pass_threshold_percent: Number(cfg.pass_threshold_percent ?? 70),
  shuffle_questions: !!cfg.shuffle_questions,
  shuffle_choices: !!cfg.shuffle_choices,
  show_correct_answers_after: !!cfg.show_correct_answers_after,
  random_selection_count: cfg.random_selection_count ?? undefined,
  source_question_banks: cfg.source_question_banks ?? [],
});

const toPayload = (d: QuizConfigFormData): QuizConfigPayload => ({
  time_limit_seconds: Math.max(0, Math.round(d.time_limit_minutes * 60)),
  max_attempts: d.max_attempts,
  pass_threshold_percent: d.pass_threshold_percent,
  shuffle_questions: d.shuffle_questions,
  shuffle_choices: d.shuffle_choices,
  show_correct_answers_after: d.show_correct_answers_after,
  random_selection_count:
    d.random_selection_count === '' || d.random_selection_count === undefined
      ? null
      : Number(d.random_selection_count),
  source_question_banks: d.source_question_banks,
});

// ── Component ────────────────────────────────────────────────────────────────

export interface QuizConfigPanelProps {
  contentId: string;
  /** Optional: called after a successful save. */
  onSaved?: (cfg: QuizConfig) => void;
}

export const QuizConfigPanel: React.FC<QuizConfigPanelProps> = ({
  contentId,
  onSaved,
}) => {
  const toast = useToast();
  const qc = useQueryClient();

  const { data: cfg, isLoading } = useQuery({
    queryKey: ['quizConfig', contentId],
    queryFn: () => assessmentService.getQuizConfig(contentId),
    enabled: !!contentId,
  });

  const { data: banksData } = useQuery({
    queryKey: ['questionBanks', 'active-only'],
    queryFn: () => adminQuestionBankService.listBanks(),
  });
  const banks = useMemo(() => banksData?.results ?? [], [banksData]);

  const form = useZodForm({
    schema: QuizConfigSchema,
    defaultValues: {
      time_limit_minutes: 0,
      max_attempts: 1,
      pass_threshold_percent: 70,
      shuffle_questions: false,
      shuffle_choices: false,
      show_correct_answers_after: true,
      random_selection_count: undefined,
      source_question_banks: [],
    },
  });

  useEffect(() => {
    if (cfg) form.reset(toFormData(cfg));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cfg?.id]);

  const saveMut = useMutation({
    mutationFn: (data: QuizConfigFormData) =>
      assessmentService.updateQuizConfig(contentId, toPayload(data)),
    onSuccess: (saved) => {
      qc.invalidateQueries({ queryKey: ['quizConfig', contentId] });
      toast.success('Quiz settings saved', 'Your changes have been applied.');
      onSaved?.(saved);
    },
    onError: () =>
      toast.error('Save failed', 'Could not update quiz settings.'),
  });

  const onSubmit = form.handleSubmit((data) => saveMut.mutate(data));

  const [bankPickerOpen, setBankPickerOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-10">
        <Loading />
      </div>
    );
  }

  const selectedBanks = form.watch('source_question_banks') ?? [];

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-6">
      <div className="rounded-xl border border-slate-200/80 bg-white p-5 shadow-sm space-y-5">
        <div className="flex items-center gap-2 text-slate-900">
          <AcademicCapIcon className="h-5 w-5 text-primary-600" />
          <h3 className="text-[15px] font-semibold">Quiz Settings</h3>
        </div>

        {/* ── Timing / attempts ────────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <FormField
            control={form.control}
            name="time_limit_minutes"
            label="Time limit (minutes)"
            type="number"
            placeholder="0 = unlimited"
          />
          <FormField
            control={form.control}
            name="max_attempts"
            label="Max attempts"
            type="number"
            placeholder="0 = unlimited"
          />
          <FormField
            control={form.control}
            name="pass_threshold_percent"
            label="Pass threshold (%)"
            type="number"
            placeholder="0 - 100"
          />
        </div>

        {/* ── Randomisation toggles ────────────────────── */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <ToggleField
            control={form.control}
            name="shuffle_questions"
            label="Shuffle questions"
            icon={<ArrowPathRoundedSquareIcon className="h-4 w-4" />}
          />
          <ToggleField
            control={form.control}
            name="shuffle_choices"
            label="Shuffle choices"
            icon={<ArrowPathRoundedSquareIcon className="h-4 w-4" />}
          />
          <ToggleField
            control={form.control}
            name="show_correct_answers_after"
            label="Show correct answers after submit"
            icon={<CheckCircleIcon className="h-4 w-4" />}
          />
        </div>

        {/* ── Random selection ─────────────────────────── */}
        <div>
          <label className="block text-[13px] font-medium text-slate-700 mb-1">
            Random selection count{' '}
            <span className="text-slate-400 font-normal">(optional)</span>
          </label>
          <Controller
            control={form.control}
            name="random_selection_count"
            render={({ field }) => (
              <input
                type="number"
                value={field.value ?? ''}
                onChange={(e) =>
                  field.onChange(e.target.value === '' ? '' : Number(e.target.value))
                }
                min={1}
                className="w-full max-w-[200px] px-3 py-2 border border-slate-200/80 rounded-xl text-sm focus:ring-2 focus:ring-primary-200 focus:border-primary-400 focus:outline-none"
                placeholder="All questions"
              />
            )}
          />
          <p className="mt-1 text-xs text-slate-400">
            If set, this many questions are randomly drawn from the linked banks
            on each attempt.
          </p>
        </div>

        {/* ── Bank picker ──────────────────────────────── */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-[13px] font-medium text-slate-700">
              Question banks ({selectedBanks.length} selected)
            </label>
            <button
              type="button"
              onClick={() => setBankPickerOpen((v) => !v)}
              className="cursor-pointer text-xs font-medium text-primary-600 hover:text-primary-700"
            >
              {bankPickerOpen ? 'Hide' : 'Manage'}
            </button>
          </div>

          {bankPickerOpen && (
            <div className="rounded-xl border border-slate-200/80 bg-slate-50 p-3 max-h-64 overflow-y-auto space-y-1.5">
              {banks.length === 0 && (
                <p className="text-xs text-slate-500 py-2">
                  No question banks yet. Create one from the Question Banks page.
                </p>
              )}
              {banks.map((bank) => {
                const checked = selectedBanks.includes(bank.id);
                return (
                  <label
                    key={bank.id}
                    className="flex items-center gap-3 px-2 py-1.5 rounded-lg hover:bg-white cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={(e) => {
                        const next = e.target.checked
                          ? [...selectedBanks, bank.id]
                          : selectedBanks.filter((id) => id !== bank.id);
                        form.setValue('source_question_banks', next, {
                          shouldDirty: true,
                        });
                      }}
                      className="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-400"
                    />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-slate-800 truncate">
                        {bank.title}
                      </p>
                      <p className="text-xs text-slate-400">
                        {bank.question_count} question
                        {bank.question_count === 1 ? '' : 's'}
                      </p>
                    </div>
                  </label>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Info row (time limit hint) ───────────────── */}
        <div className="flex items-start gap-2 rounded-lg bg-primary-50/50 border border-primary-100 p-3 text-[12px] text-primary-800">
          <ClockIcon className="h-4 w-4 mt-0.5 shrink-0" />
          <p>
            Time limits are server-enforced: answers submitted after the
            deadline + 5s grace window are marked <strong>EXPIRED</strong>. A
            value of <strong>0</strong> disables the timer.
          </p>
        </div>

        <div className="flex justify-end">
          <Button
            type="submit"
            loading={saveMut.isPending}
            disabled={!form.formState.isDirty}
          >
            Save Quiz Settings
          </Button>
        </div>
      </div>
    </form>
  );
};

// ── Small helper: toggle field ───────────────────────────────────────────────

interface ToggleFieldProps {
  control: ReturnType<typeof useZodForm<QuizConfigFormData>>['control'];
  name: 'shuffle_questions' | 'shuffle_choices' | 'show_correct_answers_after';
  label: string;
  icon?: React.ReactNode;
}

const ToggleField: React.FC<ToggleFieldProps> = ({ control, name, label, icon }) => (
  <Controller
    control={control}
    name={name}
    render={({ field }) => (
      <label className="flex items-center justify-between gap-3 px-3 py-2 rounded-xl border border-slate-200/80 bg-white cursor-pointer hover:bg-slate-50 transition-colors">
        <span className="flex items-center gap-2 text-[13px] font-medium text-slate-700">
          {icon}
          {label}
        </span>
        <div className="relative">
          <input
            type="checkbox"
            checked={!!field.value}
            onChange={(e) => field.onChange(e.target.checked)}
            className="sr-only peer"
          />
          <div className="w-10 h-5 bg-slate-200 peer-focus:ring-2 peer-focus:ring-primary-200 rounded-full peer peer-checked:after:translate-x-5 after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:border-slate-300 after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-primary-600" />
        </div>
      </label>
    )}
  />
);

export default QuizConfigPanel;
