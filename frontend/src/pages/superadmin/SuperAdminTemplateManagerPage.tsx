// src/pages/superadmin/SuperAdminTemplateManagerPage.tsx
//
// Super-admin CRUD manager for the platform-level course template library.
// Columns: slug, title, category, language, level, is_published, updated_at, actions.
// Row actions: publish toggle, edit (opens drawer), delete (soft / hard).

import React, { useState, Fragment } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Dialog, Transition } from '@headlessui/react';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  CheckCircleIcon,
  XCircleIcon,
  XMarkIcon,
  Squares2X2Icon,
} from '@heroicons/react/24/outline';
import {
  courseTemplatesService,
  type CourseTemplateListItem,
  type TemplateWritePayload,
  type BlueprintJson,
} from '../../services/courseTemplatesService';
import { useZodForm } from '../../hooks/useZodForm';
import { useToast } from '../../components/common/Toast';
import { usePageTitle } from '../../hooks/usePageTitle';

// ─── Zod Schemas ──────────────────────────────────────────────────────────────

function parseBlueprintJson(raw: string): BlueprintJson {
  const parsed: unknown = JSON.parse(raw);
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    throw new Error('blueprint_json must be a JSON object');
  }
  const obj = parsed as Record<string, unknown>;
  if (!('title' in obj) && !('course' in obj)) {
    throw new Error('blueprint_json must contain a "title" or "course" key');
  }
  if ('modules' in obj && !Array.isArray(obj.modules)) {
    throw new Error('"modules" must be an array');
  }
  return obj as unknown as BlueprintJson;
}

const TemplateFormSchema = z.object({
  slug: z.string().min(1, 'Slug is required').max(200),
  title: z.string().min(1, 'Title is required').max(300),
  description: z.string().max(2000).optional().or(z.literal('')),
  category: z.enum([
    'TEACHING_SKILLS',
    'IB_PYP',
    'IB_MYP',
    'IB_DP',
    'LEADERSHIP',
    'WELLBEING',
    'OTHER',
  ]),
  language: z.string().min(2, 'Language code required').max(10),
  level: z.enum(['BEGINNER', 'INTERMEDIATE', 'ADVANCED']),
  estimated_hours: z.coerce.number().int().min(0).max(10000),
  thumbnail_url: z.string().url('Must be a valid URL').optional().or(z.literal('')),
  is_published: z.boolean(),
  blueprint_json_raw: z
    .string()
    .min(2, 'Blueprint JSON is required')
    .refine(
      (val) => {
        try {
          parseBlueprintJson(val);
          return true;
        } catch {
          return false;
        }
      },
      {
        message:
          'Must be valid JSON with a "title" or "course" key. "modules" must be an array.',
      },
    ),
});

type TemplateFormValues = z.infer<typeof TemplateFormSchema>;

const DEFAULT_BLUEPRINT = JSON.stringify(
  {
    schema_version: 1,
    course: { title: '', description: '', estimated_hours: 0, is_mandatory: false },
    modules: [],
  },
  null,
  2,
);

// ─── Delete Dialog ────────────────────────────────────────────────────────────

interface DeleteDialogProps {
  template: CourseTemplateListItem | null;
  onClose: () => void;
  onConfirm: (hard: boolean) => void;
  isLoading: boolean;
}

const DeleteDialog: React.FC<DeleteDialogProps> = ({
  template,
  onClose,
  onConfirm,
  isLoading,
}) => {
  const [mode, setMode] = useState<'soft' | 'hard'>('soft');
  const [understood, setUnderstood] = useState(false);

  const handleClose = () => {
    if (isLoading) return;
    setMode('soft');
    setUnderstood(false);
    onClose();
  };

  const canConfirmHard = mode === 'hard' && understood;
  const canConfirm = mode === 'soft' || canConfirmHard;

  return (
    <Transition.Root show={template !== null} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={handleClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/40" />
        </Transition.Child>
        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-150"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-md transform rounded-2xl bg-white p-6 shadow-xl transition-all">
                <Dialog.Title className="text-base font-semibold text-gray-900 mb-1">
                  Delete template
                </Dialog.Title>
                {template && (
                  <p className="text-sm text-gray-500 mb-5 truncate">
                    {template.title}
                  </p>
                )}

                <fieldset className="space-y-3 mb-5">
                  <legend className="text-sm font-medium text-gray-700 mb-2">
                    Delete type
                  </legend>

                  <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-gray-200 p-3 hover:bg-gray-50 transition-colors">
                    <input
                      type="radio"
                      name="delete-mode"
                      value="soft"
                      checked={mode === 'soft'}
                      onChange={() => { setMode('soft'); setUnderstood(false); }}
                      className="mt-0.5"
                      data-testid="radio-soft"
                    />
                    <div>
                      <p className="text-sm font-medium text-gray-800">Soft unpublish</p>
                      <p className="text-xs text-gray-500 mt-0.5">
                        Marks the template as unpublished. It remains in the database and can be re-published.
                      </p>
                    </div>
                  </label>

                  <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-red-200 p-3 hover:bg-red-50 transition-colors">
                    <input
                      type="radio"
                      name="delete-mode"
                      value="hard"
                      checked={mode === 'hard'}
                      onChange={() => setMode('hard')}
                      className="mt-0.5"
                      data-testid="radio-hard"
                    />
                    <div>
                      <p className="text-sm font-medium text-red-700">Hard delete</p>
                      <p className="text-xs text-red-500 mt-0.5">
                        Permanently removes the template from the database. This cannot be undone.
                      </p>
                    </div>
                  </label>
                </fieldset>

                {mode === 'hard' && (
                  <label className="flex cursor-pointer items-start gap-2 mb-5">
                    <input
                      type="checkbox"
                      checked={understood}
                      onChange={(e) => setUnderstood(e.target.checked)}
                      data-testid="hard-delete-checkbox"
                      className="mt-0.5 h-4 w-4 rounded border-gray-300 text-red-600 focus:ring-red-500"
                    />
                    <span className="text-sm text-red-700">
                      I understand this will permanently delete this template
                    </span>
                  </label>
                )}

                <div className="flex justify-end gap-3">
                  <button
                    type="button"
                    onClick={handleClose}
                    disabled={isLoading}
                    className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => onConfirm(mode === 'hard')}
                    disabled={isLoading || !canConfirm}
                    data-testid="confirm-delete-btn"
                    className={`rounded-lg px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors disabled:opacity-50 ${
                      mode === 'hard'
                        ? 'bg-red-600 hover:bg-red-700'
                        : 'bg-amber-600 hover:bg-amber-700'
                    }`}
                  >
                    {isLoading ? 'Deleting…' : mode === 'hard' ? 'Delete permanently' : 'Unpublish'}
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  );
};

// ─── Template Form Drawer ─────────────────────────────────────────────────────

interface TemplateFormDrawerProps {
  template: CourseTemplateListItem | null;
  isNew: boolean;
  isOpen: boolean;
  onClose: () => void;
  onSaved: () => void;
}

const TemplateFormDrawer: React.FC<TemplateFormDrawerProps> = ({
  template,
  isNew,
  isOpen,
  onClose,
  onSaved,
}) => {
  const toast = useToast();
  const queryClient = useQueryClient();

  // Fetch full detail (blueprint) when editing an existing template
  const { data: detail } = useQuery({
    queryKey: ['superAdminTemplate', template?.id],
    queryFn: () => courseTemplatesService.superAdmin.getTemplate(template!.id),
    enabled: !isNew && template !== null && isOpen,
    staleTime: 60 * 1000,
  });

  const form = useZodForm({
    schema: TemplateFormSchema,
    defaultValues: {
      slug: '',
      title: '',
      description: '',
      category: 'OTHER',
      language: 'en',
      level: 'BEGINNER',
      estimated_hours: 0,
      thumbnail_url: '',
      is_published: false,
      blueprint_json_raw: DEFAULT_BLUEPRINT,
    },
  });

  // Populate form when editing
  React.useEffect(() => {
    if (!isOpen) return;
    if (isNew) {
      form.reset({
        slug: '',
        title: '',
        description: '',
        category: 'OTHER',
        language: 'en',
        level: 'BEGINNER',
        estimated_hours: 0,
        thumbnail_url: '',
        is_published: false,
        blueprint_json_raw: DEFAULT_BLUEPRINT,
      });
    } else if (detail) {
      form.reset({
        slug: detail.slug,
        title: detail.title,
        description: detail.description ?? '',
        category: detail.category,
        language: detail.language,
        level: detail.level,
        estimated_hours: detail.estimated_hours ?? 0,
        thumbnail_url: detail.thumbnail_url ?? '',
        is_published: detail.is_published,
        blueprint_json_raw: JSON.stringify(detail.blueprint_json, null, 2),
      });
    }
  }, [isOpen, isNew, detail, form]);

  const saveMutation = useMutation({
    mutationFn: (values: TemplateFormValues) => {
      const blueprint = parseBlueprintJson(values.blueprint_json_raw);
      const payload: TemplateWritePayload = {
        slug: values.slug,
        title: values.title,
        description: values.description || '',
        category: values.category,
        language: values.language,
        level: values.level,
        estimated_hours: values.estimated_hours,
        thumbnail_url: values.thumbnail_url || '',
        is_published: values.is_published,
        blueprint_json: blueprint,
      };
      if (isNew) {
        return courseTemplatesService.superAdmin.createTemplate(payload);
      }
      return courseTemplatesService.superAdmin.updateTemplate(template!.id, payload);
    },
    onSuccess: () => {
      toast.success(isNew ? 'Template created' : 'Template updated');
      queryClient.invalidateQueries({ queryKey: ['superAdminTemplates'] });
      onSaved();
    },
    onError: () => {
      toast.error('Save failed', 'Please check your input and try again.');
    },
  });

  const onSubmit = (values: TemplateFormValues) => {
    saveMutation.mutate(values);
  };

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-40" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-in-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in-out duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/30" />
        </Transition.Child>
        <div className="fixed inset-0 overflow-hidden">
          <div className="absolute inset-0 overflow-hidden">
            <div className="pointer-events-none fixed inset-y-0 right-0 flex max-w-full pl-10">
              <Transition.Child
                as={Fragment}
                enter="transform transition ease-in-out duration-300"
                enterFrom="translate-x-full"
                enterTo="translate-x-0"
                leave="transform transition ease-in-out duration-200"
                leaveFrom="translate-x-0"
                leaveTo="translate-x-full"
              >
                <Dialog.Panel className="pointer-events-auto w-screen max-w-lg">
                  <div className="flex h-full flex-col bg-white shadow-xl">
                    {/* Header */}
                    <div className="flex items-center justify-between border-b border-gray-200 px-5 py-4">
                      <Dialog.Title className="text-base font-semibold text-gray-900">
                        {isNew ? 'New template' : 'Edit template'}
                      </Dialog.Title>
                      <button
                        type="button"
                        onClick={onClose}
                        className="text-gray-400 hover:text-gray-500 transition-colors"
                        aria-label="Close drawer"
                      >
                        <XMarkIcon className="h-5 w-5" />
                      </button>
                    </div>

                    {/* Form */}
                    <form
                      onSubmit={form.handleSubmit(onSubmit)}
                      className="flex-1 overflow-y-auto px-5 py-4 space-y-4"
                      noValidate
                    >
                      {/* Slug */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Slug <span className="text-red-500">*</span>
                        </label>
                        <Controller
                          control={form.control}
                          name="slug"
                          render={({ field, fieldState }) => (
                            <>
                              <input
                                {...field}
                                type="text"
                                placeholder="e.g. ib-pyp-inquiry-beginner"
                                className={`block w-full rounded-lg border px-3 py-2 text-sm ${fieldState.error ? 'border-red-300 focus:ring-red-400' : 'border-gray-300 focus:ring-primary-500'} focus:outline-none focus:ring-2 transition-colors`}
                              />
                              {fieldState.error && <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>}
                            </>
                          )}
                        />
                      </div>

                      {/* Title */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Title <span className="text-red-500">*</span>
                        </label>
                        <Controller
                          control={form.control}
                          name="title"
                          render={({ field, fieldState }) => (
                            <>
                              <input
                                {...field}
                                type="text"
                                className={`block w-full rounded-lg border px-3 py-2 text-sm ${fieldState.error ? 'border-red-300 focus:ring-red-400' : 'border-gray-300 focus:ring-primary-500'} focus:outline-none focus:ring-2 transition-colors`}
                              />
                              {fieldState.error && <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>}
                            </>
                          )}
                        />
                      </div>

                      {/* Description */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                        <Controller
                          control={form.control}
                          name="description"
                          render={({ field }) => (
                            <textarea
                              {...field}
                              rows={3}
                              className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-200 transition-colors"
                            />
                          )}
                        />
                      </div>

                      {/* Category + Level */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Category</label>
                          <Controller
                            control={form.control}
                            name="category"
                            render={({ field }) => (
                              <select {...field} className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-200 cursor-pointer">
                                <option value="TEACHING_SKILLS">Teaching Skills</option>
                                <option value="IB_PYP">IB PYP</option>
                                <option value="IB_MYP">IB MYP</option>
                                <option value="IB_DP">IB DP</option>
                                <option value="LEADERSHIP">Leadership</option>
                                <option value="WELLBEING">Wellbeing</option>
                                <option value="OTHER">Other</option>
                              </select>
                            )}
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Level</label>
                          <Controller
                            control={form.control}
                            name="level"
                            render={({ field }) => (
                              <select {...field} className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-200 cursor-pointer">
                                <option value="BEGINNER">Beginner</option>
                                <option value="INTERMEDIATE">Intermediate</option>
                                <option value="ADVANCED">Advanced</option>
                              </select>
                            )}
                          />
                        </div>
                      </div>

                      {/* Language + Hours */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Language</label>
                          <Controller
                            control={form.control}
                            name="language"
                            render={({ field, fieldState }) => (
                              <>
                                <input {...field} type="text" placeholder="en" className={`block w-full rounded-lg border px-3 py-2 text-sm ${fieldState.error ? 'border-red-300' : 'border-gray-300 focus:ring-primary-500'} focus:outline-none focus:ring-2 transition-colors`} />
                                {fieldState.error && <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>}
                              </>
                            )}
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 mb-1">Estimated hours</label>
                          <Controller
                            control={form.control}
                            name="estimated_hours"
                            render={({ field, fieldState }) => (
                              <>
                                <input {...field} type="number" min="0" className={`block w-full rounded-lg border px-3 py-2 text-sm ${fieldState.error ? 'border-red-300' : 'border-gray-300 focus:ring-primary-500'} focus:outline-none focus:ring-2 transition-colors`} />
                                {fieldState.error && <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>}
                              </>
                            )}
                          />
                        </div>
                      </div>

                      {/* Thumbnail URL */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Thumbnail URL</label>
                        <Controller
                          control={form.control}
                          name="thumbnail_url"
                          render={({ field, fieldState }) => (
                            <>
                              <input {...field} type="url" placeholder="https://…" className={`block w-full rounded-lg border px-3 py-2 text-sm ${fieldState.error ? 'border-red-300' : 'border-gray-300 focus:ring-primary-500'} focus:outline-none focus:ring-2 transition-colors`} />
                              {fieldState.error && <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>}
                            </>
                          )}
                        />
                      </div>

                      {/* Published */}
                      <label className="flex cursor-pointer items-center gap-3">
                        <Controller
                          control={form.control}
                          name="is_published"
                          render={({ field }) => (
                            <input
                              type="checkbox"
                              checked={field.value}
                              onChange={(e) => field.onChange(e.target.checked)}
                              className="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                              data-testid="is-published-checkbox"
                            />
                          )}
                        />
                        <span className="text-sm font-medium text-gray-700">
                          Published (visible to tenant admins)
                        </span>
                      </label>

                      {/* Blueprint JSON */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">
                          Blueprint JSON <span className="text-red-500">*</span>
                        </label>
                        <Controller
                          control={form.control}
                          name="blueprint_json_raw"
                          render={({ field, fieldState }) => (
                            <>
                              <textarea
                                {...field}
                                rows={12}
                                spellCheck={false}
                                data-testid="blueprint-json-textarea"
                                className={`block w-full rounded-lg border font-mono text-xs px-3 py-2 ${fieldState.error ? 'border-red-300 focus:ring-red-400' : 'border-gray-300 focus:ring-primary-500'} focus:outline-none focus:ring-2 transition-colors`}
                              />
                              {fieldState.error && (
                                <p className="mt-1 text-xs text-red-600">{fieldState.error.message}</p>
                              )}
                              <p className="mt-1 text-xs text-gray-400">
                                Must be valid JSON. Required: a top-level "title" or "course" key; "modules" must be an array.
                              </p>
                            </>
                          )}
                        />
                      </div>
                    </form>

                    {/* Footer */}
                    <div className="border-t border-gray-200 px-5 py-4 flex justify-end gap-3">
                      <button
                        type="button"
                        onClick={onClose}
                        className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={form.handleSubmit(onSubmit)}
                        disabled={saveMutation.isPending}
                        data-testid="save-template-btn"
                        className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50 transition-colors"
                      >
                        {saveMutation.isPending ? 'Saving…' : isNew ? 'Create template' : 'Save changes'}
                      </button>
                    </div>
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  );
};

// ─── Main Page ────────────────────────────────────────────────────────────────

/**
 * Super-admin template library manager.
 * Full CRUD: create, edit, publish/unpublish toggle, soft/hard delete.
 */
export const SuperAdminTemplateManagerPage: React.FC = () => {
  usePageTitle('Template Library');

  const toast = useToast();
  const queryClient = useQueryClient();

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<CourseTemplateListItem | null>(null);
  const [deletingTemplate, setDeletingTemplate] = useState<CourseTemplateListItem | null>(null);
  const [isNew, setIsNew] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['superAdminTemplates'],
    queryFn: () => courseTemplatesService.superAdmin.listAllTemplates(),
    staleTime: 60 * 1000,
  });

  const templates = data?.results ?? [];

  // Publish toggle
  const publishMutation = useMutation({
    mutationFn: ({ id, is_published }: { id: string; is_published: boolean }) =>
      courseTemplatesService.superAdmin.updateTemplate(id, { is_published }),
    onSuccess: (updated) => {
      if (updated) {
        toast.success(
          updated.is_published ? 'Template published' : 'Template unpublished',
        );
      }
      queryClient.invalidateQueries({ queryKey: ['superAdminTemplates'] });
    },
    onError: () => toast.error('Toggle failed', 'Please try again.'),
  });

  // Delete
  const deleteMutation = useMutation({
    mutationFn: ({ id, hard }: { id: string; hard: boolean }) =>
      courseTemplatesService.superAdmin.deleteTemplate(id, hard),
    onSuccess: (_result, variables) => {
      toast.success(variables.hard ? 'Template deleted' : 'Template unpublished');
      queryClient.invalidateQueries({ queryKey: ['superAdminTemplates'] });
      setDeletingTemplate(null);
    },
    onError: () => toast.error('Delete failed', 'Please try again.'),
  });

  const openCreate = () => {
    setEditingTemplate(null);
    setIsNew(true);
    setDrawerOpen(true);
  };

  const openEdit = (t: CourseTemplateListItem) => {
    setEditingTemplate(t);
    setIsNew(false);
    setDrawerOpen(true);
  };

  const CATEGORY_LABELS: Record<string, string> = {
    TEACHING_SKILLS: 'Teaching Skills',
    IB_PYP: 'IB PYP',
    IB_MYP: 'IB MYP',
    IB_DP: 'IB DP',
    LEADERSHIP: 'Leadership',
    WELLBEING: 'Wellbeing',
    OTHER: 'Other',
  };

  return (
    <>
      <div
        className="space-y-6 p-4 sm:p-6"
        data-testid="super-admin-template-manager"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-[22px] font-bold text-slate-900 tracking-tight flex items-center gap-2">
              <Squares2X2Icon className="h-6 w-6 text-indigo-500" />
              Template Library
            </h1>
            <p className="mt-1 text-sm text-slate-400">
              Manage platform-level course templates available to all schools.
            </p>
          </div>
          <button
            type="button"
            onClick={openCreate}
            data-testid="create-template-btn"
            className="flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-indigo-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600 transition-colors"
          >
            <PlusIcon className="h-4 w-4" />
            New template
          </button>
        </div>

        {/* Table */}
        {isLoading ? (
          <div className="animate-pulse space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-12 rounded-lg bg-slate-800/10" />
            ))}
          </div>
        ) : templates.length === 0 ? (
          <div className="rounded-xl border border-slate-200 bg-white p-12 text-center">
            <Squares2X2Icon className="mx-auto h-12 w-12 text-slate-300 mb-3" />
            <p className="text-slate-500 text-sm">No templates yet. Create the first one.</p>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white" data-testid="templates-table">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Slug</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Title</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Category</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Lang</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Level</th>
                  <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wide text-slate-500">Published</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Updated</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {templates.map((t) => (
                  <tr key={t.id} data-testid="template-row" className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-slate-500 max-w-[120px] truncate">{t.slug}</td>
                    <td className="px-4 py-3 font-medium text-slate-900 max-w-[200px] truncate">{t.title}</td>
                    <td className="px-4 py-3 text-slate-600">{CATEGORY_LABELS[t.category] ?? t.category}</td>
                    <td className="px-4 py-3 text-slate-600 uppercase">{t.language}</td>
                    <td className="px-4 py-3">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
                        t.level === 'BEGINNER'
                          ? 'bg-emerald-100 text-emerald-700'
                          : t.level === 'INTERMEDIATE'
                          ? 'bg-amber-100 text-amber-700'
                          : 'bg-red-100 text-red-700'
                      }`}>
                        {t.level}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        type="button"
                        onClick={() =>
                          publishMutation.mutate({
                            id: t.id,
                            is_published: !t.is_published,
                          })
                        }
                        title={t.is_published ? 'Click to unpublish' : 'Click to publish'}
                        data-testid={`publish-toggle-${t.id}`}
                        className="inline-flex cursor-pointer transition-opacity hover:opacity-80"
                        aria-label={t.is_published ? 'Unpublish template' : 'Publish template'}
                      >
                        {t.is_published ? (
                          <CheckCircleIcon className="h-5 w-5 text-emerald-500" />
                        ) : (
                          <XCircleIcon className="h-5 w-5 text-slate-300" />
                        )}
                      </button>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400 whitespace-nowrap">
                      {new Date(t.updated_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => openEdit(t)}
                          title="Edit"
                          data-testid={`edit-btn-${t.id}`}
                          className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700 transition-colors"
                        >
                          <PencilIcon className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeletingTemplate(t)}
                          title="Delete"
                          data-testid={`delete-btn-${t.id}`}
                          className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600 transition-colors"
                        >
                          <TrashIcon className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Edit / Create drawer */}
      <TemplateFormDrawer
        template={editingTemplate}
        isNew={isNew}
        isOpen={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onSaved={() => setDrawerOpen(false)}
      />

      {/* Delete dialog */}
      <DeleteDialog
        template={deletingTemplate}
        onClose={() => setDeletingTemplate(null)}
        onConfirm={(hard) => {
          if (deletingTemplate) {
            deleteMutation.mutate({ id: deletingTemplate.id, hard });
          }
        }}
        isLoading={deleteMutation.isPending}
      />
    </>
  );
};
