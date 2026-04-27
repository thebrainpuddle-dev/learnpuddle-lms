// src/pages/admin/RubricPage.tsx
//
// Admin rubric library — create, edit, clone, and delete scoring rubrics.
// Each rubric has criteria; each criterion optionally has performance levels.
//
// Backend: TASK-044 rubric endpoints
//   GET/POST /admin/rubrics/
//   GET/PATCH/DELETE /admin/rubrics/:id/
//   POST /admin/rubrics/:id/clone/

import React, { useCallback, useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Controller, useFieldArray, useForm, useWatch } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import type { ColumnDef } from '@tanstack/react-table';
import {
  PlusIcon,
  PencilSquareIcon,
  TrashIcon,
  DocumentDuplicateIcon,
  CheckCircleIcon,
  XCircleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ClipboardDocumentListIcon,
} from '@heroicons/react/24/outline';
import { DataTable, DataTableColumnHeader } from '../../components/ui/data-table';
import { Badge } from '../../components/ui/badge';
import { Switch } from '../../components/ui/switch';
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from '../../components/ui/dialog';
import { Button, Loading, useToast } from '../../components/common';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  adminRubricService,
  type Rubric,
  type RubricCriterionPayload,
  type RubricLevelPayload,
  type RubricWritePayload,
} from '../../services/adminRubricService';

// ── Zod Schemas ──────────────────────────────────────────────────────────────

const RubricLevelSchema = z.object({
  title: z.string().min(1, 'Level title is required').max(100),
  description: z.string().max(500).default(''),
  points: z.coerce.number().min(0, 'Points must be ≥ 0').max(10000),
  order: z.number().optional(),
});

const RubricCriterionSchema = z.object({
  title: z.string().min(1, 'Criterion title is required').max(200),
  description: z.string().max(500).default(''),
  max_points: z.coerce
    .number()
    .min(0, 'Max points must be ≥ 0')
    .max(10000),
  order: z.number().optional(),
  levels: z.array(RubricLevelSchema).default([]),
});

const RubricSchema = z.object({
  title: z.string().min(1, 'Title is required').max(200),
  description: z.string().max(1000).default(''),
  is_active: z.boolean().default(true),
  criteria: z.array(RubricCriterionSchema).default([]),
});

type RubricFormData = z.infer<typeof RubricSchema>;

// ── ConfirmDialog ─────────────────────────────────────────────────────────────

interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  loading?: boolean;
  variant?: 'danger' | 'default';
}

function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  loading = false,
  variant = 'default',
}: ConfirmDialogProps) {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="fixed inset-0 bg-black/40" onClick={onClose} />
      <div className="relative z-10 bg-white rounded-2xl shadow-xl border border-slate-200/80 p-6 w-full max-w-sm mx-4">
        <h3 className="text-[15px] font-semibold text-slate-900">{title}</h3>
        <p className="mt-2 text-[13px] text-slate-600">{message}</p>
        <div className="mt-5 flex items-center justify-end gap-3">
          <Button variant="outline" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            variant={variant === 'danger' ? 'danger' : 'primary'}
            onClick={onConfirm}
            loading={loading}
          >
            Confirm
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── CriterionCard (nested inside modal) ──────────────────────────────────────

function CriterionCard({
  index,
  control,
  register,
  errors,
  remove,
}: {
  index: number;
  control: ReturnType<typeof useForm<RubricFormData>>['control'];
  register: ReturnType<typeof useForm<RubricFormData>>['register'];
  errors: ReturnType<typeof useForm<RubricFormData>>['formState']['errors'];
  remove: (index: number) => void;
}) {
  const [showLevels, setShowLevels] = useState(false);
  const { fields: levels, append: addLevel, remove: removeLevel } = useFieldArray({
    control,
    name: `criteria.${index}.levels`,
  });

  const criterionError = errors.criteria?.[index];

  return (
    <div className="border border-slate-200 rounded-xl p-4 space-y-3 bg-slate-50/50">
      {/* Criterion header */}
      <div className="flex items-start gap-3">
        <div className="flex-1 space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="sm:col-span-2">
              <label className="block text-xs font-medium text-slate-600 mb-1">
                Criterion <span className="text-red-500">*</span>
              </label>
              <input
                {...register(`criteria.${index}.title`)}
                type="text"
                placeholder={`e.g. Argument quality, Evidence use…`}
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
              {criterionError?.title && (
                <p className="mt-1 text-xs text-red-600">{criterionError.title.message}</p>
              )}
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-600 mb-1">Max pts <span className="text-red-500">*</span></label>
              <input
                {...register(`criteria.${index}.max_points`)}
                type="number"
                min={0}
                placeholder="10"
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
              {criterionError?.max_points && (
                <p className="mt-1 text-xs text-red-600">{criterionError.max_points.message}</p>
              )}
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Description (optional)</label>
            <input
              {...register(`criteria.${index}.description`)}
              type="text"
              placeholder="What this criterion measures…"
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
            />
          </div>
        </div>

        <button
          type="button"
          onClick={() => remove(index)}
          title="Remove criterion"
          className="flex-shrink-0 p-1.5 text-slate-400 hover:text-red-500 rounded cursor-pointer focus:outline-none focus:ring-2 focus:ring-red-500/30"
        >
          <TrashIcon className="h-4 w-4" />
          <span className="sr-only">Remove criterion</span>
        </button>
      </div>

      {/* Performance levels (collapsible) */}
      <div>
        <button
          type="button"
          onClick={() => setShowLevels((v) => !v)}
          className="flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500 rounded"
        >
          {showLevels ? (
            <ChevronUpIcon className="h-3.5 w-3.5" aria-hidden="true" />
          ) : (
            <ChevronDownIcon className="h-3.5 w-3.5" aria-hidden="true" />
          )}
          Performance levels ({levels.length})
        </button>

        {showLevels && (
          <div className="mt-3 space-y-2 pl-2 border-l-2 border-blue-100">
            {levels.map((level, li) => (
              <div key={level.id} className="flex items-start gap-2 bg-white rounded-lg border border-slate-200 p-3">
                <div className="flex-1 grid grid-cols-1 sm:grid-cols-3 gap-2">
                  <div>
                    <label className="block text-xs text-slate-500 mb-0.5">Level <span className="text-red-500">*</span></label>
                    <input
                      {...register(`criteria.${index}.levels.${li}.title`)}
                      type="text"
                      placeholder="e.g. Excellent"
                      className="w-full px-2 py-1.5 border border-slate-300 rounded-md text-xs focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-0.5">Description</label>
                    <input
                      {...register(`criteria.${index}.levels.${li}.description`)}
                      type="text"
                      placeholder="What earns this level…"
                      className="w-full px-2 py-1.5 border border-slate-300 rounded-md text-xs focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-500 mb-0.5">Points <span className="text-red-500">*</span></label>
                    <input
                      {...register(`criteria.${index}.levels.${li}.points`)}
                      type="number"
                      min={0}
                      placeholder="8"
                      className="w-full px-2 py-1.5 border border-slate-300 rounded-md text-xs focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
                    />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => removeLevel(li)}
                  className="flex-shrink-0 p-1 text-slate-400 hover:text-red-500 cursor-pointer focus:outline-none"
                  title="Remove level"
                >
                  <XCircleIcon className="h-4 w-4" />
                  <span className="sr-only">Remove level</span>
                </button>
              </div>
            ))}

            <button
              type="button"
              onClick={() =>
                addLevel({ title: '', description: '', points: 0, order: levels.length })
              }
              className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1 cursor-pointer focus:outline-none focus:underline"
            >
              <PlusIcon className="h-3.5 w-3.5" />
              Add level
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── RubricModal ───────────────────────────────────────────────────────────────

interface RubricModalProps {
  isOpen: boolean;
  onClose: () => void;
  editingRubric: Rubric | null;
  onSaved: () => void;
}

function RubricModal({ isOpen, onClose, editingRubric, onSaved }: RubricModalProps) {
  const toast = useToast();

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<RubricFormData>({
    resolver: zodResolver(RubricSchema),
    defaultValues: {
      title: '',
      description: '',
      is_active: true,
      criteria: [],
    },
  });

  const { fields: criteria, append: addCriterion, remove: removeCriterion } = useFieldArray({
    control,
    name: 'criteria',
  });

  // Live total points — sum of all criteria max_points
  const watchedCriteria = useWatch({ control, name: 'criteria' });
  const totalPoints = (watchedCriteria ?? []).reduce(
    (sum, c) => sum + (Number(c?.max_points) || 0),
    0,
  );

  // Reset form when modal opens/closes or editing target changes
  useEffect(() => {
    if (isOpen) {
      if (editingRubric) {
        reset({
          title: editingRubric.title,
          description: editingRubric.description,
          is_active: editingRubric.is_active,
          criteria: editingRubric.criteria.map((c) => ({
            title: c.title,
            description: c.description,
            max_points: c.max_points,
            order: c.order,
            levels: c.levels.map((l) => ({
              title: l.title,
              description: l.description,
              points: l.points,
              order: l.order,
            })),
          })),
        });
      } else {
        reset({
          title: '',
          description: '',
          is_active: true,
          criteria: [],
        });
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, editingRubric]);

  const onSubmit = handleSubmit(async (data: RubricFormData) => {
    const payload: RubricWritePayload = {
      title: data.title,
      description: data.description,
      is_active: data.is_active,
      criteria: data.criteria.map((c, ci): RubricCriterionPayload => ({
        title: c.title,
        description: c.description || '',
        max_points: c.max_points,
        order: c.order ?? ci,
        levels: c.levels.map((l, li): RubricLevelPayload => ({
          title: l.title,
          description: l.description || '',
          points: l.points,
          order: l.order ?? li,
        })),
      })),
    };

    try {
      if (editingRubric) {
        await adminRubricService.updateRubric(editingRubric.id, payload);
        toast.success('Rubric updated', `"${data.title}" has been saved.`);
      } else {
        await adminRubricService.createRubric(payload);
        toast.success('Rubric created', `"${data.title}" is ready to use.`);
      }
      onSaved();
      onClose();
    } catch {
      toast.error('Failed to save', 'Please check your inputs and try again.');
    }
  });

  return (
    // HeadlessUI Dialog provides: role="dialog", aria-modal, Escape-key close,
    // and a managed focus trap — replacing the hand-rolled div approach.
    <Dialog open={isOpen} onOpenChange={(open) => { if (!open) onClose(); }}>
      <DialogContent
        // Override default DialogContent sizing/padding to keep the custom
        // header + scrollable-body + sticky-footer layout intact.
        className="w-full max-w-2xl max-h-[90vh] overflow-hidden p-0 flex flex-col"
        showClose={false}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 pt-5 pb-4 border-b border-slate-100 flex-shrink-0">
          <DialogTitle className="text-[15px] font-semibold text-slate-900">
            {editingRubric ? 'Edit Rubric' : 'Create Rubric'}
          </DialogTitle>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <XCircleIcon className="h-5 w-5" aria-hidden="true" />
            <span className="sr-only">Close</span>
          </button>
        </div>

        {/* Body */}
        <form onSubmit={onSubmit} noValidate className="flex flex-col flex-1 min-h-0">
          <div className="px-6 py-5 space-y-5 overflow-y-auto flex-1">
            {/* Title */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Title <span className="text-red-500">*</span>
              </label>
              <input
                {...register('title')}
                type="text"
                placeholder="e.g. Research Essay Rubric"
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
              />
              {errors.title && (
                <p className="mt-1 text-xs text-red-600">{errors.title.message}</p>
              )}
            </div>

            {/* Description */}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Description
              </label>
              <textarea
                {...register('description')}
                rows={2}
                placeholder="What this rubric is used for…"
                className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 resize-none"
              />
            </div>

            {/* Active toggle */}
            <div className="flex items-center gap-3">
              <Controller
                control={control}
                name="is_active"
                render={({ field }) => (
                  <Switch
                    id="is_active"
                    checked={field.value}
                    onCheckedChange={field.onChange}
                    aria-label="Active — available to attach to assignments"
                  />
                )}
              />
              <label htmlFor="is_active" className="text-sm text-slate-700 cursor-pointer select-none">
                Active — available to attach to assignments
              </label>
            </div>

            {/* Criteria */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <p className="text-sm font-medium text-slate-700">
                  Criteria ({criteria.length})
                </p>
                <button
                  type="button"
                  onClick={() =>
                    addCriterion({
                      title: '',
                      description: '',
                      max_points: 10,
                      order: criteria.length,
                      levels: [],
                    })
                  }
                  className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-800 cursor-pointer focus:outline-none focus:underline"
                >
                  <PlusIcon className="h-4 w-4" />
                  Add criterion
                </button>
              </div>

              {criteria.length === 0 ? (
                <div className="text-center py-6 border-2 border-dashed border-slate-200 rounded-xl">
                  <p className="text-sm text-slate-500">
                    No criteria yet. Click "Add criterion" to start building your rubric.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {criteria.map((field, i) => (
                    <CriterionCard
                      key={field.id}
                      index={i}
                      control={control}
                      register={register}
                      errors={errors}
                      remove={removeCriterion}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Footer — live total + actions */}
          <div className="flex items-center justify-between px-6 py-4 border-t border-slate-100 flex-shrink-0">
            <p className="text-sm text-slate-500">
              Total:{' '}
              <span className="font-semibold text-slate-900 tabular-nums">
                {totalPoints} pts
              </span>
            </p>
            <div className="flex items-center gap-3">
              <Button type="button" variant="outline" onClick={onClose} disabled={isSubmitting}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" loading={isSubmitting}>
                {editingRubric ? 'Save changes' : 'Create rubric'}
              </Button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export const RubricPage: React.FC = () => {
  usePageTitle('Rubrics');
  const toast = useToast();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingRubric, setEditingRubric] = useState<Rubric | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Rubric | null>(null);
  // Keep a copy of the title so the delete dialog never shows "undefined"
  // during a re-render triggered by setDeleteTarget(null).
  const [deleteTitle, setDeleteTitle] = useState('');

  // Debounce: update debouncedSearch 300 ms after the user stops typing,
  // and reset to page 1 whenever the search term changes.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  // ── Queries ─────────────────────────────────────────────────────────
  const { data, isLoading } = useQuery({
    queryKey: ['rubrics', debouncedSearch, page],
    queryFn: () =>
      adminRubricService.listRubrics({
        search: debouncedSearch || undefined,
        page,
      }),
  });

  const rubrics = data?.results ?? [];
  const totalCount = data?.count ?? 0;
  const pageSize = 10; // must match backend PAGE_SIZE
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  // ── Mutations ────────────────────────────────────────────────────────

  const deleteMutation = useMutation({
    mutationFn: (id: string) => adminRubricService.deleteRubric(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rubrics'] });
      toast.success('Rubric deleted', `"${deleteTitle}" has been removed.`);
      setDeleteTarget(null);
    },
    onError: () => {
      toast.error('Delete failed', 'Please try again.');
    },
  });

  const cloneMutation = useMutation({
    mutationFn: (rubric: Rubric) => adminRubricService.cloneRubric(rubric.id),
    onSuccess: (clone) => {
      queryClient.invalidateQueries({ queryKey: ['rubrics'] });
      toast.success('Rubric cloned', `Created "${clone.title}"`);
    },
    onError: () => {
      toast.error('Clone failed', 'Please try again.');
    },
  });

  const handleCreate = useCallback(() => {
    setEditingRubric(null);
    setModalOpen(true);
  }, []);

  const handleEdit = useCallback((rubric: Rubric) => {
    setEditingRubric(rubric);
    setModalOpen(true);
  }, []);

  const handleSaved = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ['rubrics'] });
    setPage(1);
  }, [queryClient]);

  // ── Columns ──────────────────────────────────────────────────────────

  const columns: ColumnDef<Rubric>[] = [
    {
      accessorKey: 'title',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Rubric" />,
      cell: ({ row }) => (
        <div>
          <p className="font-medium text-slate-900 text-sm">{row.original.title}</p>
          {row.original.description && (
            <p className="text-xs text-slate-500 truncate max-w-[280px]">
              {row.original.description}
            </p>
          )}
        </div>
      ),
    },
    {
      accessorKey: 'criteria',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Criteria" />,
      cell: ({ row }) => (
        <span className="text-sm text-slate-700 tabular-nums">
          {row.original.criteria.length}
        </span>
      ),
    },
    {
      accessorKey: 'total_points',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Total pts" />,
      cell: ({ getValue }) => (
        <span className="text-sm font-medium text-slate-900 tabular-nums">
          {getValue() as number}
        </span>
      ),
    },
    {
      accessorKey: 'is_active',
      header: ({ column }) => <DataTableColumnHeader column={column} title="Status" />,
      cell: ({ getValue }) =>
        getValue() ? (
          <Badge variant="success">
            <CheckCircleIcon className="h-3.5 w-3.5 mr-1" aria-hidden="true" />
            Active
          </Badge>
        ) : (
          <Badge variant="secondary">Inactive</Badge>
        ),
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => (
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => handleEdit(row.original)}
            title="Edit rubric"
            className="p-1.5 text-slate-400 hover:text-blue-600 rounded-lg cursor-pointer focus:outline-none focus:ring-2 focus:ring-blue-500/30"
          >
            <PencilSquareIcon className="h-4 w-4" />
            <span className="sr-only">Edit</span>
          </button>
          <button
            type="button"
            onClick={() => cloneMutation.mutate(row.original)}
            title="Clone rubric"
            className="p-1.5 text-slate-400 hover:text-emerald-600 rounded-lg cursor-pointer focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
          >
            <DocumentDuplicateIcon className="h-4 w-4" />
            <span className="sr-only">Clone</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setDeleteTitle(row.original.title);
              setDeleteTarget(row.original);
            }}
            title="Delete rubric"
            className="p-1.5 text-slate-400 hover:text-red-600 rounded-lg cursor-pointer focus:outline-none focus:ring-2 focus:ring-red-500/30"
          >
            <TrashIcon className="h-4 w-4" />
            <span className="sr-only">Delete</span>
          </button>
        </div>
      ),
    },
  ];

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="text-[22px] font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <ClipboardDocumentListIcon className="h-6 w-6 text-primary-600" aria-hidden="true" />
            Rubrics
          </h1>
          <p className="mt-1 text-[13px] text-slate-500">
            Design grading rubrics with criteria and performance levels.
            Attach them to assignments to enable structured evaluation.
          </p>
        </div>
        <Button
          variant="primary"
          className="shrink-0 flex items-center gap-2"
          onClick={handleCreate}
        >
          <PlusIcon className="h-4 w-4" aria-hidden="true" />
          New Rubric
        </Button>
      </div>

      {/* Search */}
      <div className="flex items-center gap-3 rounded-xl border border-slate-200/80 bg-white p-4 shadow-sm">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search rubrics by title…"
          className="flex-1 px-3 py-2 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500"
        />
        {search && (
          <button
            type="button"
            onClick={() => setSearch('')}
            className="text-xs text-slate-500 hover:text-slate-800 cursor-pointer"
          >
            Clear
          </button>
        )}
      </div>

      {/* Table */}
      <div className="rounded-xl border border-slate-200/80 bg-white shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="flex justify-center py-16">
            <Loading />
          </div>
        ) : rubrics.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <ClipboardDocumentListIcon
              className="h-10 w-10 text-slate-300 mb-3"
              aria-hidden="true"
            />
            <p className="text-[15px] font-medium text-slate-600">
              {search ? 'No rubrics match your search' : 'No rubrics yet'}
            </p>
            {!search && (
              <p className="text-[13px] text-slate-400 mt-1 max-w-xs">
                Create your first rubric to enable structured feedback on assignment submissions.
              </p>
            )}
            {!search && (
              <Button
                variant="primary"
                className="mt-5 flex items-center gap-2"
                onClick={handleCreate}
              >
                <PlusIcon className="h-4 w-4" />
                Create first rubric
              </Button>
            )}
          </div>
        ) : (
          <>
            <DataTable
              columns={columns}
              data={rubrics}
              hideFilter
              hidePagination
            />
            {/* Server-side pagination controls */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-slate-100">
                <p className="text-xs text-slate-500 tabular-nums">
                  Page {page} of {totalPages} ({totalCount} rubric{totalCount !== 1 ? 's' : ''})
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="h-8 px-3 text-xs"
                  >
                    Previous
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="h-8 px-3 text-xs"
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Create / Edit modal */}
      <RubricModal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        editingRubric={editingRubric}
        onSaved={handleSaved}
      />

      {/* Delete confirm dialog */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
        title={`Delete "${deleteTitle}"?`}
        message="This will permanently remove the rubric. Assignments using it will lose their rubric attachment. This action cannot be undone."
        loading={deleteMutation.isPending}
        variant="danger"
      />
    </div>
  );
};
