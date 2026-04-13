// course-editor/CourseModuleList.tsx
//
// Content tab: module list with expand/collapse, add module, and per-module
// content items. Delegates to ModuleContentEditor for rich text editing.

import React from 'react';
import { Button } from '../../../components/common';
import {
  PlusIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  PencilIcon,
  TrashIcon,
  Bars3Icon,
} from '@heroicons/react/24/outline';
import { ModuleContentEditor } from './ModuleContentEditor';
import type { CourseEditorState } from './useCourseEditor';

interface CourseModuleListProps {
  state: CourseEditorState;
}

export const CourseModuleList: React.FC<CourseModuleListProps> = ({
  state,
}) => {
  const {
    course,
    courseId,
    expandedModules,
    toggleModule,
    editingModule,
    setEditingModule,
    newModuleTitle,
    setNewModuleTitle,
    handleAddModule,
    moduleMutation,
    updateModuleMutation,
    setConfirmDelete,
  } = state;

  return (
    <div data-tour="admin-course-content-panel" className="space-y-4">
      {/* Add Module */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex items-center space-x-3">
          <input
            id="new-module-title"
            name="new_module_title"
            type="text"
            value={newModuleTitle}
            onChange={(e) => setNewModuleTitle(e.target.value)}
            placeholder="Optional module title (you can rename it anytime)"
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
            onKeyDown={(e) => e.key === 'Enter' && handleAddModule()}
          />
          <Button
            variant="primary"
            onClick={handleAddModule}
            loading={moduleMutation.isPending}
          >
            <PlusIcon className="h-5 w-5 mr-1" />
            Add Module
          </Button>
        </div>
      </div>

      {/* Modules List */}
      {course?.modules?.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
          <Bars3Icon className="h-12 w-12 mx-auto text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-1">
            No modules yet
          </h3>
          <p className="text-gray-500">
            Add your first module to start building lessons
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {course?.modules?.map((module, moduleIndex) => {
            const moduleLabel =
              module.title?.trim() ||
              `Untitled Module ${moduleIndex + 1}`;
            return (
              <div
                key={module.id}
                className="bg-white rounded-xl border border-gray-200 overflow-hidden"
              >
                {/* Module Header */}
                <div
                  className="flex items-center justify-between p-4 bg-gray-50 cursor-pointer"
                  onClick={() => toggleModule(module.id)}
                >
                  <div className="flex items-center">
                    {expandedModules.includes(module.id) ? (
                      <ChevronUpIcon className="h-5 w-5 text-gray-400 mr-2" />
                    ) : (
                      <ChevronDownIcon className="h-5 w-5 text-gray-400 mr-2" />
                    )}

                    {editingModule === module.id ? (
                      <input
                        id={`module-title-${module.id}`}
                        name="module_title"
                        aria-label={`Module title for ${moduleLabel}`}
                        type="text"
                        defaultValue={module.title || ''}
                        placeholder={`Untitled Module ${moduleIndex + 1}`}
                        className="px-2 py-1 border border-gray-300 rounded"
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') {
                            updateModuleMutation.mutate({
                              courseId: courseId!,
                              moduleId: module.id,
                              data: {
                                title: (e.target as HTMLInputElement)
                                  .value,
                              },
                            });
                          }
                        }}
                        autoFocus
                      />
                    ) : (
                      <span className="font-medium text-gray-900">
                        {moduleLabel}
                      </span>
                    )}
                  </div>

                  <div
                    className="flex items-center space-x-2"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <span className="text-sm text-gray-500">
                      {module.contents?.length || 0} items
                    </span>
                    <button
                      onClick={() =>
                        setEditingModule(
                          editingModule === module.id
                            ? null
                            : module.id,
                        )
                      }
                      className="p-1 text-gray-400 hover:text-primary-600 rounded"
                    >
                      <PencilIcon className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() =>
                        setConfirmDelete({
                          type: 'module',
                          moduleId: module.id,
                          label: moduleLabel,
                        })
                      }
                      className="p-1 text-gray-400 hover:text-red-600 rounded"
                    >
                      <TrashIcon className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                {/* Module Content */}
                {expandedModules.includes(module.id) && (
                  <ModuleContentEditor
                    state={state}
                    module={module}
                    moduleIndex={moduleIndex}
                  />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
