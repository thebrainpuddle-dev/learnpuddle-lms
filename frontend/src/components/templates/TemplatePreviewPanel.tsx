// src/components/templates/TemplatePreviewPanel.tsx
//
// Slide-over panel that shows full template detail + blueprint tree.
// Opens when a TemplateCard is clicked; "Use this template" triggers CloneTemplateDialog.

import React, { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import {
  XMarkIcon,
  ClockIcon,
  AcademicCapIcon,
  GlobeAltIcon,
  TagIcon,
} from '@heroicons/react/24/outline';
import { useQuery } from '@tanstack/react-query';
import { courseTemplatesService } from '../../services/courseTemplatesService';
import { BlueprintTreeView } from './BlueprintTreeView';
import { Loading } from '../common';
import type { CourseTemplateListItem } from '../../services/courseTemplatesService';

interface TemplatePreviewPanelProps {
  template: CourseTemplateListItem | null;
  onClose: () => void;
  onClone: () => void;
}

const CATEGORY_LABELS: Record<string, string> = {
  TEACHING_SKILLS: 'Teaching Skills',
  IB_PYP: 'IB PYP',
  IB_MYP: 'IB MYP',
  IB_DP: 'IB DP',
  LEADERSHIP: 'Leadership',
  WELLBEING: 'Wellbeing',
  OTHER: 'Other',
};

/**
 * Slide-over preview panel for a course template.
 * Fetches the full detail (blueprint_json) lazily when a template is selected.
 */
export const TemplatePreviewPanel: React.FC<TemplatePreviewPanelProps> = ({
  template,
  onClose,
  onClone,
}) => {
  const isOpen = template !== null;

  const { data: detail, isLoading } = useQuery({
    queryKey: ['templatePreview', template?.id],
    queryFn: () => courseTemplatesService.tenant.previewTemplate(template!.id),
    enabled: isOpen,
    staleTime: 5 * 60 * 1000, // 5 min
  });

  return (
    <Transition.Root show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-40" onClose={onClose}>
        {/* Backdrop */}
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

        {/* Panel */}
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
                <Dialog.Panel className="pointer-events-auto w-screen max-w-md">
                  <div className="flex h-full flex-col bg-white shadow-xl">
                    {/* Header */}
                    <div className="flex items-start justify-between border-b border-gray-200 px-5 py-4">
                      <Dialog.Title className="text-base font-semibold text-gray-900 pr-4">
                        {template?.title ?? 'Template Preview'}
                      </Dialog.Title>
                      <button
                        type="button"
                        onClick={onClose}
                        className="rounded-md text-gray-400 hover:text-gray-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 transition-colors"
                        aria-label="Close preview"
                      >
                        <XMarkIcon className="h-5 w-5" />
                      </button>
                    </div>

                    {/* Body */}
                    <div className="flex-1 overflow-y-auto px-5 py-4 space-y-5">
                      {isLoading ? (
                        <div className="flex justify-center pt-12">
                          <Loading />
                        </div>
                      ) : detail ? (
                        <>
                          {/* Thumbnail */}
                          {detail.thumbnail_url && (
                            <img
                              src={detail.thumbnail_url}
                              alt={detail.title}
                              className="w-full h-40 object-cover rounded-lg"
                              loading="lazy"
                            />
                          )}

                          {/* Meta badges */}
                          <div className="flex flex-wrap gap-2">
                            <span className="flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600">
                              <TagIcon className="h-3.5 w-3.5" />
                              {CATEGORY_LABELS[detail.category] ?? detail.category}
                            </span>
                            <span className="flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600">
                              <AcademicCapIcon className="h-3.5 w-3.5" />
                              {detail.level}
                            </span>
                            {detail.estimated_hours > 0 && (
                              <span className="flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600">
                                <ClockIcon className="h-3.5 w-3.5" />
                                {detail.estimated_hours}h estimated
                              </span>
                            )}
                            <span className="flex items-center gap-1 rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600">
                              <GlobeAltIcon className="h-3.5 w-3.5" />
                              {detail.language.toUpperCase()}
                            </span>
                          </div>

                          {/* Description */}
                          {detail.description && (
                            <div>
                              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500">
                                Description
                              </h4>
                              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                                {detail.description}
                              </p>
                            </div>
                          )}

                          {/* Blueprint tree */}
                          <div>
                            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-500">
                              Course Structure
                            </h4>
                            <BlueprintTreeView blueprint={detail.blueprint_json} />
                          </div>
                        </>
                      ) : (
                        <p className="text-sm text-gray-500 text-center pt-12">
                          Failed to load template details.
                        </p>
                      )}
                    </div>

                    {/* Footer action */}
                    <div className="border-t border-gray-200 px-5 py-4">
                      <button
                        type="button"
                        onClick={onClone}
                        disabled={isLoading || !detail}
                        className="w-full rounded-lg bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        Use this template
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
