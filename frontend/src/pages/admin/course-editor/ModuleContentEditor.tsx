// course-editor/ModuleContentEditor.tsx
//
// Content editing within a single module: module description, content items,
// text editing, file/video upload, and media library picker integration.

import React from 'react';
import DOMPurify from 'dompurify';
import { Button } from '../../../components/common';
import { RichTextEditor } from '../../../components/common/RichTextEditor';
import {
  PlusIcon,
  PencilIcon,
  TrashIcon,
  CheckIcon,
  XMarkIcon,
  EyeIcon,
  PlayCircleIcon,
  DocumentTextIcon,
  LinkIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';
import type { Module, Content } from './types';
import type { CourseEditorState } from './useCourseEditor';

interface ModuleContentEditorProps {
  state: CourseEditorState;
  module: Module;
  moduleIndex: number;
}

export const getContentIcon = (type: Content['content_type']) => {
  switch (type) {
    case 'VIDEO':
      return <PlayCircleIcon className="h-5 w-5 text-blue-500" />;
    case 'DOCUMENT':
      return <DocumentTextIcon className="h-5 w-5 text-orange-500" />;
    case 'LINK':
      return <LinkIcon className="h-5 w-5 text-purple-500" />;
    case 'AI_CLASSROOM':
      return <PlayCircleIcon className="h-5 w-5 text-indigo-500" />;
    case 'CHATBOT':
      return <DocumentTextIcon className="h-5 w-5 text-emerald-500" />;
    default:
      return <DocumentTextIcon className="h-5 w-5 text-gray-500" />;
  }
};

export const ModuleContentEditor: React.FC<ModuleContentEditorProps> = ({
  state,
  module,
  moduleIndex,
}) => {
  const {
    courseId,
    canUploadVideo,
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
    editingTextContentId,
    editingTextModuleId,
    textContentDraft,
    setTextContentDraft,
    showEditingTextPreview,
    setShowEditingTextPreview,
    showNewTextPreview,
    setShowNewTextPreview,
    startTextContentEdit,
    saveTextContent,
    cancelTextContentEdit,
    updateContentMutation,
    addingContentToModule,
    setAddingContentToModule,
    newContentData,
    setNewContentData,
    contentFile,
    setContentFile,
    contentFileInputRef,
    contentMutation,
    handleAddContent,
    setConfirmDelete,
    setPreviewContent,
    uploadPhase,
    setUploadPhase,
    uploadProgress,
    toast,
  } = state;

  return (
    <div className="p-4 space-y-3">
      {/* Module Description */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <div className="mb-3 flex items-center justify-between">
          <h4 className="text-sm font-semibold text-gray-900">
            Module Description
          </h4>
          <div className="flex items-center gap-2">
            {editingModuleDescriptionId === module.id ? (
              <>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    cancelModuleDescriptionEdit(module.id)
                  }
                >
                  <XMarkIcon className="mr-1 h-4 w-4" />
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => saveModuleDescription(module.id)}
                  loading={updateModuleMutation.isPending}
                >
                  <CheckIcon className="mr-1 h-4 w-4" />
                  Save
                </Button>
              </>
            ) : (
              <Button
                variant="outline"
                size="sm"
                onClick={() => startModuleDescriptionEdit(module)}
              >
                <PencilIcon className="mr-1 h-4 w-4" />
                Edit
              </Button>
            )}
          </div>
        </div>

        {editingModuleDescriptionId === module.id ? (
          <RichTextEditor
            value={moduleDescriptionDrafts[module.id] || ''}
            onChange={(html) =>
              setModuleDescriptionDrafts((prev) => ({
                ...prev,
                [module.id]: html,
              }))
            }
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
                dangerouslySetInnerHTML={{
                  __html: DOMPurify.sanitize(module.description),
                }}
              />
            ) : (
              <p className="text-sm text-gray-500">
                Optional module summary (shown above lesson items).
              </p>
            )}
          </div>
        )}
      </div>

      {/* Content Items */}
      {module.contents?.map((content) => {
        const isEditingText =
          editingTextContentId === content.id &&
          editingTextModuleId === module.id;

        if (isEditingText && content.content_type === 'TEXT') {
          return (
            <div
              key={content.id}
              className="rounded-lg border border-blue-200 bg-blue-50 p-4"
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-medium text-blue-900">
                  Editing text lesson: {content.title}
                </span>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setShowEditingTextPreview((prev) => !prev)
                    }
                  >
                    <EyeIcon className="mr-1 h-4 w-4" />
                    {showEditingTextPreview
                      ? 'Back to Editor'
                      : 'Preview'}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={cancelTextContentEdit}
                  >
                    <XMarkIcon className="mr-1 h-4 w-4" />
                    Cancel
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={saveTextContent}
                    loading={updateContentMutation.isPending}
                  >
                    <CheckIcon className="mr-1 h-4 w-4" />
                    Save Text
                  </Button>
                </div>
              </div>
              <p className="mb-2 text-xs text-blue-700">
                Use the toolbar to add links, images, and indentation for
                clean lesson content.
              </p>
              {showEditingTextPreview ? (
                <div className="rounded-md border border-blue-100 bg-white p-3">
                  {textContentDraft ? (
                    <div
                      className="prose prose-sm max-w-none text-gray-700"
                      dangerouslySetInnerHTML={{
                        __html: DOMPurify.sanitize(textContentDraft),
                      }}
                    />
                  ) : (
                    <p className="text-sm text-gray-500">
                      Nothing to preview yet.
                    </p>
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
          <div
            key={content.id}
            className="flex items-center justify-between rounded-lg bg-gray-50 p-3 transition-colors hover:bg-gray-100"
          >
            <div className="min-w-0 flex items-center">
              {getContentIcon(content.content_type)}
              <span className="ml-3 truncate text-sm text-gray-900">
                {content.title}
              </span>
              <span className="ml-2 flex-shrink-0 text-xs uppercase text-gray-500">
                {content.content_type}
              </span>
              {content.content_type === 'VIDEO' &&
                content.video_status &&
                (content.video_status === 'READY' ? (
                  <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                    <CheckCircleIcon className="h-3 w-3" /> Ready
                  </span>
                ) : content.video_status === 'FAILED' ? (
                  <span
                    className="ml-2 inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-xs font-medium text-red-700"
                    title="Processing failed"
                  >
                    <ExclamationCircleIcon className="h-3 w-3" /> Failed
                  </span>
                ) : (
                  <span className="ml-2 inline-flex animate-pulse items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700">
                    <ArrowPathIcon className="h-3 w-3 animate-spin" />{' '}
                    Processing
                  </span>
                ))}
            </div>
            <div className="flex flex-shrink-0 items-center space-x-1">
              {content.content_type === 'TEXT' && (
                <button
                  type="button"
                  onClick={() =>
                    startTextContentEdit(module.id, content)
                  }
                  className="rounded p-1 text-gray-400 hover:text-primary-600"
                  title="Edit text"
                >
                  <PencilIcon className="h-4 w-4" />
                </button>
              )}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setPreviewContent(content);
                }}
                className="rounded p-1 text-gray-400 hover:text-primary-600"
                title="Preview"
              >
                <EyeIcon className="h-4 w-4" />
              </button>
              <button
                onClick={() =>
                  setConfirmDelete({
                    type: 'content',
                    moduleId: module.id,
                    contentId: content.id,
                    label: content.title || 'this content',
                  })
                }
                className="rounded p-1 text-gray-400 hover:text-red-600"
              >
                <TrashIcon className="h-4 w-4" />
              </button>
            </div>
          </div>
        );
      })}

      {/* Add Content Form */}
      {addingContentToModule === module.id ? (
        <div className="p-4 bg-blue-50 rounded-lg space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <label
              htmlFor={`new-content-title-${module.id}`}
              className="sr-only"
            >
              Content title
            </label>
            <input
              id={`new-content-title-${module.id}`}
              name="new_content_title"
              type="text"
              value={newContentData.title}
              onChange={(e) =>
                setNewContentData((prev) => ({
                  ...prev,
                  title: e.target.value,
                }))
              }
              placeholder="Content title"
              className="px-3 py-2 border border-gray-300 rounded-lg"
            />
            <label
              htmlFor={`new-content-type-${module.id}`}
              className="sr-only"
            >
              Content type
            </label>
            <select
              id={`new-content-type-${module.id}`}
              name="new_content_type"
              value={newContentData.content_type}
              onChange={(e) => {
                const newType = e.target.value as Content['content_type'];
                setNewContentData((prev) => ({
                  ...prev,
                  content_type: newType,
                  file_url: '',
                  text_content:
                    newType === 'TEXT' ? prev.text_content : '',
                }));
                setContentFile(null);
                setShowNewTextPreview(false);
              }}
              className="px-3 py-2 border border-gray-300 rounded-lg"
            >
              <option value="VIDEO" disabled={!canUploadVideo}>
                Video{!canUploadVideo ? ' (Upgrade)' : ''}
              </option>
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
                <p className="text-xs text-blue-700">
                  Add rich text with links, images, and formatting. Use
                  preview before saving.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    setShowNewTextPreview((prev) => !prev)
                  }
                >
                  <EyeIcon className="mr-1 h-4 w-4" />
                  {showNewTextPreview
                    ? 'Back to Editor'
                    : 'Preview'}
                </Button>
              </div>
              {showNewTextPreview ? (
                <div className="rounded-md border border-gray-200 bg-white p-3">
                  {newContentData.text_content ? (
                    <div
                      className="prose prose-sm max-w-none text-gray-700"
                      dangerouslySetInnerHTML={{
                        __html: DOMPurify.sanitize(
                          newContentData.text_content,
                        ),
                      }}
                    />
                  ) : (
                    <p className="text-sm text-gray-500">
                      Nothing to preview yet.
                    </p>
                  )}
                </div>
              ) : (
                <RichTextEditor
                  value={newContentData.text_content}
                  onChange={(html) =>
                    setNewContentData((prev) => ({
                      ...prev,
                      text_content: html,
                    }))
                  }
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
              <label
                htmlFor={`new-content-link-${module.id}`}
                className="sr-only"
              >
                Link URL
              </label>
              <input
                id={`new-content-link-${module.id}`}
                name="new_content_link"
                type="url"
                value={newContentData.file_url}
                onChange={(e) =>
                  setNewContentData((prev) => ({
                    ...prev,
                    file_url: e.target.value,
                  }))
                }
                placeholder="https://..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              />
            </>
          )}

          {(newContentData.content_type === 'VIDEO' ||
            newContentData.content_type === 'DOCUMENT') && (
            <div className="flex items-center gap-2">
              <input
                ref={contentFileInputRef}
                id={`module-content-file-${module.id}`}
                name="module_content_file"
                type="file"
                accept={
                  newContentData.content_type === 'VIDEO'
                    ? 'video/*'
                    : '.pdf,.doc,.docx,.ppt,.pptx'
                }
                onChange={(e) =>
                  setContentFile(e.target.files?.[0] || null)
                }
                className="hidden"
              />
              <Button
                variant="outline"
                size="sm"
                onClick={() => contentFileInputRef.current?.click()}
              >
                {contentFile ? contentFile.name : 'Choose File'}
              </Button>
            </div>
          )}


          {/* Upload progress bar (video only) */}
          {uploadPhase !== 'idle' &&
            newContentData.content_type === 'VIDEO' && (
              <div className="space-y-2">
                {uploadPhase === 'uploading' && (
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-blue-700 font-medium">
                        Uploading video...
                      </span>
                      <span className="text-blue-600">
                        {uploadProgress}%
                      </span>
                    </div>
                    <div className="h-2 bg-blue-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-600 rounded-full transition-all"
                        style={{ width: `${uploadProgress}%` }}
                      />
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
                    <CheckCircleIcon className="h-4 w-4" />
                    Video ready!
                  </div>
                )}
              </div>
            )}

          <div className="flex justify-end space-x-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setAddingContentToModule(null);
                setContentFile(null);
                setUploadPhase('idle');
                setShowNewTextPreview(false);
              }}
              disabled={
                uploadPhase === 'uploading' ||
                uploadPhase === 'processing'
              }
            >
              <XMarkIcon className="h-4 w-4 mr-1" />
              Cancel
            </Button>
            <Button
              variant="primary"
              size="sm"
              onClick={() => handleAddContent(module.id)}
              loading={
                contentMutation.isPending ||
                uploadPhase === 'uploading'
              }
              disabled={
                !newContentData.title.trim() ||
                uploadPhase === 'uploading' ||
                uploadPhase === 'processing'
              }
            >
              <CheckIcon className="h-4 w-4 mr-1" />
              {uploadPhase === 'uploading'
                ? `Uploading ${uploadProgress}%`
                : 'Add'}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <button
            onClick={() => {
              setAddingContentToModule(module.id);
              setShowNewTextPreview(false);
            }}
            className="flex-1 flex items-center justify-center p-3 border-2 border-dashed border-gray-300 rounded-lg text-gray-500 hover:border-primary-500 hover:text-primary-600 transition-colors"
          >
            <PlusIcon className="h-5 w-5 mr-2" />
            Add Content
          </button>
          {/* AI Studio functionality is now available via AIGenerationPanel in the course editor */}
        </div>
      )}
    </div>
  );
};
