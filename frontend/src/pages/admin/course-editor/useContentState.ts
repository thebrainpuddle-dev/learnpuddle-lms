// course-editor/useContentState.ts
//
// Sub-hook: content CRUD within modules, file uploads, video status polling,
// text content editing, media library, and content preview.

import { useState, useRef, useEffect, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { adminService } from '../../../services/adminService';
import { adminMediaService, type MediaAsset } from '../../../services/adminMediaService';
import api from '../../../config/api';
import * as courseApi from './api';
import type {
  Content,
  Course,
  NewContentData,
  UploadPhase,
  LibraryMediaFilter,
} from './types';

export interface UseContentStateParams {
  courseId: string | undefined;
  course: Course | undefined;
  toast: {
    success: (title: string, message: string) => void;
    error: (title: string, message: string) => void;
  };
}

export function useContentState({
  courseId,
  course,
  toast,
}: UseContentStateParams) {
  const queryClient = useQueryClient();

  // ── Video upload / polling state ────────────────────────────────────
  const [uploadPhase, setUploadPhase] = useState<UploadPhase>('idle');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [pollingContentId, setPollingContentId] = useState<string | null>(null);
  const [pollingModuleId, setPollingModuleId] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    setPollingContentId(null);
  }, []);

  const pollErrorCount = useRef(0);
  useEffect(() => {
    if (!pollingContentId || !pollingModuleId || !courseId) return;
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    pollErrorCount.current = 0;
    pollingRef.current = setInterval(async () => {
      try {
        const data = await adminService.getVideoStatus(
          courseId,
          pollingModuleId,
          pollingContentId,
        );
        pollErrorCount.current = 0;
        const st = data.video_asset?.status;
        if (st === 'READY') {
          stopPolling();
          setUploadPhase('done');
          toast.success(
            'Video ready!',
            'HLS streaming, transcript, and assignments have been created.',
          );
          queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
          setTimeout(() => setUploadPhase('idle'), 3000);
        } else if (st === 'FAILED') {
          stopPolling();
          setUploadPhase('idle');
          toast.error(
            'Video processing failed',
            data.video_asset?.error_message || 'Unknown error',
          );
          queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
        }
      } catch {
        pollErrorCount.current += 1;
        if (pollErrorCount.current >= 5) {
          stopPolling();
          setUploadPhase('idle');
          toast.error(
            'Status check failed',
            'Could not reach the server. Please refresh the page.',
          );
        }
      }
    }, 5000);
    return () => stopPolling();
  }, [pollingContentId, pollingModuleId, courseId, stopPolling, toast, queryClient]);

  // Auto-resume polling on page load when a video is processing
  useEffect(() => {
    if (!course || pollingContentId) return;
    for (const mod of course.modules || []) {
      const processing = (mod.contents || []).find(
        (c: Content) =>
          c.content_type === 'VIDEO' && c.video_status === 'PROCESSING',
      );
      if (processing) {
        setPollingContentId(processing.id);
        setPollingModuleId(mod.id);
        setUploadPhase('processing');
        break;
      }
    }
  }, [course, pollingContentId]);

  // ── Content editing state ───────────────────────────────────────────
  const contentFileInputRef = useRef<HTMLInputElement>(null);
  const [addingContentToModule, setAddingContentToModule] = useState<
    string | null
  >(null);
  const [newContentData, setNewContentData] = useState<NewContentData>({
    title: '',
    content_type: 'VIDEO',
    text_content: '',
    file_url: '',
    is_mandatory: true,
  });
  const [contentFile, setContentFile] = useState<File | null>(null);

  // ── Text content inline editing ─────────────────────────────────────
  const [editingTextContentId, setEditingTextContentId] = useState<
    string | null
  >(null);
  const [editingTextModuleId, setEditingTextModuleId] = useState<
    string | null
  >(null);
  const [textContentDraft, setTextContentDraft] = useState('');
  const [showEditingTextPreview, setShowEditingTextPreview] = useState(false);
  const [showNewTextPreview, setShowNewTextPreview] = useState(false);

  // ── Content preview ─────────────────────────────────────────────────
  const [previewContent, setPreviewContent] = useState<Content | null>(null);

  // ── Media library ───────────────────────────────────────────────────
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [librarySearch, setLibrarySearch] = useState('');
  const [libraryFilter, setLibraryFilter] = useState<LibraryMediaFilter>('ALL');
  const [libraryAssets, setLibraryAssets] = useState<MediaAsset[]>([]);

  const fetchLibraryAssets = useCallback(
    async (search = '', filter: LibraryMediaFilter = 'ALL') => {
      const params: {
        media_type?: string;
        search?: string;
        page_size: number;
      } = { page_size: 50 };
      if (filter !== 'ALL') params.media_type = filter;
      if (search.trim()) params.search = search.trim();
      try {
        const res = await adminMediaService.listMedia(params);
        setLibraryAssets(res.results);
      } catch {
        setLibraryAssets([]);
      }
    },
    [],
  );

  const openLibraryPicker = useCallback(
    async (filter: LibraryMediaFilter) => {
      setLibraryFilter(filter);
      setLibrarySearch('');
      await fetchLibraryAssets('', filter);
      setLibraryOpen(true);
    },
    [fetchLibraryAssets],
  );

  // ── Content mutations ───────────────────────────────────────────────
  const contentMutation = useMutation({
    mutationFn: courseApi.createContent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
      setAddingContentToModule(null);
      setNewContentData({
        title: '',
        content_type: 'VIDEO',
        text_content: '',
        file_url: '',
        is_mandatory: true,
      });
      setContentFile(null);
      setShowNewTextPreview(false);
      toast.success('Content added', 'Content has been added to the module.');
    },
    onError: () => {
      toast.error('Failed to add content', 'Please try again.');
    },
  });

  const updateContentMutation = useMutation({
    mutationFn: courseApi.updateContent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
      setEditingTextContentId(null);
      setEditingTextModuleId(null);
      setTextContentDraft('');
      setShowEditingTextPreview(false);
      toast.success('Content updated', 'Text lesson saved.');
    },
    onError: () => {
      toast.error('Failed to update content', 'Please try again.');
    },
  });

  const deleteContentMutation = useMutation({
    mutationFn: courseApi.deleteContent,
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
      if (pollingContentId === variables.contentId) {
        stopPolling();
        setPollingContentId(null);
        setPollingModuleId(null);
      }
      setUploadPhase('idle');
      setUploadProgress(0);
      toast.success('Content deleted', 'Content has been removed.');
    },
    onError: () => {
      toast.error('Failed to delete content', 'Please try again.');
    },
  });

  // ── Handlers ────────────────────────────────────────────────────────
  const startTextContentEdit = useCallback(
    (moduleId: string, content: Content) => {
      setEditingTextModuleId(moduleId);
      setEditingTextContentId(content.id);
      setTextContentDraft(content.text_content || '');
      setShowEditingTextPreview(false);
    },
    [],
  );

  const saveTextContent = useCallback(() => {
    if (!courseId || !editingTextModuleId || !editingTextContentId) return;
    const plainText = textContentDraft
      .replace(/<[^>]*>/g, ' ')
      .replace(/&nbsp;/g, ' ')
      .trim();
    if (!plainText) {
      toast.error('Missing text', 'Please add some text before saving.');
      return;
    }
    updateContentMutation.mutate({
      courseId,
      moduleId: editingTextModuleId,
      contentId: editingTextContentId,
      data: { text_content: textContentDraft },
    });
  }, [
    courseId,
    editingTextModuleId,
    editingTextContentId,
    textContentDraft,
    toast,
    updateContentMutation,
  ]);

  const cancelTextContentEdit = useCallback(() => {
    setEditingTextContentId(null);
    setEditingTextModuleId(null);
    setTextContentDraft('');
    setShowEditingTextPreview(false);
  }, []);

  const handleAddContent = useCallback(
    async (moduleId: string) => {
      if (!newContentData.title.trim() || !courseId) return;

      const module = course?.modules?.find((m) => m.id === moduleId);
      const order = (module?.contents?.length || 0) + 1;

      if (
        newContentData.content_type === 'VIDEO' &&
        !newContentData.file_url
      ) {
        if (!contentFile) {
          toast.error(
            'Missing video file',
            'Please choose a video to upload or select from library.',
          );
          return;
        }
        const fd = new FormData();
        fd.append('file', contentFile);
        fd.append('title', newContentData.title);
        fd.append('order', String(order));
        fd.append('is_mandatory', String(newContentData.is_mandatory));
        fd.append('language', 'en');

        try {
          setUploadPhase('uploading');
          setUploadProgress(0);
          const res = await api.post(
            `/courses/${courseId}/modules/${moduleId}/contents/video-upload/`,
            fd,
            {
              timeout: 600000,
              onUploadProgress: (e) => {
                setUploadProgress(
                  Math.round((e.loaded / (e.total || 1)) * 100),
                );
              },
            },
          );
          setUploadPhase('processing');
          await queryClient.invalidateQueries({
            queryKey: ['adminCourse', courseId],
          });
          const newContentId = res.data?.content?.id;
          if (newContentId) {
            setPollingContentId(newContentId);
            setPollingModuleId(moduleId);
          }
          setAddingContentToModule(null);
          setNewContentData({
            title: '',
            content_type: 'VIDEO',
            text_content: '',
            file_url: '',
            is_mandatory: true,
          });
          setContentFile(null);
          toast.success(
            'Video uploaded',
            'Processing started — HLS, transcript, and assignments will be generated automatically.',
          );
        } catch (err: any) {
          setUploadPhase('idle');
          const msg = err?.response?.data?.error || 'Please try again.';
          toast.error('Video upload failed', msg);
        }
        return;
      }

      const data = new FormData();
      data.append('title', newContentData.title);
      data.append('content_type', newContentData.content_type);
      data.append('is_mandatory', String(newContentData.is_mandatory));
      data.append('order', String(order));

      if (
        newContentData.content_type === 'LINK' &&
        !newContentData.file_url?.trim()
      ) {
        toast.error('Missing URL', 'Please enter a valid link.');
        return;
      }
      if (
        newContentData.content_type === 'DOCUMENT' &&
        !contentFile &&
        !newContentData.file_url
      ) {
        toast.error(
          'Missing file',
          'Please upload a document or select from the media library.',
        );
        return;
      }

      if (newContentData.content_type === 'TEXT') {
        const plainText = newContentData.text_content
          .replace(/<[^>]*>/g, ' ')
          .replace(/&nbsp;/g, ' ')
          .trim();
        if (!plainText) {
          toast.error('Missing text', 'Please add text content.');
          return;
        }
        data.append('text_content', newContentData.text_content);
      } else if (newContentData.content_type === 'LINK') {
        data.append('file_url', newContentData.file_url);
      } else if (contentFile) {
        const fileUrl = await courseApi.uploadFile(contentFile, 'content');
        data.append('file_url', fileUrl);
        data.append('file_size', String(contentFile.size));
        if (newContentData.content_type === 'DOCUMENT') {
          try {
            await adminMediaService.uploadMedia({
              title: newContentData.title || contentFile.name,
              media_type: 'DOCUMENT',
              file_url: fileUrl,
            });
          } catch {
            // Best-effort
          }
        }
      } else if (newContentData.file_url) {
        data.append('file_url', newContentData.file_url);
      }

      contentMutation.mutate({ courseId, moduleId, data });
    },
    [
      courseId,
      course,
      newContentData,
      contentFile,
      toast,
      queryClient,
      contentMutation,
    ],
  );

  /** Called by module hook when a new module is created (bootstrap default text content) */
  const bootstrapModuleTextContent = useCallback(
    async (moduleId: string) => {
      if (!courseId) return;
      try {
        const data = new FormData();
        data.append('title', 'Module Text');
        data.append('content_type', 'TEXT');
        data.append('is_mandatory', 'true');
        data.append('order', '1');
        data.append(
          'text_content',
          '<p>Start writing your module content here.</p>',
        );
        const defaultTextContent = await courseApi.createContent({
          courseId,
          moduleId,
          data,
        });
        setEditingTextModuleId(moduleId);
        setEditingTextContentId(defaultTextContent.id);
        setTextContentDraft(defaultTextContent.text_content || '');
        setShowEditingTextPreview(false);
      } catch {
        // Keep module creation successful even if default content bootstrap fails.
      }
    },
    [courseId],
  );

  /** Called by module hook on module delete when deleted module was being polled */
  const handlePollingModuleDeleted = useCallback(
    (moduleId: string) => {
      if (pollingModuleId === moduleId) {
        stopPolling();
        setPollingContentId(null);
        setPollingModuleId(null);
      }
      setUploadPhase('idle');
      setUploadProgress(0);
    },
    [pollingModuleId, stopPolling],
  );

  return {
    // Video upload / polling
    uploadPhase,
    setUploadPhase,
    uploadProgress,
    pollingContentId,
    pollingModuleId,

    // Content editing
    contentFileInputRef,
    addingContentToModule,
    setAddingContentToModule,
    newContentData,
    setNewContentData,
    contentFile,
    setContentFile,

    // Text editing
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

    // Preview
    previewContent,
    setPreviewContent,

    // Media library
    libraryOpen,
    setLibraryOpen,
    librarySearch,
    setLibrarySearch,
    libraryFilter,
    setLibraryFilter,
    libraryAssets,
    fetchLibraryAssets,
    openLibraryPicker,

    // Mutations
    contentMutation,
    updateContentMutation,
    deleteContentMutation,

    // Handlers
    handleAddContent,
    bootstrapModuleTextContent,
    handlePollingModuleDeleted,
  };
}
