// src/components/templates/CloneTemplateDialog.tsx
//
// Modal dialog for cloning a template into the current tenant.
// Uses RHF + Zod for validation.
// On success: shows a toast and navigates to the new course's edit page.

import React, { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { XMarkIcon } from '@heroicons/react/24/outline';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { z } from 'zod';
import { Controller } from 'react-hook-form';
import {
  courseTemplatesService,
  type CourseTemplateListItem,
} from '../../services/courseTemplatesService';
import { useZodForm } from '../../hooks/useZodForm';
import { useToast } from '../common/Toast';

// ─── Zod Schema ───────────────────────────────────────────────────────────────

export const CloneTemplateSchema = z.object({
  title_override: z
    .string()
    .max(200, 'Title must be 200 characters or fewer')
    .optional()
    .or(z.literal('')),
  module_prefix: z
    .string()
    .max(50, 'Module prefix must be 50 characters or fewer')
    .optional()
    .or(z.literal('')),
});

export type CloneTemplateFormValues = z.infer<typeof CloneTemplateSchema>;

// ─── Props ────────────────────────────────────────────────────────────────────

interface CloneTemplateDialogProps {
  template: CourseTemplateListItem | null;
  onClose: () => void;
}

/**
 * Dialog form for cloning a published template into the current tenant.
 *
 * @example
 * <CloneTemplateDialog template={selected} onClose={() => setSelected(null)} />
 */
export const CloneTemplateDialog: React.FC<CloneTemplateDialogProps> = ({
  template,
  onClose,
}) => {
  const isOpen = template !== null;
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const form = useZodForm({
    schema: CloneTemplateSchema,
    defaultValues: {
      title_override: '',
      module_prefix: '',
    },
  });

  const cloneMutation = useMutation({
    mutationFn: (values: CloneTemplateFormValues) =>
      courseTemplatesService.tenant.cloneTemplate(template!.id, {
        title_override: values.title_override || undefined,
        module_prefix: values.module_prefix || undefined,
      }),
    onSuccess: (course) => {
      toast.success(
        'Template cloned!',
        `"${course.title}" has been added to your courses.`,
      );
      queryClient.invalidateQueries({ queryKey: ['adminCourses'] });
      onClose();
      navigate(`/admin/courses/${course.id}/edit`);
    },
    onError: () => {
      toast.error('Clone failed', 'Something went wrong. Please try again.');
    },
  });

  const handleClose = () => {
    if (cloneMutation.isPending) return;
    form.reset();
    onClose();
  };

  const onSubmit = (values: CloneTemplateFormValues) => {
    cloneMutation.mutate(values);
  };

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={handleClose}>
        {/* Backdrop */}
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
                {/* Header */}
                <div className="flex items-start justify-between mb-5">
                  <div>
                    <Dialog.Title className="text-lg font-semibold text-gray-900">
                      Use this template
                    </Dialog.Title>
                    {template && (
                      <p className="mt-0.5 text-sm text-gray-500 truncate max-w-xs">
                        {template.title}
                      </p>
                    )}
                  </div>
                  <button
                    type="button"
                    onClick={handleClose}
                    disabled={cloneMutation.isPending}
                    className="rounded-md text-gray-400 hover:text-gray-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:opacity-50 transition-colors"
                    aria-label="Close dialog"
                  >
                    <XMarkIcon className="h-5 w-5" />
                  </button>
                </div>

                {/* Form */}
                <form onSubmit={form.handleSubmit(onSubmit)} noValidate>
                  <div className="space-y-4">
                    {/* Title override */}
                    <Controller
                      control={form.control}
                      name="title_override"
                      render={({ field, fieldState }) => (
                        <div>
                          <label
                            htmlFor="title_override"
                            className="block text-sm font-medium text-gray-700 mb-1"
                          >
                            Course title
                            <span className="ml-1 text-xs text-gray-400 font-normal">
                              (optional — defaults to template title)
                            </span>
                          </label>
                          <input
                            {...field}
                            id="title_override"
                            type="text"
                            placeholder={template?.title ?? 'Enter a custom title…'}
                            className={`block w-full rounded-lg border px-3 py-2 text-sm shadow-sm placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                              fieldState.error
                                ? 'border-red-300 focus:ring-red-400'
                                : 'border-gray-300 focus:ring-primary-500'
                            }`}
                          />
                          {fieldState.error && (
                            <p className="mt-1 text-xs text-red-600">
                              {fieldState.error.message}
                            </p>
                          )}
                        </div>
                      )}
                    />

                    {/* Module prefix */}
                    <Controller
                      control={form.control}
                      name="module_prefix"
                      render={({ field, fieldState }) => (
                        <div>
                          <label
                            htmlFor="module_prefix"
                            className="block text-sm font-medium text-gray-700 mb-1"
                          >
                            Module prefix
                            <span className="ml-1 text-xs text-gray-400 font-normal">
                              (optional — e.g. "Term 1 – ")
                            </span>
                          </label>
                          <input
                            {...field}
                            id="module_prefix"
                            type="text"
                            placeholder="e.g. Term 1 – "
                            className={`block w-full rounded-lg border px-3 py-2 text-sm shadow-sm placeholder-gray-400 focus:outline-none focus:ring-2 transition-colors ${
                              fieldState.error
                                ? 'border-red-300 focus:ring-red-400'
                                : 'border-gray-300 focus:ring-primary-500'
                            }`}
                          />
                          {fieldState.error && (
                            <p className="mt-1 text-xs text-red-600">
                              {fieldState.error.message}
                            </p>
                          )}
                          <p className="mt-1 text-xs text-gray-400">
                            This prefix is prepended to every module name during cloning.
                          </p>
                        </div>
                      )}
                    />
                  </div>

                  {/* Actions */}
                  <div className="mt-6 flex justify-end gap-3">
                    <button
                      type="button"
                      onClick={handleClose}
                      disabled={cloneMutation.isPending}
                      className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:opacity-50 transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={cloneMutation.isPending}
                      className="rounded-lg bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:opacity-50 transition-colors"
                    >
                      {cloneMutation.isPending ? 'Cloning…' : 'Clone into my courses'}
                    </button>
                  </div>
                </form>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  );
};
