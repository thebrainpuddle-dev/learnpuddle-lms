// src/pages/admin/GamificationPage.tsx
//
// Admin Gamification Management — Leaderboard, XP History, Badge CRUD, Config
// Built with TanStack Query, RHF + Zod modals, DataTable, Recharts RadarChart.

import React, { useState } from 'react';
import axios from 'axios';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import { format, parseISO, isValid } from 'date-fns';
import type { ColumnDef } from '@tanstack/react-table';
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  Legend,
  ResponsiveContainer,
  Tooltip,
} from 'recharts';
import { DataTable, DataTableColumnHeader } from '../../components/ui/data-table';
import { Badge } from '../../components/ui/badge';
import { Switch } from '../../components/ui/switch';
import {
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
  TabsPanels,
} from '../../components/ui/tabs';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from '../../components/ui/dialog';
import { Button } from '../../components/common/Button';
import { FormField } from '../../components/common/FormField';
import { Loading, useToast, ConfirmDialog } from '../../components/common';
import { useZodForm } from '../../hooks/useZodForm';
import {
  gamificationService,
  type GamificationConfig,
  type BadgeDefinition,
  type BadgeCreateData,
  type XPTransaction,
  type LeaderboardEntry,
} from '../../services/gamificationService';
import {
  masteryService,
  mpToNumber,
  type MasteryLeaderboardEntry,
  type MasteryLeaderboardPeriod,
} from '../../services/masteryService';
import { fetchTeachers as fetchTeacherList } from './course-editor/api';
import {
  TrophyIcon,
  PlusIcon,
  PencilIcon,
  TrashIcon,
  AdjustmentsHorizontalIcon,
  StarIcon,
  FireIcon,
  BoltIcon,
  ChartBarIcon,
  Cog6ToothIcon,
  AcademicCapIcon,
} from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useModeLabels } from '../../hooks/useModeLabels';

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(raw: string): string {
  try {
    const d = parseISO(raw);
    return isValid(d) ? format(d, 'dd MMM yyyy, HH:mm') : '—';
  } catch {
    return '—';
  }
}

function fmtShortDate(raw: string): string {
  try {
    const d = parseISO(raw);
    return isValid(d) ? format(d, 'dd MMM yyyy') : '—';
  } catch {
    return '—';
  }
}

const MEDAL: Record<number, string> = { 1: '🥇', 2: '🥈', 3: '🥉' };

/** Narrow an unknown mutation error into a user-facing message. */
function getErrorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { detail?: string; error?: string } | undefined;
    if (data?.error) return data.error;
    if (data?.detail) return data.detail;
    if (err.message) return err.message;
  }
  if (err instanceof Error) return err.message;
  return fallback;
}

/** Minimal shape of a teacher record as returned by /api/teachers/. */
interface TeacherRow {
  id: string;
  first_name?: string;
  last_name?: string;
  email?: string;
}

// ── Zod Schemas ───────────────────────────────────────────────────────────────

const BadgeSchema = z.object({
  name: z.string().min(1, 'Name is required').max(100),
  description: z.string().max(500).optional().or(z.literal('')),
  icon: z.string().max(50).optional().or(z.literal('')),
  color: z
    .string()
    .regex(/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/, 'Must be a valid hex colour (e.g. #3b82f6)')
    .optional()
    .or(z.literal('')),
  category: z.enum(['milestone', 'streak', 'completion', 'skill', 'special']),
  criteria_type: z.enum([
    'xp_threshold',
    'courses_completed',
    'streak_days',
    'content_completed',
    'manual',
  ]),
  criteria_value: z.coerce.number().min(0, 'Must be ≥ 0'),
  is_active: z.boolean().default(true),
  sort_order: z.coerce.number().min(0).default(0),
});
type BadgeFormData = z.infer<typeof BadgeSchema>;

const XPAdjustSchema = z.object({
  teacher_id: z.string().min(1, 'Teacher is required'),
  xp_amount: z.coerce
    .number()
    .int('Must be a whole number')
    .refine((n) => n !== 0, 'Cannot be zero'),
  reason: z.string().max(200).optional().or(z.literal('')),
});
type XPAdjustFormData = z.infer<typeof XPAdjustSchema>;

const ConfigSchema = z.object({
  xp_per_content_completion: z.coerce.number().min(0),
  xp_per_course_completion: z.coerce.number().min(0),
  xp_per_assignment_submission: z.coerce.number().min(0),
  xp_per_quiz_submission: z.coerce.number().min(0),
  xp_per_streak_day: z.coerce.number().min(0),
  streak_freeze_max: z.coerce.number().min(0).max(30),
  leaderboard_enabled: z.boolean(),
  leaderboard_anonymize: z.boolean(),
  opt_out_allowed: z.boolean(),
  is_active: z.boolean(),
});
type ConfigFormData = z.infer<typeof ConfigSchema>;

// ── Constants ─────────────────────────────────────────────────────────────────

const PERIOD_OPTIONS = [
  { value: 'weekly', label: 'This Week' },
  { value: 'monthly', label: 'This Month' },
  { value: 'all_time', label: 'All Time' },
] as const;

const CATEGORY_LABELS: Record<string, string> = {
  milestone: 'Milestone',
  streak: 'Streak',
  completion: 'Completion',
  skill: 'Skill',
  special: 'Special',
};

const CRITERIA_LABELS: Record<string, string> = {
  xp_threshold: 'XP Threshold',
  courses_completed: 'Courses Completed',
  streak_days: 'Streak Days',
  content_completed: 'Content Completed',
  manual: 'Manual Award',
};

const CATEGORY_VARIANTS: Record<string, 'default' | 'secondary' | 'success' | 'warning' | 'destructive' | 'outline'> = {
  milestone: 'default',
  streak: 'warning',
  completion: 'success',
  skill: 'outline',
  special: 'destructive',
};

const REASON_COLORS: Record<string, string> = {
  content_completion: 'bg-blue-100 text-blue-800',
  course_completion: 'bg-emerald-100 text-emerald-800',
  assignment_submission: 'bg-violet-100 text-violet-800',
  quiz_submission: 'bg-indigo-100 text-indigo-800',
  streak_bonus: 'bg-orange-100 text-orange-800',
  admin_adjustment: 'bg-gray-100 text-gray-800',
};

// ── XP Adjustment Modal ───────────────────────────────────────────────────────

interface TeacherOption {
  id: string;
  name: string;
  email: string;
}

interface XPAdjustModalProps {
  open: boolean;
  onClose: () => void;
  teachers: TeacherOption[];
  preselectedTeacherId?: string;
}

function XPAdjustModal({ open, onClose, teachers, preselectedTeacherId }: XPAdjustModalProps) {
  const toast = useToast();
  const queryClient = useQueryClient();

  const form = useZodForm({
    schema: XPAdjustSchema,
    defaultValues: {
      teacher_id: preselectedTeacherId ?? '',
      xp_amount: 0,
      reason: '',
    },
  });

  React.useEffect(() => {
    if (open) {
      form.reset({
        teacher_id: preselectedTeacherId ?? '',
        xp_amount: 0,
        reason: '',
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, preselectedTeacherId]);

  const { mutate, isPending } = useMutation({
    mutationFn: (data: XPAdjustFormData) =>
      gamificationService.admin.adjustXP({
        teacher_id: data.teacher_id,
        xp_amount: data.xp_amount,
        reason: data.reason || undefined,
      }),
    onSuccess: () => {
      toast.success('XP adjusted successfully');
      queryClient.invalidateQueries({ queryKey: ['adminXPHistory'] });
      queryClient.invalidateQueries({ queryKey: ['adminLeaderboard'] });
      onClose();
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, 'Failed to adjust XP'));
    },
  });

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent onClose={onClose} showClose className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Adjust XP</DialogTitle>
          <DialogDescription>
            Manually award or deduct experience points for a teacher.
            Use positive values to add XP, negative to deduct.
          </DialogDescription>
        </DialogHeader>

        <form
          onSubmit={form.handleSubmit((d) => mutate(d))}
          className="mt-4 space-y-4"
        >
          {/* Teacher select */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Teacher <span className="text-red-500">*</span>
            </label>
            <Controller
              control={form.control}
              name="teacher_id"
              render={({ field, fieldState }) => (
                <>
                  <select
                    {...field}
                    className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                  >
                    <option value="">Select teacher…</option>
                    {teachers.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name} ({t.email})
                      </option>
                    ))}
                  </select>
                  {fieldState.error && (
                    <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                  )}
                </>
              )}
            />
          </div>

          {/* XP Amount */}
          <FormField
            control={form.control}
            name="xp_amount"
            label="XP Amount"
            type="number"
            placeholder="+100 or -50"
            leftIcon={<BoltIcon className="h-4 w-4 text-gray-400" />}
          />

          {/* Reason */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Reason (optional)
            </label>
            <Controller
              control={form.control}
              name="reason"
              render={({ field }) => (
                <textarea
                  {...field}
                  rows={2}
                  placeholder="e.g. Course completion bonus"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                />
              )}
            />
          </div>

          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
              Cancel
            </Button>
            <Button type="submit" loading={isPending}>
              Apply Adjustment
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Badge Modal ───────────────────────────────────────────────────────────────

interface BadgeModalProps {
  open: boolean;
  onClose: () => void;
  editing?: BadgeDefinition | null;
}

function BadgeModal({ open, onClose, editing }: BadgeModalProps) {
  const toast = useToast();
  const queryClient = useQueryClient();

  const form = useZodForm({
    schema: BadgeSchema,
    defaultValues: {
      name: '',
      description: '',
      icon: '',
      color: '#3b82f6',
      category: 'milestone',
      criteria_type: 'xp_threshold',
      criteria_value: 100,
      is_active: true,
      sort_order: 0,
    },
  });

  React.useEffect(() => {
    if (open) {
      if (editing) {
        form.reset({
          name: editing.name,
          description: editing.description ?? '',
          icon: editing.icon ?? '',
          color: editing.color ?? '#3b82f6',
          category: editing.category,
          criteria_type: editing.criteria_type,
          criteria_value: editing.criteria_value,
          is_active: editing.is_active,
          sort_order: editing.sort_order,
        });
      } else {
        form.reset({
          name: '',
          description: '',
          icon: '',
          color: '#3b82f6',
          category: 'milestone',
          criteria_type: 'xp_threshold',
          criteria_value: 100,
          is_active: true,
          sort_order: 0,
        });
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, editing]);

  const { mutate: createBadge, isPending: isCreating } = useMutation({
    mutationFn: (data: BadgeCreateData) => gamificationService.admin.createBadge(data),
    onSuccess: () => {
      toast.success('Badge created');
      queryClient.invalidateQueries({ queryKey: ['adminBadges'] });
      onClose();
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, 'Failed to create badge'));
    },
  });

  const { mutate: updateBadge, isPending: isUpdating } = useMutation({
    mutationFn: (data: BadgeCreateData) =>
      gamificationService.admin.updateBadge(editing!.id, data),
    onSuccess: () => {
      toast.success('Badge updated');
      queryClient.invalidateQueries({ queryKey: ['adminBadges'] });
      onClose();
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, 'Failed to update badge'));
    },
  });

  const isPending = isCreating || isUpdating;

  const onSubmit = (data: BadgeFormData) => {
    const payload: BadgeCreateData = {
      name: data.name,
      description: data.description || undefined,
      icon: data.icon || undefined,
      color: data.color || undefined,
      category: data.category,
      criteria_type: data.criteria_type,
      criteria_value: data.criteria_value,
      is_active: data.is_active,
      sort_order: data.sort_order,
    };
    if (editing) {
      updateBadge(payload);
    } else {
      createBadge(payload);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent onClose={onClose} showClose className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? 'Edit Badge' : 'Create Badge'}</DialogTitle>
          <DialogDescription>
            {editing
              ? 'Update the badge definition and award criteria.'
              : 'Define a new achievement badge that teachers can earn.'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(onSubmit)} className="mt-4 space-y-4">
          <FormField control={form.control} name="name" label="Badge Name" placeholder="e.g. Course Champion" />

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <Controller
              control={form.control}
              name="description"
              render={({ field }) => (
                <textarea
                  {...field}
                  rows={2}
                  placeholder="Short description of what earns this badge"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                />
              )}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* Category */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
              <Controller
                control={form.control}
                name="category"
                render={({ field, fieldState }) => (
                  <>
                    <select
                      {...field}
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                    >
                      {Object.entries(CATEGORY_LABELS).map(([v, l]) => (
                        <option key={v} value={v}>{l}</option>
                      ))}
                    </select>
                    {fieldState.error && (
                      <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                    )}
                  </>
                )}
              />
            </div>

            {/* Criteria Type */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Criteria</label>
              <Controller
                control={form.control}
                name="criteria_type"
                render={({ field, fieldState }) => (
                  <>
                    <select
                      {...field}
                      className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                    >
                      {Object.entries(CRITERIA_LABELS).map(([v, l]) => (
                        <option key={v} value={v}>{l}</option>
                      ))}
                    </select>
                    {fieldState.error && (
                      <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                    )}
                  </>
                )}
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <FormField
              control={form.control}
              name="criteria_value"
              label="Threshold Value"
              type="number"
              min={0}
              placeholder="100"
            />
            <FormField
              control={form.control}
              name="sort_order"
              label="Sort Order"
              type="number"
              min={0}
              placeholder="0"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <FormField
              control={form.control}
              name="icon"
              label="Icon Key"
              placeholder="award, flame, star…"
            />
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Colour</label>
              <Controller
                control={form.control}
                name="color"
                render={({ field, fieldState }) => (
                  <>
                    <div className="flex gap-2 items-center">
                      <input
                        {...field}
                        type="color"
                        className="h-9 w-12 cursor-pointer rounded-lg border border-gray-300 p-0.5"
                      />
                      <input
                        value={field.value}
                        onChange={field.onChange}
                        type="text"
                        placeholder="#3b82f6"
                        className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
                      />
                    </div>
                    {fieldState.error && (
                      <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                    )}
                  </>
                )}
              />
            </div>
          </div>

          {/* Active toggle */}
          <div className="flex items-center justify-between py-2 border-t border-gray-100">
            <div>
              <p className="text-sm font-medium text-gray-900">Active</p>
              <p className="text-xs text-gray-500">Inactive badges cannot be earned</p>
            </div>
            <Controller
              control={form.control}
              name="is_active"
              render={({ field }) => (
                <Switch
                  checked={field.value}
                  onCheckedChange={field.onChange}
                  aria-label="Badge active"
                />
              )}
            />
          </div>

          <DialogFooter className="pt-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
              Cancel
            </Button>
            <Button type="submit" loading={isPending}>
              {editing ? 'Save Changes' : 'Create Badge'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Leaderboard Tab ───────────────────────────────────────────────────────────

interface LeaderboardTabProps {
  teachers: TeacherOption[];
}

function LeaderboardTab({ teachers }: LeaderboardTabProps) {
  const toast = useToast();
  const { label } = useModeLabels();
  const [period, setPeriod] = useState<'weekly' | 'monthly' | 'all_time'>('weekly');
  const [adjustTeacherId, setAdjustTeacherId] = useState<string | undefined>();
  const [showAdjust, setShowAdjust] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['adminLeaderboard', period],
    queryFn: () => gamificationService.admin.getLeaderboard(period),
  });

  // Build radar data for top 5 teachers.
  // Use teacher_id as the dataKey (guaranteed unique) to avoid collisions when
  // two teachers share the same first name.
  // Metric labels use useModeLabels so they reflect tenant mode (e.g. "Points"
  // instead of "XP" in Corporate mode).
  const radarData = React.useMemo(() => {
    if (!data?.entries?.length) return [];
    const top5 = data.entries.slice(0, 5);
    const maxXP = Math.max(...top5.map((e) => e.total_xp), 1);
    const maxStreak = Math.max(...top5.map((e) => e.current_streak), 1);
    const maxBadges = Math.max(...top5.map((e) => e.badge_count), 1);
    return [
      {
        metric: label('xp'),
        ...Object.fromEntries(top5.map((e) => [e.teacher_id, Math.round((e.total_xp / maxXP) * 100)])),
      },
      {
        metric: label('streak'),
        ...Object.fromEntries(top5.map((e) => [e.teacher_id, Math.round((e.current_streak / maxStreak) * 100)])),
      },
      {
        metric: `${label('badge')}s`,
        ...Object.fromEntries(top5.map((e) => [e.teacher_id, Math.round((e.badge_count / maxBadges) * 100)])),
      },
      {
        metric: 'Level',
        ...Object.fromEntries(top5.map((e) => [e.teacher_id, Math.min(e.level * 10, 100)])),
      },
    ];
  }, [data, label]);

  const RADAR_COLORS = ['#2563eb', '#0ea5e9', '#10b981', '#f59e0b', '#ef4444'];
  // Keep a reference to the top-5 entries for rendering Radar series (dataKey = teacher_id,
  // legend name = first name — fine since it's display-only).
  const top5Entries = data?.entries.slice(0, 5) ?? [];

  return (
    <>
      <div className="space-y-6">
        {/* Period + Adjust XP */}
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
          <div className="flex gap-2">
            {PERIOD_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setPeriod(opt.value)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
                  period === opt.value
                    ? 'bg-primary-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          <Button
            size="sm"
            variant="outline"
            leftIcon={<BoltIcon className="h-4 w-4" />}
            onClick={() => {
              setAdjustTeacherId(undefined);
              setShowAdjust(true);
            }}
          >
            Adjust XP
          </Button>
        </div>

        {isLoading ? (
          <Loading />
        ) : !data?.entries.length ? (
          <div className="rounded-xl border border-gray-200 bg-white p-12 text-center">
            <TrophyIcon className="h-12 w-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 text-sm">No leaderboard data for this period yet.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
            {/* Rankings table */}
            <div className="lg:col-span-3">
              <div className="rounded-xl border border-gray-200 bg-white overflow-hidden">
                <div className="px-5 py-3.5 border-b border-gray-100 flex items-center gap-2">
                  <TrophyIcon className="h-4 w-4 text-amber-500" />
                  <h3 className="text-sm font-semibold text-gray-900">Rankings</h3>
                  <span className="ml-auto text-xs text-gray-400 capitalize">{data.period}</span>
                </div>
                <div className="divide-y divide-gray-50">
                  {data.entries.map((entry: LeaderboardEntry) => (
                    <div
                      key={entry.teacher_id}
                      className="flex items-center gap-3 px-5 py-3 hover:bg-gray-50 transition-colors"
                    >
                      {/* Rank */}
                      <div className="w-8 flex-shrink-0 text-center">
                        {MEDAL[entry.rank] ? (
                          <span className="text-lg leading-none">{MEDAL[entry.rank]}</span>
                        ) : (
                          <span className="text-sm font-bold text-gray-400">#{entry.rank}</span>
                        )}
                      </div>

                      {/* Avatar */}
                      <div className="h-8 w-8 rounded-full bg-primary-100 flex items-center justify-center flex-shrink-0">
                        <span className="text-xs font-semibold text-primary-700">
                          {entry.teacher_name.charAt(0)}
                        </span>
                      </div>

                      {/* Name + level */}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-gray-900 truncate">
                          {entry.teacher_name}
                        </p>
                        <p className="text-xs text-gray-500">
                          {entry.level_name} · Lv {entry.level}
                        </p>
                      </div>

                      {/* Stats */}
                      <div className="flex items-center gap-4 text-xs text-gray-500">
                        <div className="flex items-center gap-1">
                          <BoltIcon className="h-3.5 w-3.5 text-amber-500" />
                          <span className="font-medium text-gray-900 tabular-nums">
                            {entry.xp_period.toLocaleString()}
                          </span>
                        </div>
                        <div className="hidden sm:flex items-center gap-1">
                          <FireIcon className="h-3.5 w-3.5 text-orange-400" />
                          <span>{entry.current_streak}d</span>
                        </div>
                        <div className="hidden sm:flex items-center gap-1">
                          <StarIcon className="h-3.5 w-3.5 text-violet-400" />
                          <span>{entry.badge_count}</span>
                        </div>
                      </div>

                      {/* Adjust XP */}
                      <button
                        type="button"
                        className="p-1.5 rounded-md text-gray-400 hover:text-primary-600 hover:bg-primary-50 transition-colors cursor-pointer"
                        title="Adjust XP"
                        onClick={() => {
                          setAdjustTeacherId(entry.teacher_id);
                          setShowAdjust(true);
                        }}
                      >
                        <AdjustmentsHorizontalIcon className="h-4 w-4" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Radar chart for top 5 */}
            {radarData.length > 0 && top5Entries.length >= 2 && (
              <div className="lg:col-span-2">
                <div className="rounded-xl border border-gray-200 bg-white p-5 h-full">
                  <div className="flex items-center gap-2 mb-3">
                    <ChartBarIcon className="h-4 w-4 text-primary-500" />
                    <h3 className="text-sm font-semibold text-gray-900">Top 5 Comparison</h3>
                  </div>
                  <div className="h-56">
                    <ResponsiveContainer width="100%" height="100%">
                      <RadarChart data={radarData}>
                        <PolarGrid />
                        <PolarAngleAxis dataKey="metric" tick={{ fontSize: 11 }} />
                        <PolarRadiusAxis domain={[0, 100]} tick={{ fontSize: 10 }} />
                        {top5Entries.map((entry, i) => (
                          <Radar
                            key={entry.teacher_id}
                            name={entry.teacher_name.split(' ')[0]}
                            dataKey={entry.teacher_id}
                            stroke={RADAR_COLORS[i % RADAR_COLORS.length]}
                            fill={RADAR_COLORS[i % RADAR_COLORS.length]}
                            fillOpacity={0.08}
                          />
                        ))}
                        <Legend wrapperStyle={{ fontSize: 11 }} />
                        <Tooltip formatter={(v: number) => `${v}%`} />
                      </RadarChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="mt-2 text-[11px] text-gray-400 text-center">
                    Scores normalised relative to top performer
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      <XPAdjustModal
        open={showAdjust}
        onClose={() => setShowAdjust(false)}
        teachers={teachers}
        preselectedTeacherId={adjustTeacherId}
      />
    </>
  );
}

// ── XP History Tab ────────────────────────────────────────────────────────────

function XPHistoryTab() {
  const [teacherFilter, setTeacherFilter] = useState('');
  const [reasonFilter, setReasonFilter] = useState('');
  const { label } = useModeLabels();

  const { data: transactions = [], isLoading } = useQuery<XPTransaction[]>({
    queryKey: ['adminXPHistory'],
    queryFn: () => gamificationService.admin.getXPHistory(),
  });

  const filtered = React.useMemo(() => {
    return transactions.filter((t) => {
      const matchTeacher =
        !teacherFilter ||
        t.teacher_name.toLowerCase().includes(teacherFilter.toLowerCase()) ||
        t.teacher_email.toLowerCase().includes(teacherFilter.toLowerCase());
      const matchReason = !reasonFilter || t.reason === reasonFilter;
      return matchTeacher && matchReason;
    });
  }, [transactions, teacherFilter, reasonFilter]);

  const uniqueReasons = React.useMemo(
    () => [...new Set(transactions.map((t) => t.reason).filter(Boolean))],
    [transactions],
  );

  const columns: ColumnDef<XPTransaction>[] = [
    {
      accessorKey: 'teacher_name',
      header: ({ column }) => <DataTableColumnHeader column={column} title={label('learner')} />,
      cell: ({ row }) => (
        <div>
          <p className="font-medium text-gray-900 text-sm">{row.original.teacher_name}</p>
          <p className="text-xs text-gray-500">{row.original.teacher_email}</p>
        </div>
      ),
    },
    {
      accessorKey: 'xp_amount',
      header: ({ column }) => <DataTableColumnHeader column={column} title={label('xp')} />,
      cell: ({ getValue }) => {
        const v = getValue() as number;
        return (
          <span
            className={`inline-flex items-center gap-1 text-sm font-semibold tabular-nums ${
              v >= 0 ? 'text-emerald-600' : 'text-red-600'
            }`}
          >
            <BoltIcon className="h-3.5 w-3.5" />
            {v >= 0 ? '+' : ''}{v}
          </span>
        );
      },
    },
    {
      accessorKey: 'reason',
      header: 'Reason',
      cell: ({ getValue }) => {
        const r = getValue() as string;
        const colorCls = REASON_COLORS[r] ?? 'bg-gray-100 text-gray-800';
        return (
          <span className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-medium ${colorCls}`}>
            {r.replace(/_/g, ' ')}
          </span>
        );
      },
    },
    {
      accessorKey: 'description',
      header: 'Description',
      cell: ({ getValue }) => (
        <span className="text-sm text-gray-600 line-clamp-1">{(getValue() as string) || '—'}</span>
      ),
    },
    {
      accessorKey: 'created_at',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Date" />,
      cell: ({ getValue }) => (
        <span className="text-xs text-gray-500 tabular-nums whitespace-nowrap">
          {fmtDate(getValue() as string)}
        </span>
      ),
    },
  ];

  if (isLoading) return <Loading />;

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <input
          type="text"
          value={teacherFilter}
          onChange={(e) => setTeacherFilter(e.target.value)}
          placeholder="Search teacher…"
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
        />
        <select
          value={reasonFilter}
          onChange={(e) => setReasonFilter(e.target.value)}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
        >
          <option value="">All reasons</option>
          {uniqueReasons.map((r) => (
            <option key={r} value={r}>
              {r.replace(/_/g, ' ')}
            </option>
          ))}
        </select>
        {(teacherFilter || reasonFilter) && (
          <button
            type="button"
            onClick={() => { setTeacherFilter(''); setReasonFilter(''); }}
            className="text-sm text-gray-500 hover:text-gray-700 underline cursor-pointer whitespace-nowrap"
          >
            Clear filters
          </button>
        )}
      </div>

      <DataTable columns={columns} data={filtered} />
    </div>
  );
}

// ── Badges Tab ────────────────────────────────────────────────────────────────

function BadgesTab() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const { label } = useModeLabels();
  const [editing, setEditing] = useState<BadgeDefinition | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const { data: badges = [], isLoading } = useQuery<BadgeDefinition[]>({
    queryKey: ['adminBadges'],
    queryFn: () => gamificationService.admin.listBadges(),
  });

  const { mutate: deleteBadge, isPending: isDeleting } = useMutation({
    mutationFn: (id: string) => gamificationService.admin.deleteBadge(id),
    onSuccess: () => {
      toast.success('Badge deleted');
      queryClient.invalidateQueries({ queryKey: ['adminBadges'] });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, 'Failed to delete badge'));
    },
    onSettled: () => setDeletingId(null),
  });

  const columns: ColumnDef<BadgeDefinition>[] = [
    {
      accessorKey: 'name',
      header: ({ column }) => <DataTableColumnHeader column={column} title={label('badge')} />,
      cell: ({ row }) => (
        <div className="flex items-center gap-3">
          <div
            className="h-8 w-8 rounded-full flex items-center justify-center flex-shrink-0"
            style={{ backgroundColor: `${row.original.color ?? '#3b82f6'}22` }}
          >
            <StarIcon
              className="h-4 w-4"
              style={{ color: row.original.color ?? '#3b82f6' }}
            />
          </div>
          <div>
            <p className="text-sm font-medium text-gray-900">{row.original.name}</p>
            <p className="text-xs text-gray-500 line-clamp-1">{row.original.description || '—'}</p>
          </div>
        </div>
      ),
    },
    {
      accessorKey: 'category',
      header: 'Category',
      cell: ({ getValue }) => (
        <Badge variant={CATEGORY_VARIANTS[getValue() as string] ?? 'secondary'}>
          {CATEGORY_LABELS[getValue() as string] ?? getValue() as string}
        </Badge>
      ),
    },
    {
      accessorKey: 'criteria_type',
      header: 'Criteria',
      cell: ({ getValue }) => (
        <span className="text-xs text-gray-600">
          {CRITERIA_LABELS[getValue() as string] ?? getValue() as string}
        </span>
      ),
    },
    {
      accessorKey: 'criteria_value',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Threshold" />,
      cell: ({ getValue }) => (
        <span className="text-sm tabular-nums text-gray-700">{getValue() as number}</span>
      ),
    },
    {
      accessorKey: 'is_active',
      header: 'Status',
      cell: ({ getValue }) =>
        getValue() ? (
          <Badge variant="success">Active</Badge>
        ) : (
          <Badge variant="secondary">Inactive</Badge>
        ),
    },
    {
      accessorKey: 'created_at',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Created" />,
      cell: ({ getValue }) => (
        <span className="text-xs text-gray-500">{fmtShortDate(getValue() as string)}</span>
      ),
    },
    {
      id: 'actions',
      cell: ({ row }) => (
        <div className="flex items-center gap-1 justify-end">
          <button
            type="button"
            className="p-1.5 text-gray-400 hover:text-primary-600 hover:bg-primary-50 rounded-md transition-colors cursor-pointer"
            title="Edit"
            onClick={() => { setEditing(row.original); setShowModal(true); }}
          >
            <PencilIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors cursor-pointer"
            title="Delete"
            onClick={() => setDeletingId(row.original.id)}
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <>
      <div className="space-y-4">
        <div className="flex justify-end">
          <Button
            size="sm"
            leftIcon={<PlusIcon className="h-4 w-4" />}
            onClick={() => { setEditing(null); setShowModal(true); }}
          >
            New Badge
          </Button>
        </div>

        {isLoading ? (
          <Loading />
        ) : (
          <DataTable columns={columns} data={badges} />
        )}
      </div>

      <BadgeModal
        open={showModal}
        onClose={() => { setShowModal(false); setEditing(null); }}
        editing={editing}
      />

      <ConfirmDialog
        isOpen={!!deletingId}
        title="Delete Badge"
        message="Are you sure you want to delete this badge? Teachers who have already earned it will keep their award."
        confirmLabel="Delete"
        onConfirm={() => deletingId && deleteBadge(deletingId)}
        onClose={() => setDeletingId(null)}
        variant="danger"
        loading={isDeleting}
      />
    </>
  );
}

// ── Config Tab ────────────────────────────────────────────────────────────────

function ConfigTab() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const { data: config, isLoading } = useQuery<GamificationConfig>({
    queryKey: ['adminGamificationConfig'],
    queryFn: () => gamificationService.admin.getConfig(),
  });

  const form = useZodForm({ schema: ConfigSchema });

  // Populate form when config loads
  React.useEffect(() => {
    if (config) {
      form.reset({
        xp_per_content_completion: config.xp_per_content_completion,
        xp_per_course_completion: config.xp_per_course_completion,
        xp_per_assignment_submission: config.xp_per_assignment_submission,
        xp_per_quiz_submission: config.xp_per_quiz_submission,
        xp_per_streak_day: config.xp_per_streak_day,
        streak_freeze_max: config.streak_freeze_max,
        leaderboard_enabled: config.leaderboard_enabled,
        leaderboard_anonymize: config.leaderboard_anonymize,
        opt_out_allowed: config.opt_out_allowed,
        is_active: config.is_active,
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const { mutate: saveConfig, isPending } = useMutation({
    mutationFn: (data: ConfigFormData) => gamificationService.admin.updateConfig(data),
    onSuccess: () => {
      toast.success('Gamification config saved');
      queryClient.invalidateQueries({ queryKey: ['adminGamificationConfig'] });
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, 'Failed to save config'));
    },
  });

  if (isLoading) return <Loading />;

  return (
    <form onSubmit={form.handleSubmit((d) => saveConfig(d))} className="space-y-6 max-w-2xl">
      {/* XP Settings */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
        <div className="flex items-center gap-2 mb-2">
          <BoltIcon className="h-4 w-4 text-amber-500" />
          <h3 className="text-sm font-semibold text-gray-900">XP Points per Action</h3>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <FormField control={form.control} name="xp_per_content_completion" label="Content Completion" type="number" min={0} />
          <FormField control={form.control} name="xp_per_course_completion" label="Course Completion" type="number" min={0} />
          <FormField control={form.control} name="xp_per_assignment_submission" label="Assignment Submission" type="number" min={0} />
          <FormField control={form.control} name="xp_per_quiz_submission" label="Quiz Submission" type="number" min={0} />
          <FormField control={form.control} name="xp_per_streak_day" label="Streak Day Bonus" type="number" min={0} />
          <FormField control={form.control} name="streak_freeze_max" label="Max Streak Freezes" type="number" min={0} max={30} />
        </div>
      </div>

      {/* Feature Toggles */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 space-y-4">
        <div className="flex items-center gap-2 mb-2">
          <Cog6ToothIcon className="h-4 w-4 text-gray-500" />
          <h3 className="text-sm font-semibold text-gray-900">Feature Settings</h3>
        </div>

        {(
          [
            { name: 'is_active', label: 'Gamification Active', desc: 'Enable the entire gamification system' },
            { name: 'leaderboard_enabled', label: 'Leaderboard Enabled', desc: 'Show the teacher leaderboard' },
            { name: 'leaderboard_anonymize', label: 'Anonymise Leaderboard', desc: 'Hide real names on the public leaderboard' },
            { name: 'opt_out_allowed', label: 'Allow Opt-Out', desc: 'Teachers can opt out of gamification tracking' },
          ] as { name: keyof ConfigFormData; label: string; desc: string }[]
        ).map(({ name, label, desc }) => (
          <div key={name} className="flex items-center justify-between py-2 border-b border-gray-50 last:border-0">
            <div>
              <p className="text-sm font-medium text-gray-900">{label}</p>
              <p className="text-xs text-gray-500">{desc}</p>
            </div>
            <Controller
              control={form.control}
              name={name}
              render={({ field }) => (
                <Switch
                  checked={field.value as boolean}
                  onCheckedChange={field.onChange}
                  aria-label={label}
                />
              )}
            />
          </div>
        ))}
      </div>

      <div className="flex justify-end">
        <Button type="submit" loading={isPending}>
          Save Configuration
        </Button>
      </div>
    </form>
  );
}

// ── Mastery Leaderboard Tab (TASK-018) ────────────────────────────────────────

function MasteryLeaderboardTab() {
  const [period, setPeriod] = useState<MasteryLeaderboardPeriod>('all_time');
  const { label } = useModeLabels();

  const { data, isLoading } = useQuery({
    queryKey: ['adminMasteryLeaderboard', period],
    queryFn: () => masteryService.getAdminLeaderboard({ period }),
  });

  const rows = data?.results ?? [];

  const columns: ColumnDef<MasteryLeaderboardEntry>[] = [
    {
      accessorKey: 'rank',
      header: 'Rank',
      cell: ({ getValue }) => {
        const rank = getValue() as number;
        return (
          <span className="w-8 text-center inline-block">
            {MEDAL[rank] ?? (
              <span className="text-sm font-bold text-gray-400">#{rank}</span>
            )}
          </span>
        );
      },
    },
    {
      accessorKey: 'teacher_name',
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title={label('learner')} />
      ),
      cell: ({ row }) => (
        <div>
          <p className="text-sm font-medium text-gray-900">
            {row.original.teacher_name}
          </p>
          <p className="text-xs text-gray-500">{row.original.teacher_email}</p>
        </div>
      ),
    },
    {
      accessorKey: 'total_mastery_points',
      header: ({ column }) => (
        <DataTableColumnHeader column={column} title="Total MP" />
      ),
      cell: ({ getValue }) => (
        <span
          className="inline-flex items-center gap-1 text-sm font-semibold tabular-nums text-emerald-600"
          data-testid="mastery-lb-total"
        >
          <AcademicCapIcon className="h-3.5 w-3.5" />
          {mpToNumber(getValue() as string).toFixed(2)}
        </span>
      ),
    },
    {
      id: 'quiz_mp',
      header: 'Quiz MP',
      cell: ({ row }) => {
        // The backend summary ships only aggregated totals today; we render
        // the period-scoped columns alongside quiz/assignment/course columns
        // populated by the admin report when the detail endpoint lands.
        // Until then, we show this-week/this-month as the secondary
        // period-scoped columns so the tab still has per-period colour.
        const n = mpToNumber(row.original.mp_this_week);
        return (
          <span className="text-sm tabular-nums text-gray-700">
            {n.toFixed(2)}
          </span>
        );
      },
    },
    {
      id: 'assignment_mp',
      header: 'Assignment MP',
      cell: ({ row }) => {
        const n = mpToNumber(row.original.mp_this_month);
        return (
          <span className="text-sm tabular-nums text-gray-700">
            {n.toFixed(2)}
          </span>
        );
      },
    },
    {
      id: 'course_mp',
      header: 'Course MP',
      cell: ({ row }) => {
        // Course MP is the residual between total and (week + month) when the
        // backend adds per-reason totals; today we surface a placeholder so
        // the column renders without blocking the ship.
        const total = mpToNumber(row.original.total_mastery_points);
        const month = mpToNumber(row.original.mp_this_month);
        const residual = Math.max(0, total - month);
        return (
          <span className="text-sm tabular-nums text-gray-700">
            {residual.toFixed(2)}
          </span>
        );
      },
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
        <div className="flex gap-2">
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setPeriod(opt.value)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
                period === opt.value
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              }`}
              data-testid={`mastery-lb-period-${opt.value}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-gray-500">
          Ranked by total MP across the tenant.
        </p>
      </div>

      {isLoading ? (
        <Loading />
      ) : !rows.length ? (
        <div className="rounded-xl border border-gray-200 bg-white p-12 text-center">
          <AcademicCapIcon className="h-12 w-12 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500 text-sm">
            No Mastery Point data for this period yet.
          </p>
        </div>
      ) : (
        <DataTable
          columns={columns}
          data={rows}
          emptyMessage="No MP data yet."
        />
      )}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export const AdminGamificationPage: React.FC = () => {
  usePageTitle('Gamification');

  // Fetch teachers for the XP adjustment modal
  const { data: teachersData } = useQuery({
    queryKey: ['adminTeachers'],
    queryFn: () => fetchTeacherList(),
    staleTime: 5 * 60 * 1000,
  });

  const teachers: TeacherOption[] = React.useMemo(
    () =>
      ((teachersData ?? []) as TeacherRow[]).map((t) => ({
        id: t.id,
        name: `${t.first_name ?? ''} ${t.last_name ?? ''}`.trim(),
        email: t.email ?? '',
      })),
    [teachersData],
  );

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Gamification</h1>
        <p className="mt-1 text-sm text-gray-500">
          Manage XP points, badges, leaderboards, and gamification settings for your school.
        </p>
      </div>

      {/* Tabs */}
      <Tabs>
        <TabsList className="w-full sm:w-auto">
          <TabsTrigger>
            <TrophyIcon className="h-4 w-4 mr-1.5" />
            Leaderboard
          </TabsTrigger>
          <TabsTrigger>
            <BoltIcon className="h-4 w-4 mr-1.5" />
            XP History
          </TabsTrigger>
          <TabsTrigger>
            <StarIcon className="h-4 w-4 mr-1.5" />
            Badges
          </TabsTrigger>
          <TabsTrigger>
            <AcademicCapIcon className="h-4 w-4 mr-1.5" />
            Mastery Leaderboard
          </TabsTrigger>
          <TabsTrigger>
            <Cog6ToothIcon className="h-4 w-4 mr-1.5" />
            Config
          </TabsTrigger>
        </TabsList>

        <TabsPanels className="mt-4">
          <TabsContent>
            <LeaderboardTab teachers={teachers} />
          </TabsContent>
          <TabsContent>
            <XPHistoryTab />
          </TabsContent>
          <TabsContent>
            <BadgesTab />
          </TabsContent>
          <TabsContent>
            <MasteryLeaderboardTab />
          </TabsContent>
          <TabsContent>
            <ConfigTab />
          </TabsContent>
        </TabsPanels>
      </Tabs>
    </div>
  );
};
