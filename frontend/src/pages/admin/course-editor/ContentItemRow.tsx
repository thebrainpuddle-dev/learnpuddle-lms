// course-editor/ContentItemRow.tsx
//
// Renders a single content item row (display or text edit mode)
// within ModuleContentEditor.

import React from 'react';
import DOMPurify from 'dompurify';
import { Button } from '../../../components/common';
import { RichTextEditor } from '../../../components/common/RichTextEditor';
import {
  PencilIcon,
  TrashIcon,
  CheckIcon,
  XMarkIcon,
  EyeIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import type { Content, Module } from './types';
import type { CourseEditorState } from './useCourseEditor';
import { getContentIcon } from './contentUtils';

interface ContentItemRowProps {
  state: CourseEditorState;
  module: Module;
  content: Content;
}

export const ContentItemRow: React.FC<ContentItemRowProps> = ({ state, module, content }) => {
  const {
    editorMode,
    handleEditorModeChange,
    handleModeWarning,
    uploadEditorImage,
    editingTextContentId,
    editingTextModuleId,
    textContentDraft,
    setTextContentDraft,
    showEditingTextPreview,
    setShowEditingTextPreview,
    startTextContentEdit,
    saveTextContent,
    cancelTextContentEdit,
    updateContentMutation,
    setPreviewContent,
    setConfirmDelete,
  } = state;

  const isEditingText = editingTextContentId === content.id && editingTextModuleId === module.id;

  if (isEditingText && content.content_type === 'TEXT') {
    return (
      <div id={`content-${content.id}`} className="rounded-lg border border-blue-200 bg-blue-50 p-4">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium text-blue-900">Editing text lesson: {content.title}</span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setShowEditingTextPreview((prev) => !prev)}>
              <EyeIcon className="mr-1 h-4 w-4" />
              {showEditingTextPreview ? 'Back to Editor' : 'Preview'}
            </Button>
            <Button variant="outline" size="sm" onClick={cancelTextContentEdit}>
              <XMarkIcon className="mr-1 h-4 w-4" />Cancel
            </Button>
            <Button variant="primary" size="sm" onClick={saveTextContent} loading={updateContentMutation.isPending}>
              <CheckIcon className="mr-1 h-4 w-4" />Save Text
            </Button>
          </div>
        </div>
        <p className="mb-2 text-xs text-blue-700">
          Use the toolbar to add links, images, and indentation for clean lesson content.
        </p>
        {showEditingTextPreview ? (
          <div className="rounded-md border border-blue-100 bg-white p-3">
            {textContentDraft ? (
              <div className="prose prose-sm max-w-none text-gray-700" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(textContentDraft) }} />
            ) : (
              <p className="text-sm text-gray-500">Nothing to preview yet.</p>
            )}
          </div>
        ) : (
          <RichTextEditor
            value={textContentDraft}
            onChange={setTextContentDraft}
            mode={editorMode}
            onModeChange={handleEditorModeChange}
            onImageUpload={uploadEditorImage}
            onModeWarning={handleModeWarning}
            placeholder="Write module intro, links, and supporting context..."
            minHeightClassName="min-h-[180px]"
          />
        )}
      </div>
    );
  }

  return (
    <div id={`content-${content.id}`} className="flex items-center justify-between rounded-lg bg-gray-50 p-3 transition-colors hover:bg-gray-100">
      <div className="min-w-0 flex items-center">
        {getContentIcon(content.content_type)}
        <span className="ml-3 truncate text-sm text-gray-900">{content.title}</span>
        <span className="ml-2 flex-shrink-0 text-xs uppercase text-gray-500">{content.content_type}</span>
        {content.content_type === 'VIDEO' && content.video_status && (
          content.video_status === 'READY' ? (
            <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
              <CheckCircleIcon className="h-3 w-3" /> Ready
            </span>
          ) : content.video_status === 'FAILED' ? (
            <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700" title="Processing failed">
              <ExclamationCircleIcon className="h-3 w-3" /> Failed
            </span>
          ) : (
            <span className="ml-2 inline-flex animate-pulse items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
              <ArrowPathIcon className="h-3 w-3 animate-spin" /> Processing
            </span>
          )
        )}
      </div>
      <div className="flex flex-shrink-0 items-center space-x-1">
        {content.content_type === 'TEXT' && (
          <button type="button" onClick={() => startTextContentEdit(module.id, content)} className="rounded p-1 text-gray-400 hover:text-primary-600" title="Edit text">
            <PencilIcon className="h-4 w-4" />
          </button>
        )}
        <button type="button" onClick={(e) => { e.stopPropagation(); setPreviewContent(content); }} className="rounded p-1 text-gray-400 hover:text-primary-600" title="Preview">
          <EyeIcon className="h-4 w-4" />
        </button>
        <button
          onClick={() => setConfirmDelete({ type: 'content', moduleId: module.id, contentId: content.id, label: content.title || 'this content' })}
          className="rounded p-1 text-gray-400 hover:text-red-600"
        >
          <TrashIcon className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
};
