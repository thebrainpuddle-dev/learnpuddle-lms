// course-editor/useCourseForm.ts
//
// Sub-hook: basic course form data (title, description, hours, deadline,
// thumbnail), course create/update mutations, and publish toggle.

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useLocation, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { usePageTitle } from '../../../hooks/usePageTitle';
import { useToast } from '../../../components/common';
import { useTenantStore } from '../../../stores/tenantStore';
import { useAuthStore } from '../../../stores/authStore';
import api from '../../../config/api';
import * as courseApi from './api';
import type {
  Course,
  CourseFormData,
  ConfirmDeleteTarget,
  EditorTab,
  TextEditorMode,
} from './types';

export function useCourseForm() {
  const toast = useToast();
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuthStore();
  const [, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const { hasFeature } = useTenantStore();
  const canUploadVideo = hasFeature('video_upload');
  const isTeacherAuthoring = location.pathname.startsWith('/teacher/authoring');
  const canManageAssignments =
    !isTeacherAuthoring &&
    (!user?.role || user.role === 'SCHOOL_ADMIN' || user.role === 'SUPER_ADMIN');
  const courseListPath = isTeacherAuthoring ? '/teacher/authoring' : '/admin/courses';
  usePageTitle(isTeacherAuthoring ? 'Course Authoring Editor' : 'Course Editor');

  const isEditing = !!courseId && courseId !== 'new';

  // ── Tab management ──────────────────────────────────────────────────
  const resolveTab = React.useCallback(
    (raw: string | null): EditorTab => {
      if (raw === 'audience' && canManageAssignments) return 'audience';
      if (raw === 'ai' && isEditing) return 'ai';
      if (raw === 'content' && isEditing) return 'content';
      return 'details';
    },
    [canManageAssignments, isEditing],
  );

  const activeTab = React.useMemo(
    () => resolveTab(new URLSearchParams(location.search).get('tab')),
    [location.search, resolveTab],
  );

  const setActiveTab = React.useCallback(
    (nextTab: EditorTab) => {
      const audienceSafeTab =
        !canManageAssignments && nextTab === 'audience'
          ? 'details'
          : nextTab;
      const sanitizedTab =
        !isEditing &&
        (audienceSafeTab === 'content' ||
          audienceSafeTab === 'ai' ||
          audienceSafeTab === 'audience')
          ? 'details'
          : audienceSafeTab;
      if (activeTab === sanitizedTab) return;
      const params = new URLSearchParams(location.search);
      params.set('tab', sanitizedTab);
      setSearchParams(params, { replace: true });
    },
    [activeTab, canManageAssignments, isEditing, location.search, setSearchParams],
  );

  // Normalize tab param on mount
  React.useEffect(() => {
    const rawTab = new URLSearchParams(location.search).get('tab');
    const normalizedTab = resolveTab(rawTab);
    if (rawTab === normalizedTab) return;
    const params = new URLSearchParams(location.search);
    params.set('tab', normalizedTab);
    setSearchParams(params, { replace: true });
  }, [location.search, resolveTab, setSearchParams]);

  // ── Editor mode ─────────────────────────────────────────────────────
  const [editorMode, setEditorMode] = useState<TextEditorMode>('WYSIWYG');
  const [showEditorChooser, setShowEditorChooser] = useState(false);
  const [rememberEditorMode, setRememberEditorMode] = useState(true);

  useEffect(() => {
    let isMounted = true;
    api
      .get('/users/auth/preferences/')
      .then((res) => {
        if (!isMounted) return;
        const mode = res?.data?.content_editor_mode;
        if (mode === 'WYSIWYG' || mode === 'MARKDOWN') {
          setEditorMode(mode);
        } else {
          setShowEditorChooser(true);
        }
      })
      .catch(() => {
        if (!isMounted) return;
        setShowEditorChooser(true);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const persistEditorMode = useCallback(async (mode: TextEditorMode) => {
    try {
      await api.patch('/users/auth/preferences/', { content_editor_mode: mode });
    } catch {
      // Non-blocking preference save.
    }
  }, []);

  const handleEditorModeChange = useCallback(
    (mode: TextEditorMode) => {
      setEditorMode(mode);
      if (rememberEditorMode) {
        void persistEditorMode(mode);
      }
    },
    [persistEditorMode, rememberEditorMode],
  );

  const handleSaveEditorChoice = async () => {
    if (rememberEditorMode) {
      await persistEditorMode(editorMode);
    }
    setShowEditorChooser(false);
  };

  const handleModeWarning = useCallback(
    (message: string) => {
      toast.info('Markdown note', message);
    },
    [toast],
  );

  // ── Pre-fill from URL params (e.g. ?sectionId=xxx) ──────────────────
  const prefillSectionId = React.useMemo(() => {
    if (isEditing) return null;
    return new URLSearchParams(window.location.search).get('sectionId');
  }, [isEditing]);

  // ── Form data ───────────────────────────────────────────────────────
  const [formData, setFormData] = useState<CourseFormData>({
    title: '',
    description: '',
    is_mandatory: false,
    deadline: '',
    estimated_hours: 0,
    assigned_to_all: true,
    assigned_groups: [],
    assigned_teachers: [],
    target_sections: prefillSectionId ? [prefillSectionId] : [],
  });

  // ── Thumbnail ───────────────────────────────────────────────────────
  const thumbnailInputRef = useRef<HTMLInputElement>(null);
  const [thumbnailPreview, setThumbnailPreview] = useState<string | null>(null);
  const [thumbnailFile, setThumbnailFile] = useState<File | null>(null);

  const handleThumbnailChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) {
        setThumbnailFile(file);
        const reader = new FileReader();
        reader.onloadend = () =>
          setThumbnailPreview(reader.result as string);
        reader.readAsDataURL(file);
      }
    },
    [],
  );

  // ── Confirm delete (shared across modules/content) ──────────────────
  const [confirmDelete, setConfirmDelete] = useState<ConfirmDeleteTarget | null>(
    null,
  );

  // ── Course query ────────────────────────────────────────────────────
  const {
    data: course,
    isLoading: courseLoading,
  } = useQuery({
    queryKey: ['adminCourse', courseId],
    queryFn: () => courseApi.fetchCourse(courseId!),
    enabled: isEditing,
  });

  // Populate form when course loads
  useEffect(() => {
    if (course) {
      setFormData({
        title: course.title,
        description: course.description,
        is_mandatory: course.is_mandatory,
        deadline: course.deadline || '',
        estimated_hours: course.estimated_hours,
        assigned_to_all: course.assigned_to_all,
        assigned_groups: course.assigned_groups || [],
        assigned_teachers: course.assigned_teachers || [],
        target_sections: course.target_sections || [],
      });
      if (course.thumbnail_url || course.thumbnail) {
        if (course.thumbnail_url) {
          setThumbnailPreview(course.thumbnail_url);
        } else if (course.thumbnail) {
          const backendOrigin = (
            process.env.REACT_APP_API_URL || 'http://localhost:8000/api'
          ).replace(/\/api\/?$/, '');
          const thumbnailUrl = course.thumbnail.startsWith('http')
            ? course.thumbnail
            : `${backendOrigin}${course.thumbnail.startsWith('/') ? '' : '/'}${course.thumbnail}`;
          setThumbnailPreview(thumbnailUrl);
        }
      }
    }
  }, [course]);

  // ── Input handler ───────────────────────────────────────────────────
  const handleInputChange = useCallback(
    (
      e: React.ChangeEvent<
        HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
      >,
    ) => {
      const { name, value, type } = e.target;
      setFormData((prev) => ({
        ...prev,
        [name]:
          type === 'checkbox'
            ? (e.target as HTMLInputElement).checked
            : value,
      }));
    },
    [],
  );

  // ── Course mutations ────────────────────────────────────────────────
  const createCourseMutation = useMutation({
    mutationFn: courseApi.createCourse,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['adminCourses'] });
      queryClient.invalidateQueries({ queryKey: ['adminDashboardStats'] });
      toast.success('Course created', 'Now add modules and content.');
      navigate(`${courseListPath}/${data.id}/edit`);
    },
    onError: () => {
      toast.error(
        'Failed to create course',
        'Please check the details and try again.',
      );
    },
  });

  const updateCourseMutation = useMutation({
    mutationFn: courseApi.updateCourse,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['adminCourses'] });
      queryClient.invalidateQueries({ queryKey: ['adminCourse', data.id] });
      queryClient.invalidateQueries({ queryKey: ['adminDashboardStats'] });
      toast.success('Course saved', 'Your changes have been saved.');
    },
    onError: () => {
      toast.error('Failed to save course', 'Please try again.');
    },
  });

  const courseMutationPending =
    createCourseMutation.isPending || updateCourseMutation.isPending;

  const publishMutation = useMutation({
    mutationFn: async (publish: boolean) => {
      const res = await api.patch(`/courses/${courseId}/`, {
        is_published: publish,
      });
      return res.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
      queryClient.invalidateQueries({ queryKey: ['adminCourses'] });
      queryClient.invalidateQueries({ queryKey: ['adminDashboardStats'] });
      toast.success(
        data.is_published ? 'Course published' : 'Course unpublished',
        data.is_published
          ? 'Teachers can now access this course.'
          : 'Course is now in draft mode.',
      );
    },
    onError: () =>
      toast.error('Failed to update status', 'Please try again.'),
  });

  // ── Save handler ────────────────────────────────────────────────────
  const handleSaveCourse = useCallback(async () => {
    const data = new FormData();
    data.append('title', formData.title);
    data.append('description', formData.description);
    data.append('is_mandatory', String(formData.is_mandatory));
    if (formData.deadline) data.append('deadline', formData.deadline);
    data.append('estimated_hours', String(formData.estimated_hours));
    data.append(
      'assigned_to_all',
      String(canManageAssignments ? formData.assigned_to_all : false),
    );

    if (canManageAssignments && !formData.assigned_to_all) {
      formData.assigned_groups.forEach((id) =>
        data.append('assigned_groups', id),
      );
      formData.assigned_teachers.forEach((id) =>
        data.append('assigned_teachers', id),
      );
    }

    // Always send target_sections if any are set
    formData.target_sections.forEach((id) =>
      data.append('target_sections', id),
    );

    if (thumbnailFile) {
      data.append('thumbnail', thumbnailFile);
    }

    if (isEditing) {
      updateCourseMutation.mutate({ id: courseId!, data });
    } else {
      createCourseMutation.mutate(data);
    }
  }, [
    formData,
    thumbnailFile,
    canManageAssignments,
    isEditing,
    courseId,
    updateCourseMutation,
    createCourseMutation,
  ]);

  return {
    // Identity / navigation
    courseId,
    isEditing,
    isTeacherAuthoring,
    canManageAssignments,
    canUploadVideo,
    courseListPath,
    navigate,
    toast,

    // Tab
    activeTab,
    setActiveTab,

    // Editor mode
    editorMode,
    setEditorMode,
    showEditorChooser,
    setShowEditorChooser,
    rememberEditorMode,
    setRememberEditorMode,
    handleEditorModeChange,
    handleSaveEditorChoice,
    handleModeWarning,

    // Course data
    course,
    courseLoading,
    formData,
    setFormData,
    handleInputChange,
    handleSaveCourse,
    courseMutationPending,

    // Thumbnail
    thumbnailPreview,
    thumbnailFile,
    thumbnailInputRef,
    handleThumbnailChange,

    // Publish
    publishMutation,

    // Confirm delete
    confirmDelete,
    setConfirmDelete,
  };
}
