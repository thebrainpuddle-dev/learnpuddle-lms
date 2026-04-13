// src/pages/admin/CourseEditorPage.tsx
//
// Thin orchestrator that composes the Course Editor sub-components.
// State is centralized in the useCourseEditor hook and passed down via props.
//
// Integrations:
//   - AIGenerationPanel: unified AI content generation
//   - FilePicker: browse existing media uploads

import React, { useState, useCallback } from 'react';
import DOMPurify from 'dompurify';
import { Loading, ConfirmDialog, HlsVideoPlayer } from '../../components/common';
import { Button } from '../../components/common';
import {
  PlayCircleIcon,
  DocumentTextIcon,
  LinkIcon,
  XMarkIcon,
  ArrowPathIcon,
  ExclamationCircleIcon,
  FolderIcon,
  MagnifyingGlassIcon,
} from '@heroicons/react/24/outline';
import type {
  EditorTab,
  TextEditorMode,
  Content,
} from './course-editor/types';
import {
  useCourseEditor,
  CourseEditorHeader,
  CourseBasicInfo,
  CourseModuleList,
  CourseSettings,
  getContentIcon,
} from './course-editor';
import { AIGenerationPanel } from '../../components/courses/AIGenerationPanel';
import { FilePicker } from '../../components/courses/FilePicker';
import type { MediaAsset } from '../../services/adminMediaService';
import { useQueryClient } from '@tanstack/react-query';

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
    // Media library (legacy inline picker — kept for backwards compat)
    libraryOpen,
    setLibraryOpen,
    librarySearch,
    setLibrarySearch,
    libraryFilter,
    setLibraryFilter,
    libraryAssets,
    fetchLibraryAssets,
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

  // ── Query client for course data invalidation ───────────────────────────

  const queryClient = useQueryClient();

  // ── FilePicker state for the extracted component ─────────────────────────

  const [filePickerOpen, setFilePickerOpen] = useState(false);

  // ── AI content added handler ──────────────────────────────────────────

  const handleContentAdded = useCallback(() => {
    if (courseId) {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
    }
  }, [courseId, queryClient]);

  // ── FilePicker selection handler ─────────────────────────────────────────

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
                {
                  key: 'WYSIWYG' as TextEditorMode,
                  title: 'WYSIWYG',
                  description: 'Format text visually with toolbar controls and embedded media.',
                },
                {
                  key: 'MARKDOWN' as TextEditorMode,
                  title: 'Markdown',
                  description: 'Write with markdown syntax while keeping rich output support.',
                },
              ]).map((choice) => (
                <button
                  key={choice.key}
                  onClick={() => setEditorMode(choice.key)}
                  className={`rounded-xl border p-5 text-left transition-colors ${
                    editorMode === choice.key
                      ? 'border-primary-500 bg-primary-50'
                      : 'border-gray-200 hover:border-gray-300'
                  }`}
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
              <Button variant="primary" onClick={() => void handleSaveEditorChoice()}>
                Save
              </Button>
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
          ].map((tab) => (
            <button
              type="button"
              key={tab.key}
              data-tour={
                tab.key === 'details'
                  ? 'admin-course-editor-tab-details'
                  : tab.key === 'content'
                  ? 'admin-course-editor-tab-content'
                  : tab.key === 'ai'
                  ? 'admin-course-editor-tab-ai'
                  : 'admin-course-editor-tab-audience'
              }
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
              {tab.label}
              {tab.disabled && ' (save first)'}
            </button>
          ))}
        </nav>
      </div>

      {/* Details Tab */}
      {activeTab === 'details' && <CourseBasicInfo state={state} />}

      {/* Content Tab */}
      {activeTab === 'content' && isEditing && <CourseModuleList state={state} />}

      {/* AI Generator Tab */}
      {activeTab === 'ai' && isEditing && courseId && (
        <AIGenerationPanel
          courseId={courseId}
          modules={(course?.modules ?? []).map((m) => ({ id: m.id, title: m.title, order: m.order }))}
          onContentAdded={handleContentAdded}
        />
      )}

      {/* Course Audience Tab */}
      {activeTab === 'audience' && isEditing && canManageAssignments && (
        <CourseSettings state={state} />
      )}

      {/* Content Preview Modal */}
      {previewContent && (() => {
        const backendOrigin = (process.env.REACT_APP_API_URL || `http://${window.location.hostname}:8000/api`).replace(/\/api\/?$/, '');
        const resolveUrl = (u: string | null) => {
          if (!u) return '';
          // In dev, rewrite absolute URLs to use the local backend origin
          // (stored URLs may point to port 80/nginx which isn't running locally)
          if (u.startsWith('http')) {
            try {
              const parsed = new URL(u);
              const path = parsed.pathname + parsed.search;
              return `${backendOrigin}${path}`;
            } catch {
              return u;
            }
          }
          return `${backendOrigin}${u.startsWith('/') ? '' : '/'}${u}`;
        };
        const c = previewContent;
        return (
          <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setPreviewContent(null)}>
            <div className="bg-white rounded-xl max-w-3xl w-full mx-4 max-h-[85vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
              <div className="flex items-center justify-between p-4 border-b border-gray-200">
                <div className="flex items-center gap-2">
                  {getContentIcon(c.content_type)}
                  <h3 className="text-lg font-semibold text-gray-900 truncate">{c.title}</h3>
                  <span className="text-xs text-gray-500 uppercase">{c.content_type}</span>
                </div>
                <button onClick={() => setPreviewContent(null)} className="p-1 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
                  <XMarkIcon className="h-5 w-5" />
                </button>
              </div>
              <div className="p-6 overflow-y-auto flex-1">
                {c.content_type === 'VIDEO' ? (
                  c.video_status === 'READY' && c.file_url ? (
                    <HlsVideoPlayer src={resolveUrl(c.file_url)} className="w-full rounded-lg bg-black aspect-video" />
                  ) : c.video_status === 'PROCESSING' ? (
                    <div className="flex flex-col items-center justify-center py-16 text-amber-600">
                      <ArrowPathIcon className="h-12 w-12 animate-spin mb-3" />
                      <p className="font-medium">Video is still processing...</p>
                      <p className="text-sm text-gray-500 mt-1">HLS transcoding, transcript, and assignments are being generated.</p>
                    </div>
                  ) : c.video_status === 'FAILED' ? (
                    <div className="flex flex-col items-center justify-center py-16 text-red-600">
                      <ExclamationCircleIcon className="h-12 w-12 mb-3" />
                      <p className="font-medium">Video processing failed</p>
                      <p className="text-sm text-gray-500 mt-1">Try re-uploading the video.</p>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center py-16 text-gray-400">
                      <PlayCircleIcon className="h-12 w-12 mb-3" />
                      <p className="text-sm">Video uploaded, waiting for processing...</p>
                    </div>
                  )
                ) : c.content_type === 'DOCUMENT' ? (
                  c.file_url ? (
                    <div className="flex flex-col items-center justify-center py-16 space-y-3">
                      <DocumentTextIcon className="h-12 w-12 text-orange-400" />
                      <p className="font-medium text-gray-900">{c.title}</p>
                      <a href={c.file_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700">
                        Open document in new tab
                      </a>
                    </div>
                  ) : (
                    <p className="text-gray-400 text-center py-8">No file uploaded</p>
                  )
                ) : c.content_type === 'LINK' ? (
                  c.file_url ? (
                    <div className="flex flex-col items-center justify-center py-16 space-y-4">
                      <div className="w-20 h-20 bg-gradient-to-br from-purple-50 to-purple-100 rounded-full flex items-center justify-center shadow-sm border border-purple-200">
                        <LinkIcon className="h-10 w-10 text-purple-500" />
                      </div>
                      <p className="font-medium text-gray-900">{c.title}</p>
                      <p className="text-sm text-gray-500 break-all max-w-md text-center">{c.file_url}</p>
                      <a
                        href={c.file_url.startsWith('http') ? c.file_url : `https://${c.file_url}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700"
                      >
                        Open link in new tab
                      </a>
                    </div>
                  ) : (
                    <p className="text-gray-400 text-center py-8">No URL provided</p>
                  )
                ) : c.content_type === 'TEXT' ? (
                  <div className="prose prose-sm max-w-none">
                    {c.text_content ? (
                      <div className="p-4 bg-gray-50 rounded-lg text-gray-700 leading-relaxed" dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(c.text_content) }} />
                    ) : (
                      <div className="p-4 bg-gray-50 rounded-lg text-gray-500">No text content</div>
                    )}
                  </div>
                ) : (
                  <p className="text-gray-400 text-center py-8">Preview not available for this content type</p>
                )}
              </div>
              <div className="p-4 border-t border-gray-200 flex justify-end">
                <Button variant="outline" onClick={() => setPreviewContent(null)}>Close</Button>
              </div>
            </div>
          </div>
        );
      })()}

      {/* Media Library Picker Modal (legacy inline version) */}
      {libraryOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => { setLibraryOpen(false); setLibrarySearch(''); setLibraryFilter('ALL'); }}>
          <div className="bg-white rounded-xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900">Choose from Media Library</h3>
              <button onClick={() => { setLibraryOpen(false); setLibrarySearch(''); setLibraryFilter('ALL'); }} className="p-1 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>
            <div className="p-4 border-b border-gray-200 space-y-3">
              <div className="flex items-center gap-2">
                {(['ALL', 'VIDEO', 'DOCUMENT', 'LINK'] as const).map((filter) => (
                  <button
                    key={filter}
                    type="button"
                    onClick={() => { setLibraryFilter(filter); void fetchLibraryAssets(librarySearch, filter); }}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      libraryFilter === filter ? 'bg-primary-600 text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    {filter}
                  </button>
                ))}
              </div>
              <div className="relative">
                <label htmlFor="library-search" className="sr-only">Search media library</label>
                <MagnifyingGlassIcon className="h-5 w-5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  id="library-search"
                  name="library_search"
                  type="text"
                  value={librarySearch}
                  onChange={async (e) => { const v = e.target.value; setLibrarySearch(v); await fetchLibraryAssets(v, libraryFilter); }}
                  placeholder="Search media..."
                  className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg text-sm"
                />
              </div>
            </div>
            <div className="overflow-y-auto flex-1 p-4">
              {libraryAssets.length === 0 ? (
                <div className="text-center py-12 text-gray-500">
                  <FolderIcon className="h-12 w-12 mx-auto text-gray-300 mb-3" />
                  <p className="text-sm">No assets found. Upload some in the Media Library first.</p>
                </div>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {libraryAssets.map((asset) => (
                    <button
                      key={asset.id}
                      onClick={() => {
                        setNewContentData((prev) => ({
                          ...prev,
                          content_type: asset.media_type,
                          title: prev.title || asset.title,
                          file_url: asset.file_url,
                        }));
                        setContentFile(null);
                        setShowNewTextPreview(false);
                        setLibraryOpen(false);
                        setLibrarySearch('');
                        setLibraryFilter('ALL');
                        toast.success('Selected', `"${asset.title}" selected from library.`);
                      }}
                      className="flex flex-col items-center p-3 border border-gray-200 rounded-lg hover:border-primary-500 hover:bg-primary-50 transition-colors text-left"
                    >
                      <div className="h-16 w-full flex items-center justify-center bg-gray-50 rounded mb-2">
                        {asset.media_type === 'VIDEO' && <PlayCircleIcon className="h-8 w-8 text-blue-500" />}
                        {asset.media_type === 'DOCUMENT' && <DocumentTextIcon className="h-8 w-8 text-orange-500" />}
                        {asset.media_type === 'LINK' && <LinkIcon className="h-8 w-8 text-purple-500" />}
                      </div>
                      <p className="text-xs font-medium text-gray-900 truncate w-full text-center">{asset.title}</p>
                      {asset.file_name && (
                        <p className="text-[10px] text-gray-400 truncate w-full text-center">{asset.file_name}</p>
                      )}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* FilePicker Modal (extracted component -- used via "Browse Existing" button) */}
      <FilePicker
        isOpen={filePickerOpen}
        onClose={() => setFilePickerOpen(false)}
        onSelect={handleFilePickerSelect}
      />

      {/* Delete confirmation dialog */}
      <ConfirmDialog
        isOpen={!!confirmDelete}
        onClose={() => setConfirmDelete(null)}
        onConfirm={() => {
          if (!confirmDelete) return;
          if (confirmDelete.type === 'module') {
            deleteModuleMutation.mutate({ courseId: courseId!, moduleId: confirmDelete.moduleId });
          } else if (confirmDelete.contentId) {
            deleteContentMutation.mutate({
              courseId: courseId!,
              moduleId: confirmDelete.moduleId,
              contentId: confirmDelete.contentId,
            });
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
