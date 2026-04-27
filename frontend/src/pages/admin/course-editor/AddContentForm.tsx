// course-editor/AddContentForm.tsx
//
// The "Add Content" form (shown when addingContentToModule === module.id)
// and the dashed "Add Content" trigger button. Extracted from ModuleContentEditor.

import React from 'react';
import DOMPurify from 'dompurify';
import { Button } from '../../../components/common';
import { RichTextEditor } from '../../../components/common/RichTextEditor';
import {
  PlusIcon,
  CheckIcon,
  XMarkIcon,
  EyeIcon,
  ArrowPathIcon,
  CheckCircleIcon,
} from '@heroicons/react/24/outline';
import type { Content, Module } from './types';
import type { CourseEditorState } from './useCourseEditor';

interface AddContentFormProps {
  state: CourseEditorState;
  module: Module;
}

export const AddContentForm: React.FC<AddContentFormProps> = ({ state, module }) => {
  const {
    canUploadVideo,
    editorMode,
    handleEditorModeChange,
    handleModeWarning,
    uploadEditorImage,
    addingContentToModule,
    setAddingContentToModule,
    newContentData,
    setNewContentData,
    contentFile,
    setContentFile,
    contentFileInputRef,
    contentMutation,
    handleAddContent,
    uploadPhase,
    setUploadPhase,
    uploadProgress,
    showNewTextPreview,
    setShowNewTextPreview,
  } = state;

  if (addingContentToModule !== module.id) {
    return (
      <div className="flex gap-2">
        <button
          onClick={() => { setAddingContentToModule(module.id); setShowNewTextPreview(false); }}
          className="flex-1 flex items-center justify-center p-3 border-2 border-dashed border-gray-300 rounded-lg text-gray-500 hover:border-primary-500 hover:text-primary-600 transition-colors"
        >
          <PlusIcon className="h-5 w-5 mr-2" />
          Add Content
        </button>
      </div>
    );
  }

  return (
    <div className="p-4 bg-blue-50 rounded-lg space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <label htmlFor={`new-content-title-${module.id}`} className="sr-only">Content title</label>
        <input
          id={`new-content-title-${module.id}`}
          name="new_content_title"
          type="text"
          value={newContentData.title}
          onChange={(e) => setNewContentData((prev) => ({ ...prev, title: e.target.value }))}
          placeholder="Content title"
          className="px-3 py-2 border border-gray-300 rounded-lg"
        />
        <label htmlFor={`new-content-type-${module.id}`} className="sr-only">Content type</label>
        <select
          id={`new-content-type-${module.id}`}
          name="new_content_type"
          value={newContentData.content_type}
          onChange={(e) => {
            const newType = e.target.value as Content['content_type'];
            setNewContentData((prev) => ({ ...prev, content_type: newType, file_url: '', text_content: newType === 'TEXT' ? prev.text_content : '' }));
            setContentFile(null);
            setShowNewTextPreview(false);
          }}
          className="px-3 py-2 border border-gray-300 rounded-lg"
        >
          <option value="VIDEO" disabled={!canUploadVideo}>Video{!canUploadVideo ? ' (Upgrade)' : ''}</option>
          <option value="DOCUMENT">Document</option>
          <option value="TEXT">Text</option>
          <option value="LINK">Link</option>
          <option value="AI_CLASSROOM">AI Classroom</option>
          <option value="CHATBOT">AI Tutor</option>
        </select>
      </div>

      {newContentData.content_type === 'TEXT' && (
        <>
          <div className="flex items-center justify-between">
            <p className="text-xs text-blue-700">Add rich text with links, images, and formatting. Use preview before saving.</p>
            <Button variant="outline" size="sm" onClick={() => setShowNewTextPreview((prev) => !prev)}>
              <EyeIcon className="mr-1 h-4 w-4" />
              {showNewTextPreview ? 'Back to Editor' : 'Preview'}
            </Button>
          </div>
          {showNewTextPreview ? (
            <div className="rounded-md border border-gray-200 bg-white p-3">
              {newContentData.text_content ? (
                <div className="prose prose-sm max-w-none text-gray-700" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(newContentData.text_content) }} />
              ) : (
                <p className="text-sm text-gray-500">Nothing to preview yet.</p>
              )}
            </div>
          ) : (
            <RichTextEditor
              value={newContentData.text_content}
              onChange={(html) => setNewContentData((prev) => ({ ...prev, text_content: html }))}
              mode={editorMode}
              onModeChange={handleEditorModeChange}
              onImageUpload={uploadEditorImage}
              onModeWarning={handleModeWarning}
              placeholder="Start writing module intro, links, notes, or pasted code..."
              minHeightClassName="min-h-[160px]"
            />
          )}
        </>
      )}

      {newContentData.content_type === 'LINK' && (
        <>
          <label htmlFor={`new-content-link-${module.id}`} className="sr-only">Link URL</label>
          <input
            id={`new-content-link-${module.id}`}
            name="new_content_link"
            type="url"
            value={newContentData.file_url}
            onChange={(e) => setNewContentData((prev) => ({ ...prev, file_url: e.target.value }))}
            placeholder="https://..."
            className="w-full px-3 py-2 border border-gray-300 rounded-lg"
          />
        </>
      )}

      {(newContentData.content_type === 'VIDEO' || newContentData.content_type === 'DOCUMENT') && (
        <div className="flex items-center gap-2">
          <input
            ref={contentFileInputRef}
            id={`module-content-file-${module.id}`}
            name="module_content_file"
            type="file"
            accept={newContentData.content_type === 'VIDEO' ? 'video/*' : '.pdf,.doc,.docx,.ppt,.pptx'}
            onChange={(e) => setContentFile(e.target.files?.[0] || null)}
            className="hidden"
          />
          <Button variant="outline" size="sm" onClick={() => contentFileInputRef.current?.click()}>
            {contentFile ? contentFile.name : 'Choose File'}
          </Button>
        </div>
      )}

      {/* Upload progress bar (video only) */}
      {uploadPhase !== 'idle' && newContentData.content_type === 'VIDEO' && (
        <div className="space-y-2">
          {uploadPhase === 'uploading' && (
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-blue-700 font-medium">Uploading video...</span>
                <span className="text-blue-600">{uploadProgress}%</span>
              </div>
              <div className="h-2 bg-blue-100 rounded-full overflow-hidden">
                <div className="h-full bg-blue-600 rounded-full transition-all" style={{ width: `${uploadProgress}%` }} />
              </div>
            </div>
          )}
          {uploadPhase === 'processing' && (
            <div className="flex items-center gap-2 text-amber-700 text-sm font-medium">
              <ArrowPathIcon className="h-4 w-4 animate-spin" />
              Processing video (HLS, transcript, assignments)...
            </div>
          )}
          {uploadPhase === 'done' && (
            <div className="flex items-center gap-2 text-emerald-700 text-sm font-medium">
              <CheckCircleIcon className="h-4 w-4" />Video ready!
            </div>
          )}
        </div>
      )}

      <div className="flex justify-end space-x-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => { setAddingContentToModule(null); setContentFile(null); setUploadPhase('idle'); setShowNewTextPreview(false); }}
          disabled={uploadPhase === 'uploading' || uploadPhase === 'processing'}
        >
          <XMarkIcon className="h-4 w-4 mr-1" />Cancel
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={() => handleAddContent(module.id)}
          loading={contentMutation.isPending || uploadPhase === 'uploading'}
          disabled={!newContentData.title.trim() || uploadPhase === 'uploading' || uploadPhase === 'processing'}
        >
          <CheckIcon className="h-4 w-4 mr-1" />
          {uploadPhase === 'uploading' ? `Uploading ${uploadProgress}%` : 'Add'}
        </Button>
      </div>
    </div>
  );
};

