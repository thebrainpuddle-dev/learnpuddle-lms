// src/pages/admin/CourseEditorPage.tsx
//
// Thin orchestrator that composes the Course Editor sub-components.
// State is centralized in the useCourseEditor hook and passed down via props.
//
// Integrations:
//   - AIGenerationPanel: unified AI content generation
//   - FilePicker: browse existing media uploads

import React, { useState, useCallback, useEffect } from 'react';
import { Loading, ConfirmDialog } from '../../components/common';
import { Button } from '../../components/common';
import { XMarkIcon } from '@heroicons/react/24/outline';
import type { EditorTab, TextEditorMode } from './course-editor/types';
import {
  useCourseEditor,
  CourseEditorHeader,
  CourseBasicInfo,
  CourseModuleList,
  CourseSettings,
} from './course-editor';
import { AIGenerationPanel } from '../../components/courses/AIGenerationPanel';
import { FilePicker } from '../../components/courses/FilePicker';
import type { MediaAsset } from '../../services/adminMediaService';
import { useQueryClient } from '@tanstack/react-query';
import { useLocation } from 'react-router-dom';
import {
  RevisionHistoryPanel,
  useRevisionCount,
} from '../../components/versioning/RevisionHistoryPanel';
import { ContentPreviewModal } from './course-editor/ContentPreviewModal';
import { MediaLibraryModal } from './course-editor/MediaLibraryModal';
import type { Content } from './course-editor/types';

export const CourseEditorPage: React.FC = () => {
  const state = useCourseEditor();
  const {
    courseId,
    isEditing,
    canManageAssignments,
    courseLoading,
    activeTab,
    setActiveTab,
    // Editor chooser
    editorMode,
    setEditorMode,
    showEditorChooser,
    setShowEditorChooser,
    rememberEditorMode,
    setRememberEditorMode,
    handleSaveEditorChoice,
    // Course data
    course,
    // Preview
    previewContent,
    setPreviewContent,
    // Confirm delete
    confirmDelete,
    setConfirmDelete,
    // Content data for library pick
    setNewContentData,
    setContentFile,
    setShowNewTextPreview,
    // Delete mutations
    deleteModuleMutation,
    deleteContentMutation,
    // Toast
    toast,
  } = state;

  const queryClient = useQueryClient();
  const revisionCount = useRevisionCount('course', courseId);
  const [filePickerOpen, setFilePickerOpen] = useState(false);
  const { hash } = useLocation();

  // Scroll to #module-{id} or #content-{id} anchors emitted by SearchPage navigation
  useEffect(() => {
    if (!hash) return;
    const id = hash.slice(1);
    // Wait one tick so DOM elements with matching id are mounted
    const timer = setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 300);
    return () => clearTimeout(timer);
  }, [hash]);

  const handleContentAdded = useCallback(() => {
    if (courseId) queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
  }, [courseId, queryClient]);

  const handleFilePickerSelect = useCallback(
    (asset: MediaAsset) => {
      setNewContentData((prev) => ({
        ...prev,
        content_type: asset.media_type as Content['content_type'],
        title: prev.title || asset.title,
        file_url: asset.file_url,
      }));
      setContentFile(null);
      setShowNewTextPreview(false);
      toast.success('Selected', `"${asset.title}" selected from library.`);
    },
    [setNewContentData, setContentFile, setShowNewTextPreview, toast],
  );

  if (courseLoading && isEditing) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loading />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <CourseEditorHeader state={state} />

      {/* Editor Mode Chooser Modal */}
      {showEditorChooser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-3xl rounded-2xl bg-white p-6 shadow-xl">
            <div className="mb-5 flex items-start justify-between">
              <div>
                <h2 className="text-2xl font-semibold text-gray-900">Choose your text editor</h2>
                <p className="mt-1 text-sm text-gray-500">This choice can be saved to your profile.</p>
              </div>
              <button
                onClick={() => setShowEditorChooser(false)}
                className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
                aria-label="Close chooser"
              >
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {([
                { key: 'WYSIWYG' as TextEditorMode, title: 'WYSIWYG', description: 'Format text visually with toolbar controls and embedded media.' },
                { key: 'MARKDOWN' as TextEditorMode, title: 'Markdown', description: 'Write with markdown syntax while keeping rich output support.' },
              ]).map((choice) => (
                <button
                  key={choice.key}
                  onClick={() => setEditorMode(choice.key)}
                  className={`rounded-xl border p-5 text-left transition-colors ${editorMode === choice.key ? 'border-primary-500 bg-primary-50' : 'border-gray-200 hover:border-gray-300'}`}
                >
                  <p className="text-lg font-semibold text-gray-900">{choice.title}</p>
                  <p className="mt-2 text-sm text-gray-600">{choice.description}</p>
                </button>
              ))}
            </div>

            <label className="mt-5 flex items-center text-sm text-gray-700">
              <input
                type="checkbox"
                checked={rememberEditorMode}
                onChange={(e) => setRememberEditorMode(e.target.checked)}
                className="mr-2 h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              Remember my preference
            </label>

            <div className="mt-6 flex justify-end">
              <Button variant="primary" onClick={() => void handleSaveEditorChoice()}>Save</Button>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav data-tour="admin-course-editor-tabs" className="-mb-px flex gap-6 overflow-x-auto">
          {[
            { key: 'details', label: 'Details' },
            { key: 'content', label: 'Content', disabled: !isEditing },
            { key: 'ai', label: 'AI Content', disabled: !isEditing },
            { key: 'audience', label: 'Course Audience', disabled: !isEditing },
            { key: 'history', label: revisionCount > 0 ? `History (${revisionCount > 99 ? '99+' : revisionCount})` : 'History', disabled: !isEditing },
          ].map((tab) => (
            <button
              type="button"
              key={tab.key}
              data-tour={`admin-course-editor-tab-${tab.key}`}
              onClick={() => !tab.disabled && setActiveTab(tab.key as EditorTab)}
              disabled={tab.disabled}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors whitespace-nowrap ${
                activeTab === tab.key
                  ? 'border-primary-500 text-primary-600'
                  : tab.disabled
                  ? 'border-transparent text-gray-300 cursor-not-allowed'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.label}{tab.disabled && ' (save first)'}
            </button>
          ))}
        </nav>
      </div>

      {activeTab === 'details' && <CourseBasicInfo state={state} />}
      {activeTab === 'content' && isEditing && <CourseModuleList state={state} />}
      {activeTab === 'ai' && isEditing && courseId && (
        <AIGenerationPanel
          courseId={courseId}
          modules={(course?.modules ?? []).map((m) => ({ id: m.id, title: m.title, order: m.order }))}
          onContentAdded={handleContentAdded}
        />
      )}
      {activeTab === 'audience' && isEditing && canManageAssignments && <CourseSettings state={state} />}
      {activeTab === 'history' && isEditing && courseId && (
        <div className="bg-white rounded-xl border border-gray-200 p-4">
          <RevisionHistoryPanel kind="course" objectId={courseId} onRestored={handleContentAdded} />
        </div>
      )}

      {/* Content Preview Modal */}
      {previewContent && <ContentPreviewModal content={previewContent} onClose={() => setPreviewContent(null)} />}

      {/* Media Library Modal (legacy inline version) */}
      <MediaLibraryModal state={state} />

      {/* FilePicker Modal (extracted component) */}
      <FilePicker isOpen={filePickerOpen} onClose={() => setFilePickerOpen(false)} onSelect={handleFilePickerSelect} />

      {/* Delete confirmation dialog */}
      <ConfirmDialog
        isOpen={!!confirmDelete}
        onClose={() => setConfirmDelete(null)}
        onConfirm={() => {
          if (!confirmDelete) return;
          if (confirmDelete.type === 'module') {
            deleteModuleMutation.mutate({ courseId: courseId!, moduleId: confirmDelete.moduleId });
          } else if (confirmDelete.contentId) {
            deleteContentMutation.mutate({ courseId: courseId!, moduleId: confirmDelete.moduleId, contentId: confirmDelete.contentId });
          }
        }}
        title={confirmDelete?.type === 'module' ? 'Delete Module' : 'Delete Content'}
        message={
          confirmDelete?.type === 'module'
            ? `Are you sure you want to delete "${confirmDelete.label}" and all its content? This cannot be undone.`
            : `Are you sure you want to delete "${confirmDelete?.label}"? This cannot be undone.`
        }
        confirmLabel="Delete"
        variant="danger"
      />
    </div>
  );
};
