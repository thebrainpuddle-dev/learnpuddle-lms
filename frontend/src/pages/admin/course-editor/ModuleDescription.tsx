// course-editor/ModuleDescription.tsx
//
// Renders the module description editor / display area within ModuleContentEditor.

import React from 'react';
import DOMPurify from 'dompurify';
import { Button } from '../../../components/common';
import { RichTextEditor } from '../../../components/common/RichTextEditor';
import {
  PencilIcon,
  CheckIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline';
import type { Module } from './types';
import type { CourseEditorState } from './useCourseEditor';

interface ModuleDescriptionProps {
  state: CourseEditorState;
  module: Module;
}

export const ModuleDescription: React.FC<ModuleDescriptionProps> = ({ state, module }) => {
  const {
    editorMode,
    handleEditorModeChange,
    handleModeWarning,
    uploadEditorImage,
    editingModuleDescriptionId,
    moduleDescriptionDrafts,
    setModuleDescriptionDrafts,
    startModuleDescriptionEdit,
    saveModuleDescription,
    cancelModuleDescriptionEdit,
    updateModuleMutation,
  } = state;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h4 className="text-sm font-semibold text-gray-900">Module Description</h4>
        <div className="flex items-center gap-2">
          {editingModuleDescriptionId === module.id ? (
            <>
              <Button variant="outline" size="sm" onClick={() => cancelModuleDescriptionEdit(module.id)}>
                <XMarkIcon className="mr-1 h-4 w-4" />Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => saveModuleDescription(module.id)}
                loading={updateModuleMutation.isPending}
              >
                <CheckIcon className="mr-1 h-4 w-4" />Save
              </Button>
            </>
          ) : (
            <Button variant="outline" size="sm" onClick={() => startModuleDescriptionEdit(module)}>
              <PencilIcon className="mr-1 h-4 w-4" />Edit
            </Button>
          )}
        </div>
      </div>

      {editingModuleDescriptionId === module.id ? (
        <RichTextEditor
          value={moduleDescriptionDrafts[module.id] || ''}
          onChange={(html) => setModuleDescriptionDrafts((prev) => ({ ...prev, [module.id]: html }))}
          mode={editorMode}
          onModeChange={handleEditorModeChange}
          onImageUpload={uploadEditorImage}
          onModeWarning={handleModeWarning}
          placeholder="Add context, links, and key points that appear before lessons."
          minHeightClassName="min-h-[180px]"
        />
      ) : (
        <div className="rounded-md bg-gray-50 p-3">
          {module.description ? (
            <div
              className="prose prose-sm max-w-none text-gray-700"
              dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(module.description) }}
            />
          ) : (
            <p className="text-sm text-gray-500">Optional module summary (shown above lesson items).</p>
          )}
        </div>
      )}
    </div>
  );
};
