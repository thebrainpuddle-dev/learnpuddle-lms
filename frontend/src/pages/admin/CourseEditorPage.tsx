// src/pages/admin/CourseEditorPage.tsx

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useLocation, useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { usePageTitle } from '../../hooks/usePageTitle';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Input, Loading, useToast, HlsVideoPlayer, ConfirmDialog } from '../../components/common';
import { RichTextEditor } from '../../components/common/RichTextEditor';
import DOMPurify from 'dompurify';
import { useTenantStore } from '../../stores/tenantStore';
import { useAuthStore } from '../../stores/authStore';
import {
  adminService,
  type AdminAssignment,
  type AdminAssignmentPayload,
  type AdminAssignmentType,
  type AdminQuizQuestion,
} from '../../services/adminService';
import { adminMediaService, type MediaAsset } from '../../services/adminMediaService';
import api from '../../config/api';
import {
  ArrowLeftIcon,
  PhotoIcon,
  PlusIcon,
  TrashIcon,
  ChevronUpIcon,
  ChevronDownIcon,
  Bars3Icon,
  PlayCircleIcon,
  DocumentTextIcon,
  LinkIcon,
  PencilIcon,
  CheckIcon,
  XMarkIcon,
  UserGroupIcon,
  UsersIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
  EyeIcon,
  GlobeAltIcon,
  FolderIcon,
  MagnifyingGlassIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline';

interface Teacher {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
}

interface TeacherGroup {
  id: string;
  name: string;
  description: string;
  group_type: string;
  member_count?: number;
}

interface Content {
  id: string;
  title: string;
  content_type: 'VIDEO' | 'DOCUMENT' | 'TEXT' | 'LINK';
  order: number;
  file_url: string | null;
  text_content: string;
  is_mandatory: boolean;
  duration: number | null;
  file_size: number | null;
  video_status?: 'UPLOADED' | 'PROCESSING' | 'READY' | 'FAILED' | null;
}

interface Module {
  id: string;
  title: string;
  description: string;
  order: number;
  contents: Content[];
}

interface Course {
  id: string;
  title: string;
  slug: string;
  description: string;
  thumbnail: string | null;
  thumbnail_url: string | null;
  is_mandatory: boolean;
  deadline: string | null;
  estimated_hours: number;
  assigned_to_all: boolean;
  assigned_groups: string[];
  assigned_teachers: string[];
  is_published: boolean;
  modules: Module[];
}

type EditorTab = 'details' | 'content' | 'assignments' | 'audience';
type TextEditorMode = 'WYSIWYG' | 'MARKDOWN';
type LibraryMediaFilter = 'ALL' | MediaAsset['media_type'];
type AssignmentScopeFilter = 'ALL' | 'COURSE' | 'MODULE';

const fetchCourse = async (id: string): Promise<Course> => {
  const response = await api.get(`/courses/${id}/`);
  return response.data;
};

const fetchTeachers = async (): Promise<Teacher[]> => {
  const response = await api.get('/teachers/');
  // Backend returns paginated response { results: [...], count, next, previous }
  return response.data.results ?? response.data;
};

const fetchGroups = async (): Promise<TeacherGroup[]> => {
  const response = await api.get('/teacher-groups/');
  return response.data.results ?? response.data;
};

const createCourse = async (data: FormData): Promise<Course> => {
  // Axios automatically sets Content-Type with boundary for FormData
  const response = await api.post('/courses/', data);
  return response.data;
};

const updateCourse = async ({ id, data }: { id: string; data: FormData }): Promise<Course> => {
  // Axios automatically sets Content-Type with boundary for FormData
  const response = await api.patch(`/courses/${id}/`, data);
  return response.data;
};

const createModule = async ({ courseId, data }: { courseId: string; data: any }): Promise<Module> => {
  const response = await api.post(`/courses/${courseId}/modules/`, data);
  return response.data;
};

const updateModule = async ({ courseId, moduleId, data }: { courseId: string; moduleId: string; data: any }): Promise<Module> => {
  const response = await api.patch(`/courses/${courseId}/modules/${moduleId}/`, data);
  return response.data;
};

const deleteModule = async ({ courseId, moduleId }: { courseId: string; moduleId: string }): Promise<void> => {
  await api.delete(`/courses/${courseId}/modules/${moduleId}/`);
};

const createContent = async ({ courseId, moduleId, data }: { courseId: string; moduleId: string; data: FormData }): Promise<Content> => {
  // Axios automatically sets Content-Type with boundary for FormData
  const response = await api.post(`/courses/${courseId}/modules/${moduleId}/contents/`, data);
  return response.data;
};

const updateContent = async ({
  courseId,
  moduleId,
  contentId,
  data,
}: {
  courseId: string;
  moduleId: string;
  contentId: string;
  data: Record<string, any>;
}): Promise<Content> => {
  const response = await api.patch(`/courses/${courseId}/modules/${moduleId}/contents/${contentId}/`, data);
  return response.data;
};

const deleteContent = async ({ courseId, moduleId, contentId }: { courseId: string; moduleId: string; contentId: string }): Promise<void> => {
  await api.delete(`/courses/${courseId}/modules/${moduleId}/contents/${contentId}/`);
};

const uploadFile = async (file: File, type: 'thumbnail' | 'content'): Promise<string> => {
  const formData = new FormData();
  formData.append('file', file);

  const endpoint = type === 'thumbnail' ? '/uploads/course-thumbnail/' : '/uploads/content-file/';
  // Axios automatically sets Content-Type with boundary for FormData
  const response = await api.post(endpoint, formData);
  return response.data.url;
};

const uploadEditorImage = async (file: File): Promise<{ src: string; imageId: string }> => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await api.post('/uploads/editor-image/', formData);
  return {
    src: response.data.preview_url,
    imageId: response.data.asset_id,
  };
};

const buildEmptyQuestion = (order: number): AdminQuizQuestion => ({
  order,
  question_type: 'MCQ',
  selection_mode: 'SINGLE',
  prompt: '',
  options: ['Option 1', 'Option 2'],
  correct_answer: { option_index: 0 },
  explanation: '',
  points: 1,
});

const buildEmptyAssignmentForm = (): AdminAssignmentPayload => ({
  title: '',
  description: '',
  instructions: '',
  due_date: null,
  max_score: 100,
  passing_score: 70,
  is_mandatory: true,
  is_active: true,
  scope_type: 'COURSE',
  module_id: null,
  assignment_type: 'QUIZ',
  questions: [buildEmptyQuestion(1)],
});

export const CourseEditorPage: React.FC = () => {
  const toast = useToast();
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuthStore();
  const [, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const thumbnailInputRef = useRef<HTMLInputElement>(null);
  const contentFileInputRef = useRef<HTMLInputElement>(null);
  const { hasFeature } = useTenantStore();
  const canUploadVideo = hasFeature('video_upload');
  const isTeacherAuthoring = location.pathname.startsWith('/teacher/authoring');
  const canManageAssignments = !isTeacherAuthoring && (
    !user?.role || user.role === 'SCHOOL_ADMIN' || user.role === 'SUPER_ADMIN'
  );
  const courseListPath = isTeacherAuthoring ? '/teacher/authoring' : '/admin/courses';
  usePageTitle(isTeacherAuthoring ? 'Course Authoring Editor' : 'Course Editor');

  const isEditing = !!courseId && courseId !== 'new';

  // Video upload progress + processing status polling
  const [uploadPhase, setUploadPhase] = useState<'idle' | 'uploading' | 'processing' | 'done'>('idle');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [pollingContentId, setPollingContentId] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll video-status until READY or FAILED
  const stopPolling = useCallback(() => {
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
    setPollingContentId(null);
  }, []);

  // pollingModuleId is set alongside pollingContentId
  const [pollingModuleId, setPollingModuleId] = useState<string | null>(null);

  const pollErrorCount = useRef(0);
  useEffect(() => {
    if (!pollingContentId || !pollingModuleId || !courseId) return;
    // Clear any previous interval before starting a new one
    if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
    pollErrorCount.current = 0;
    pollingRef.current = setInterval(async () => {
      try {
        const data = await adminService.getVideoStatus(courseId, pollingModuleId, pollingContentId);
        pollErrorCount.current = 0; // reset on success
        const st = data.video_asset?.status;
        if (st === 'READY') {
          stopPolling();
          setUploadPhase('done');
          toast.success('Video ready!', 'HLS streaming, transcript, and assignments have been created.');
          queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
          setTimeout(() => setUploadPhase('idle'), 3000);
        } else if (st === 'FAILED') {
          stopPolling();
          setUploadPhase('idle');
          toast.error('Video processing failed', data.video_asset?.error_message || 'Unknown error');
          queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
        }
      } catch {
        pollErrorCount.current += 1;
        if (pollErrorCount.current >= 5) {
          stopPolling();
          setUploadPhase('idle');
          toast.error('Status check failed', 'Could not reach the server. Please refresh the page.');
        }
      }
    }, 5000);
    return () => stopPolling();
  }, [pollingContentId, pollingModuleId, courseId, stopPolling, toast, queryClient]);

  const resolveTab = React.useCallback(
    (raw: string | null): EditorTab => {
      if ((raw === 'assignment' || raw === 'audience') && canManageAssignments) return 'audience';
      if (raw === 'assignments' && canManageAssignments && isEditing) return 'assignments';
      if (raw === 'content' && isEditing) return 'content';
      return 'details';
    },
    [canManageAssignments, isEditing]
  );
  const activeTab = React.useMemo(
    () => resolveTab(new URLSearchParams(location.search).get('tab')),
    [location.search, resolveTab]
  );
  const setActiveTab = React.useCallback(
    (nextTab: EditorTab) => {
      const assignmentSafeTab = !canManageAssignments && (nextTab === 'assignments' || nextTab === 'audience')
        ? 'details'
        : nextTab;
      const sanitizedTab = !isEditing && (assignmentSafeTab === 'content' || assignmentSafeTab === 'assignments' || assignmentSafeTab === 'audience')
        ? 'details'
        : assignmentSafeTab;
      if (activeTab === sanitizedTab) return;
      const params = new URLSearchParams(location.search);
      params.set('tab', sanitizedTab);
      setSearchParams(params, { replace: true });
    },
    [activeTab, canManageAssignments, isEditing, location.search, setSearchParams]
  );
  const [editorMode, setEditorMode] = useState<TextEditorMode>('WYSIWYG');
  const [showEditorChooser, setShowEditorChooser] = useState(false);
  const [rememberEditorMode, setRememberEditorMode] = useState(true);
  const [editingModuleDescriptionId, setEditingModuleDescriptionId] = useState<string | null>(null);
  const [moduleDescriptionDrafts, setModuleDescriptionDrafts] = useState<Record<string, string>>({});
  const [editingTextContentId, setEditingTextContentId] = useState<string | null>(null);
  const [editingTextModuleId, setEditingTextModuleId] = useState<string | null>(null);
  const [textContentDraft, setTextContentDraft] = useState('');
  const [showEditingTextPreview, setShowEditingTextPreview] = useState(false);
  const [showNewTextPreview, setShowNewTextPreview] = useState(false);
  const [thumbnailPreview, setThumbnailPreview] = useState<string | null>(null);
  const [thumbnailFile, setThumbnailFile] = useState<File | null>(null);
  const [expandedModules, setExpandedModules] = useState<string[]>([]);
  const [editingModule, setEditingModule] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<{ type: 'module' | 'content'; moduleId: string; contentId?: string; label: string } | null>(null);
  const [newModuleTitle, setNewModuleTitle] = useState('');
  const [addingContentToModule, setAddingContentToModule] = useState<string | null>(null);
  const [newContentData, setNewContentData] = useState({
    title: '',
    content_type: 'VIDEO' as Content['content_type'],
    text_content: '',
    file_url: '',
    is_mandatory: true,
  });
  const [contentFile, setContentFile] = useState<File | null>(null);

  // Inline group creation (for assignment UX)
  const [createGroupOpen, setCreateGroupOpen] = useState(false);
  const [createGroupForm, setCreateGroupForm] = useState({
    name: '',
    description: '',
    group_type: 'CUSTOM',
  });
  
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    is_mandatory: false,
    deadline: '',
    estimated_hours: 0,
    assigned_to_all: true,
    assigned_groups: [] as string[],
    assigned_teachers: [] as string[],
  });
  const [assignmentScopeFilter, setAssignmentScopeFilter] = useState<AssignmentScopeFilter>('ALL');
  const [selectedAssignmentId, setSelectedAssignmentId] = useState<string | null>(null);
  const [isCreatingNewAssignment, setIsCreatingNewAssignment] = useState(false);
  const [assignmentForm, setAssignmentForm] = useState<AdminAssignmentPayload>(buildEmptyAssignmentForm());
  const [aiQuestionCount, setAiQuestionCount] = useState(6);
  const [aiIncludeShortAnswer, setAiIncludeShortAnswer] = useState(true);
  const [aiTitleHint, setAiTitleHint] = useState('');
  const aiModelLabel = 'Ollama (backend-configured, default: mistral) with deterministic fallback';

  useEffect(() => {
    let isMounted = true;
    api.get('/users/auth/preferences/')
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

  // Fetch course if editing
  const { data: course, isLoading: courseLoading } = useQuery({
    queryKey: ['adminCourse', courseId],
    queryFn: () => fetchCourse(courseId!),
    enabled: isEditing,
  });

  // Auto-resume polling on page load for any video still in PROCESSING state
  useEffect(() => {
    if (!course || pollingContentId) return;
    for (const mod of course.modules || []) {
      const processing = (mod.contents || []).find(
        (c: Content) => c.content_type === 'VIDEO' && c.video_status === 'PROCESSING'
      );
      if (processing) {
        setPollingContentId(processing.id);
        setPollingModuleId(mod.id);
        setUploadPhase('processing');
        break;
      }
    }
  }, [course, pollingContentId]);

  // Fetch teachers and groups for assignment
  const { data: teachers } = useQuery({
    queryKey: ['adminTeachers'],
    queryFn: fetchTeachers,
    enabled: canManageAssignments,
  });

  const { data: groups } = useQuery({
    queryKey: ['adminGroups'],
    queryFn: fetchGroups,
    enabled: canManageAssignments,
  });

  const { data: assignmentList = [], isLoading: assignmentListLoading } = useQuery({
    queryKey: ['courseAssignments', courseId, assignmentScopeFilter],
    queryFn: () => adminService.listCourseAssignments(courseId!, {
      scope: assignmentScopeFilter,
    }),
    enabled: Boolean(courseId) && isEditing && canManageAssignments,
  });

  const { data: selectedAssignment, isLoading: selectedAssignmentLoading } = useQuery({
    queryKey: ['courseAssignment', courseId, selectedAssignmentId],
    queryFn: () => adminService.getCourseAssignment(courseId!, selectedAssignmentId!),
    enabled: Boolean(courseId && selectedAssignmentId),
  });

  const createAssignmentMutation = useMutation({
    mutationFn: (payload: AdminAssignmentPayload) => adminService.createCourseAssignment(courseId!, payload),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({ queryKey: ['courseAssignments', courseId] });
      setIsCreatingNewAssignment(false);
      setSelectedAssignmentId(created.id);
      toast.success('Assignment created', 'Assignment builder item is ready to edit.');
    },
    onError: (error: any) => {
      const msg = error?.response?.data?.error || 'Please review inputs and try again.';
      toast.error('Failed to create assignment', msg);
    },
  });

  const updateAssignmentMutation = useMutation({
    mutationFn: ({ assignmentId, payload }: { assignmentId: string; payload: Partial<AdminAssignmentPayload> }) =>
      adminService.updateCourseAssignment(courseId!, assignmentId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['courseAssignments', courseId] });
      await queryClient.invalidateQueries({ queryKey: ['courseAssignment', courseId, selectedAssignmentId] });
      toast.success('Assignment saved', 'Builder changes have been saved.');
    },
    onError: (error: any) => {
      const msg = error?.response?.data?.error || 'Please review inputs and try again.';
      toast.error('Failed to save assignment', msg);
    },
  });

  const deleteAssignmentMutation = useMutation({
    mutationFn: (assignmentId: string) => adminService.deleteCourseAssignment(courseId!, assignmentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['courseAssignments', courseId] });
      setSelectedAssignmentId(null);
      setIsCreatingNewAssignment(false);
      setAssignmentForm(buildEmptyAssignmentForm());
      toast.success('Assignment deleted', 'The assignment was removed from this course.');
    },
    onError: (error: any) => {
      const msg = error?.response?.data?.error || 'Please try again.';
      toast.error('Failed to delete assignment', msg);
    },
  });

  const aiGenerateMutation = useMutation({
    mutationFn: () =>
      adminService.aiGenerateCourseAssignment(courseId!, {
        scope_type: assignmentForm.scope_type,
        module_id: assignmentForm.scope_type === 'MODULE' ? assignmentForm.module_id : null,
        question_count: aiQuestionCount,
        include_short_answer: aiIncludeShortAnswer,
        title_hint: aiTitleHint || assignmentForm.title || undefined,
      }),
    onSuccess: async (assignment) => {
      await queryClient.invalidateQueries({ queryKey: ['courseAssignments', courseId] });
      setIsCreatingNewAssignment(false);
      setSelectedAssignmentId(assignment.id);
      toast.success('AI assignment generated', 'Review and save the generated questions.');
    },
    onError: (error: any) => {
      const msg = error?.response?.data?.error || 'Please try again.';
      toast.error('AI generation failed', msg);
    },
  });

  useEffect(() => {
    if (!assignmentList.length) return;
    if (!selectedAssignmentId && !isCreatingNewAssignment) {
      setSelectedAssignmentId(assignmentList[0].id);
      return;
    }
    if (!assignmentList.find((item) => item.id === selectedAssignmentId)) {
      setSelectedAssignmentId(assignmentList[0].id);
    }
  }, [assignmentList, selectedAssignmentId, isCreatingNewAssignment]);

  useEffect(() => {
    if (!selectedAssignment) return;
    setAssignmentForm({
      title: selectedAssignment.title,
      description: selectedAssignment.description || '',
      instructions: selectedAssignment.instructions || '',
      due_date: selectedAssignment.due_date || null,
      max_score: Number(selectedAssignment.max_score || 100),
      passing_score: Number(selectedAssignment.passing_score || 70),
      is_mandatory: selectedAssignment.is_mandatory,
      is_active: selectedAssignment.is_active,
      scope_type: selectedAssignment.scope_type,
      module_id: selectedAssignment.module_id,
      assignment_type: selectedAssignment.assignment_type,
      questions: selectedAssignment.questions?.length
        ? selectedAssignment.questions.map((q) => ({
            ...q,
            selection_mode: q.selection_mode || 'SINGLE',
            options: q.options || [],
            correct_answer: q.correct_answer || {},
          }))
        : [],
    });
  }, [selectedAssignment]);

  const createGroupMutation = useMutation({
    mutationFn: (payload: { name: string; description?: string; group_type?: string }) =>
      api.post('/teacher-groups/', payload).then((r) => r.data),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['adminGroups'] });
      setCreateGroupForm({ name: '', description: '', group_type: 'CUSTOM' });
      setCreateGroupOpen(false);
    },
  });

  // Populate form when course data loads
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
      });
      if (course.thumbnail_url || course.thumbnail) {
        // Prefer signed thumbnail_url, fallback to resolving thumbnail
        if (course.thumbnail_url) {
          setThumbnailPreview(course.thumbnail_url);
        } else if (course.thumbnail) {
          const backendOrigin = (process.env.REACT_APP_API_URL || 'http://localhost:8000/api').replace(/\/api\/?$/, '');
          const thumbnailUrl = course.thumbnail.startsWith('http')
            ? course.thumbnail
            : `${backendOrigin}${course.thumbnail.startsWith('/') ? '' : '/'}${course.thumbnail}`;
          setThumbnailPreview(thumbnailUrl);
        }
      }
      // Expand all modules by default when editing
      if (course.modules) {
        setExpandedModules(course.modules.map(m => m.id));
      }
    }
  }, [course]);

  const aiSourceState = React.useMemo(() => {
    const selectedModule =
      assignmentForm.scope_type === 'MODULE'
        ? (course?.modules || []).find((module) => module.id === assignmentForm.module_id) || null
        : null;

    if (assignmentForm.scope_type === 'MODULE' && !selectedModule) {
      return {
        enabled: false,
        reason: 'Select a module first.',
        summary: 'No module selected',
      };
    }

    const scopedContents =
      assignmentForm.scope_type === 'MODULE'
        ? selectedModule?.contents || []
        : (course?.modules || []).flatMap((module) => module.contents || []);

    if (!scopedContents.length) {
      return {
        enabled: false,
        reason: 'Add content first. AI needs text, documents, or a processed video transcript.',
        summary: 'No content available in selected scope',
      };
    }

    const textCount = scopedContents.filter(
      (content) => content.content_type === 'TEXT' && Boolean(content.text_content?.replace(/<[^>]+>/g, '').trim())
    ).length;
    const documentCount = scopedContents.filter(
      (content) => content.content_type === 'DOCUMENT' && Boolean(content.file_url)
    ).length;
    const readyVideoCount = scopedContents.filter(
      (content) =>
        content.content_type === 'VIDEO' &&
        (content.video_status === 'READY' || (!content.video_status && Boolean(content.file_url)))
    ).length;
    const processingVideoCount = scopedContents.filter(
      (content) => content.content_type === 'VIDEO' && content.video_status === 'PROCESSING'
    ).length;

    const enabled = textCount > 0 || documentCount > 0 || readyVideoCount > 0;
    if (!enabled && processingVideoCount > 0) {
      return {
        enabled: false,
        reason: 'Video processing is in progress. AI generation unlocks once transcript is ready.',
        summary: `${processingVideoCount} video(s) processing`,
      };
    }
    if (!enabled) {
      return {
        enabled: false,
        reason: 'Upload text, document, or a processed video to generate AI assignments.',
        summary: 'No eligible source material found',
      };
    }

    const summaryParts: string[] = [];
    if (readyVideoCount) summaryParts.push(`${readyVideoCount} transcript-ready video`);
    if (documentCount) summaryParts.push(`${documentCount} document`);
    if (textCount) summaryParts.push(`${textCount} text block`);

    return {
      enabled: true,
      reason: '',
      summary: `Using ${summaryParts.join(', ')}`,
    };
  }, [assignmentForm.module_id, assignmentForm.scope_type, course]);

  // Mutations
  const createCourseMutation = useMutation({
    mutationFn: createCourse,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['adminCourses'] });
      queryClient.invalidateQueries({ queryKey: ['adminDashboardStats'] });
      toast.success('Course created', 'Now add modules and content.');
      navigate(`${courseListPath}/${data.id}/edit`);
    },
    onError: () => {
      toast.error('Failed to create course', 'Please check the details and try again.');
    },
  });

  const updateCourseMutation = useMutation({
    mutationFn: updateCourse,
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

  const courseMutationPending = createCourseMutation.isPending || updateCourseMutation.isPending;

  React.useEffect(() => {
    const rawTab = new URLSearchParams(location.search).get('tab');
    const normalizedTab = resolveTab(rawTab);
    if (rawTab === normalizedTab) return;
    const params = new URLSearchParams(location.search);
    params.set('tab', normalizedTab);
    setSearchParams(params, { replace: true });
  }, [location.search, resolveTab, setSearchParams]);

  const moduleMutation = useMutation({
    mutationFn: createModule,
    onSuccess: async (newModule) => {
      if (!courseId) return;
      setNewModuleTitle('');
      setExpandedModules((prev) => (prev.includes(newModule.id) ? prev : [...prev, newModule.id]));
      setEditingModule(newModule.id);

      try {
        const data = new FormData();
        data.append('title', 'Module Text');
        data.append('content_type', 'TEXT');
        data.append('is_mandatory', 'true');
        data.append('order', '1');
        data.append('text_content', '<p>Start writing your module content here.</p>');
        const defaultTextContent = await createContent({ courseId, moduleId: newModule.id, data });
        setEditingTextModuleId(newModule.id);
        setEditingTextContentId(defaultTextContent.id);
        setTextContentDraft(defaultTextContent.text_content || '');
        setShowEditingTextPreview(false);
      } catch {
        // Keep module creation successful even if default content bootstrap fails.
      }

      await queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
      toast.success('Module added', 'Module is ready with a default text editor.');
    },
    onError: () => {
      toast.error('Failed to add module', 'Please try again.');
    },
  });

  const updateModuleMutation = useMutation({
    mutationFn: updateModule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
      setEditingModule(null);
      toast.success('Module updated', 'Changes saved.');
    },
    onError: () => {
      toast.error('Failed to update module', 'Please try again.');
    },
  });

  const deleteModuleMutation = useMutation({
    mutationFn: deleteModule,
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
      // Reset upload/processing state if the deleted module contained a processing video
      if (pollingModuleId === variables.moduleId) {
        stopPolling();
        setPollingContentId(null);
        setPollingModuleId(null);
      }
      setUploadPhase('idle');
      setUploadProgress(0);
      toast.success('Module deleted', 'Module and its content have been removed.');
    },
    onError: () => {
      toast.error('Failed to delete module', 'Please try again.');
    },
  });

  const contentMutation = useMutation({
    mutationFn: createContent,
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
    mutationFn: updateContent,
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
    mutationFn: deleteContent,
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
      // Reset upload/processing state if the deleted content was being processed
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

  // Publish / unpublish
  const publishMutation = useMutation({
    mutationFn: async (publish: boolean) => {
      const res = await api.patch(`/courses/${courseId}/`, { is_published: publish });
      return res.data;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
      queryClient.invalidateQueries({ queryKey: ['adminCourses'] });
      queryClient.invalidateQueries({ queryKey: ['adminDashboardStats'] });
      toast.success(data.is_published ? 'Course published' : 'Course unpublished',
        data.is_published ? 'Teachers can now access this course.' : 'Course is now in draft mode.');
    },
    onError: () => toast.error('Failed to update status', 'Please try again.'),
  });

  // Content preview
  const [previewContent, setPreviewContent] = useState<Content | null>(null);

  // Media library picker
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [librarySearch, setLibrarySearch] = useState('');
  const [libraryFilter, setLibraryFilter] = useState<LibraryMediaFilter>('ALL');
  const [libraryAssets, setLibraryAssets] = useState<MediaAsset[]>([]);

  const fetchLibraryAssets = useCallback(async (search = '', filter: LibraryMediaFilter = 'ALL') => {
    const params: { media_type?: string; search?: string; page_size: number } = { page_size: 50 };
    if (filter !== 'ALL') params.media_type = filter;
    if (search.trim()) params.search = search.trim();
    try {
      const res = await adminMediaService.listMedia(params);
      setLibraryAssets(res.results);
    } catch {
      setLibraryAssets([]);
    }
  }, []);

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? (e.target as HTMLInputElement).checked : value,
    }));
  };

  const handleThumbnailChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setThumbnailFile(file);
      const reader = new FileReader();
      reader.onloadend = () => setThumbnailPreview(reader.result as string);
      reader.readAsDataURL(file);
    }
  };

  const persistEditorMode = useCallback(async (mode: TextEditorMode) => {
    try {
      await api.patch('/users/auth/preferences/', { content_editor_mode: mode });
    } catch {
      // Non-blocking preference save.
    }
  }, []);

  const handleEditorModeChange = useCallback((mode: TextEditorMode) => {
    setEditorMode(mode);
    if (rememberEditorMode) {
      void persistEditorMode(mode);
    }
  }, [persistEditorMode, rememberEditorMode]);

  const handleSaveEditorChoice = async () => {
    if (rememberEditorMode) {
      await persistEditorMode(editorMode);
    }
    setShowEditorChooser(false);
  };

  const handleModeWarning = useCallback((message: string) => {
    toast.info('Markdown note', message);
  }, [toast]);

  const startModuleDescriptionEdit = (module: Module) => {
    setEditingModuleDescriptionId(module.id);
    setModuleDescriptionDrafts((prev) => ({ ...prev, [module.id]: module.description || '' }));
  };

  const saveModuleDescription = (moduleId: string) => {
    if (!courseId) return;
    updateModuleMutation.mutate({
      courseId,
      moduleId,
      data: { description: moduleDescriptionDrafts[moduleId] || '' },
    }, {
      onSuccess: () => {
        setEditingModuleDescriptionId(null);
      },
    });
  };

  const cancelModuleDescriptionEdit = (moduleId: string) => {
    setEditingModuleDescriptionId(null);
    setModuleDescriptionDrafts((prev) => {
      const next = { ...prev };
      delete next[moduleId];
      return next;
    });
  };

  const startTextContentEdit = (moduleId: string, content: Content) => {
    setEditingTextModuleId(moduleId);
    setEditingTextContentId(content.id);
    setTextContentDraft(content.text_content || '');
    setShowEditingTextPreview(false);
  };

  const saveTextContent = () => {
    if (!courseId || !editingTextModuleId || !editingTextContentId) return;
    const plainText = textContentDraft.replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').trim();
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
  };

  const cancelTextContentEdit = () => {
    setEditingTextContentId(null);
    setEditingTextModuleId(null);
    setTextContentDraft('');
    setShowEditingTextPreview(false);
  };

  const handleSaveCourse = async () => {
    const data = new FormData();
    data.append('title', formData.title);
    data.append('description', formData.description);
    data.append('is_mandatory', String(formData.is_mandatory));
    if (formData.deadline) data.append('deadline', formData.deadline);
    data.append('estimated_hours', String(formData.estimated_hours));
    data.append('assigned_to_all', String(canManageAssignments ? formData.assigned_to_all : false));

    if (canManageAssignments && !formData.assigned_to_all) {
      // Append each ID separately - DRF's parser will combine into array
      formData.assigned_groups.forEach(id => data.append('assigned_groups', id));
      formData.assigned_teachers.forEach(id => data.append('assigned_teachers', id));
    }

    if (thumbnailFile) {
      data.append('thumbnail', thumbnailFile);
    }

    if (isEditing) {
      updateCourseMutation.mutate({ id: courseId!, data });
    } else {
      createCourseMutation.mutate(data);
    }
  };

  const handleAddModule = () => {
    if (!courseId) return;
    const nextOrder = (course?.modules?.length || 0) + 1;
    const nextTitle = newModuleTitle.trim() || `Untitled Module ${nextOrder}`;
    moduleMutation.mutate({
      courseId,
      data: {
        title: nextTitle,
        description: '',
        order: nextOrder,
      },
    });
  };

  const openLibraryPicker = useCallback(async (filter: LibraryMediaFilter) => {
    setLibraryFilter(filter);
    setLibrarySearch('');
    await fetchLibraryAssets('', filter);
    setLibraryOpen(true);
  }, [fetchLibraryAssets]);

  const handleAddContent = async (moduleId: string) => {
    if (!newContentData.title.trim() || !courseId) return;
    
    const module = course?.modules?.find(m => m.id === moduleId);
    const order = (module?.contents?.length || 0) + 1;

    // Video uses dedicated endpoint (HLS + transcript + assignments pipeline)
    // But if file_url is already set from library, use the regular content creation flow
    if (newContentData.content_type === 'VIDEO' && !newContentData.file_url) {
      if (!contentFile) {
        toast.error('Missing video file', 'Please choose a video to upload or select from library.');
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
        // Axios automatically sets Content-Type with boundary for FormData
        const res = await api.post(`/courses/${courseId}/modules/${moduleId}/contents/video-upload/`, fd, {
          timeout: 600000, // 10 min for large files
          onUploadProgress: (e) => {
            setUploadProgress(Math.round((e.loaded / (e.total || 1)) * 100));
          },
        });
        setUploadPhase('processing');
        await queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
        // Start polling for processing status
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
        toast.success('Video uploaded', 'Processing started — HLS, transcript, and assignments will be generated automatically.');
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

    if (newContentData.content_type === 'LINK' && !newContentData.file_url?.trim()) {
      toast.error('Missing URL', 'Please enter a valid link.');
      return;
    }
    if (newContentData.content_type === 'DOCUMENT' && !contentFile && !newContentData.file_url) {
      toast.error('Missing file', 'Please upload a document or select from the media library.');
      return;
    }

    if (newContentData.content_type === 'TEXT') {
      const plainText = newContentData.text_content.replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').trim();
      if (!plainText) {
        toast.error('Missing text', 'Please add text content.');
        return;
      }
      data.append('text_content', newContentData.text_content);
    } else if (newContentData.content_type === 'LINK') {
      data.append('file_url', newContentData.file_url);
    } else if (contentFile) {
      // Upload file first
      const fileUrl = await uploadFile(contentFile, 'content');
      data.append('file_url', fileUrl);
      data.append('file_size', String(contentFile.size));
      // Also register in Media Library so it appears on the Media Library page
      if (newContentData.content_type === 'DOCUMENT') {
        try {
          await adminMediaService.uploadMedia({
            title: newContentData.title || contentFile.name,
            media_type: 'DOCUMENT',
            file_url: fileUrl,
          });
        } catch {
          // Best-effort: don't block content creation if library sync fails
        }
      }
    } else if (newContentData.file_url) {
      // file_url already set (e.g. from media library)
      data.append('file_url', newContentData.file_url);
    }

    contentMutation.mutate({ courseId, moduleId, data });
  };

  const toggleModule = (moduleId: string) => {
    setExpandedModules(prev =>
      prev.includes(moduleId) ? prev.filter(id => id !== moduleId) : [...prev, moduleId]
    );
  };

  const getContentIcon = (type: Content['content_type']) => {
    switch (type) {
      case 'VIDEO':
        return <PlayCircleIcon className="h-5 w-5 text-blue-500" />;
      case 'DOCUMENT':
        return <DocumentTextIcon className="h-5 w-5 text-orange-500" />;
      case 'LINK':
        return <LinkIcon className="h-5 w-5 text-purple-500" />;
      default:
        return <DocumentTextIcon className="h-5 w-5 text-gray-500" />;
    }
  };

  const updateAssignmentQuestion = (questionIndex: number, updater: (question: AdminQuizQuestion) => AdminQuizQuestion) => {
    setAssignmentForm((prev) => {
      const questions = [...(prev.questions || [])];
      questions[questionIndex] = updater(questions[questionIndex]);
      return { ...prev, questions };
    });
  };

  const addAssignmentQuestion = () => {
    setAssignmentForm((prev) => {
      const questions = [...(prev.questions || [])];
      questions.push(buildEmptyQuestion(questions.length + 1));
      return { ...prev, questions };
    });
  };

  const removeAssignmentQuestion = (questionIndex: number) => {
    setAssignmentForm((prev) => {
      const questions = [...(prev.questions || [])];
      questions.splice(questionIndex, 1);
      const reordered = questions.map((q, idx) => ({ ...q, order: idx + 1 }));
      return { ...prev, questions: reordered };
    });
  };

  const resetAssignmentBuilder = () => {
    setIsCreatingNewAssignment(true);
    setSelectedAssignmentId(null);
    setAssignmentForm(buildEmptyAssignmentForm());
    setAiTitleHint('');
    setAiQuestionCount(6);
    setAiIncludeShortAnswer(true);
  };

  const validateAssignmentForm = (): string | null => {
    if (!assignmentForm.title.trim()) return 'Assignment title is required.';
    if (assignmentForm.scope_type === 'MODULE' && !assignmentForm.module_id) return 'Select a module for module-scoped assignments.';
    if (assignmentForm.assignment_type === 'QUIZ') {
      if (!assignmentForm.questions || assignmentForm.questions.length === 0) return 'At least one question is required for quiz assignments.';
      for (let i = 0; i < assignmentForm.questions.length; i += 1) {
        const q = assignmentForm.questions[i];
        if (!q.prompt.trim()) return `Question ${i + 1} prompt is required.`;
        if (q.question_type === 'MCQ') {
          const options = (q.options || []).map((opt) => opt.trim()).filter(Boolean);
          if (options.length < 2) return `Question ${i + 1} needs at least 2 options.`;
          if (q.selection_mode === 'SINGLE') {
            const idx = Number(q.correct_answer?.option_index);
            if (!Number.isInteger(idx) || idx < 0 || idx >= options.length) return `Question ${i + 1} has an invalid correct option.`;
          } else {
            const indices = Array.isArray(q.correct_answer?.option_indices) ? q.correct_answer.option_indices : [];
            if (indices.length < 2) return `Question ${i + 1} needs at least 2 correct options for multi-select.`;
          }
        }
        if (q.question_type === 'TRUE_FALSE' && typeof q.correct_answer?.value !== 'boolean') {
          return `Question ${i + 1} must set True or False as the correct answer.`;
        }
      }
    }
    return null;
  };

  const sanitizeAssignmentQuestions = (questions: AdminQuizQuestion[]) =>
    questions.map((question, index) => ({
      ...question,
      order: index + 1,
      prompt: question.prompt.trim(),
      options: (question.options || []).map((opt) => opt.trim()).filter(Boolean),
      points: Number(question.points || (question.question_type === 'SHORT_ANSWER' ? 2 : 1)),
      correct_answer:
        question.question_type === 'MCQ'
          ? question.selection_mode === 'MULTIPLE'
            ? {
                option_indices: (Array.isArray(question.correct_answer?.option_indices)
                  ? question.correct_answer.option_indices
                  : []
                )
                  .map((value: number) => Number(value))
                  .filter((value: number) => Number.isInteger(value)),
              }
            : { option_index: Number(question.correct_answer?.option_index ?? 0) }
          : question.question_type === 'TRUE_FALSE'
          ? { value: Boolean(question.correct_answer?.value) }
          : {},
    }));

  const handleSaveAssignmentBuilder = () => {
    if (!courseId) return;
    const validationError = validateAssignmentForm();
    if (validationError) {
      toast.error('Assignment validation failed', validationError);
      return;
    }

    const payload: AdminAssignmentPayload = {
      ...assignmentForm,
      title: assignmentForm.title.trim(),
      description: assignmentForm.description || '',
      instructions: assignmentForm.instructions || '',
      module_id: assignmentForm.scope_type === 'MODULE' ? assignmentForm.module_id : null,
      questions: assignmentForm.assignment_type === 'QUIZ'
        ? sanitizeAssignmentQuestions(assignmentForm.questions || [])
        : [],
    };
    if (!payload.due_date) {
      delete payload.due_date;
    }

    if (selectedAssignmentId) {
      updateAssignmentMutation.mutate({ assignmentId: selectedAssignmentId, payload });
    } else {
      createAssignmentMutation.mutate(payload);
    }
  };

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
      <div className="flex items-center justify-between">
        <div className="flex items-center">
          <button
            onClick={() => navigate(courseListPath)}
            className="mr-4 p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {isTeacherAuthoring
                ? isEditing
                  ? 'Edit Authored Course'
                  : 'Create Authored Course'
                : isEditing
                ? 'Edit Course'
                : 'Create Course'}
            </h1>
            <p className="mt-1 text-gray-500">
              {isTeacherAuthoring
                ? isEditing
                  ? 'Update your draft course content'
                  : 'Create a draft course with modules and rich lessons'
                : isEditing
                ? 'Update course details and content'
                : 'Set up a new training course'}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {isEditing && canManageAssignments && (
            <>
              <span
                className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                  course?.is_published
                    ? 'bg-green-100 text-green-800'
                    : 'bg-yellow-100 text-yellow-800'
                }`}
              >
                {course?.is_published ? 'Published' : 'Draft'}
              </span>
              <Button
                variant="outline"
                onClick={() => publishMutation.mutate(!course?.is_published)}
                loading={publishMutation.isPending}
              >
                {course?.is_published ? (
                  <><EyeIcon className="h-4 w-4 mr-1.5" /> Unpublish</>
                ) : (
                  <><GlobeAltIcon className="h-4 w-4 mr-1.5" /> Publish</>
                )}
              </Button>
            </>
          )}
          <Button
            variant="primary"
            onClick={handleSaveCourse}
            loading={courseMutationPending}
          >
            {isEditing ? 'Save Changes' : 'Create Course'}
          </Button>
        </div>
      </div>

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
              {[
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
              ].map((choice) => (
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
            ...(canManageAssignments ? [
              { key: 'assignments', label: 'Assignment Builder', disabled: !isEditing },
              { key: 'audience', label: 'Course Audience', disabled: !isEditing },
            ] : []),
          ].map((tab) => (
            <button
              type="button"
              key={tab.key}
              data-tour={
                tab.key === 'details'
                  ? 'admin-course-editor-tab-details'
                  : tab.key === 'content'
                  ? 'admin-course-editor-tab-content'
                  : tab.key === 'assignments'
                  ? 'admin-course-editor-tab-assignment-builder'
                  : 'admin-course-editor-tab-assignment'
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
      {activeTab === 'details' && (
        <div data-tour="admin-course-details-panel" className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Basic Information</h2>
              
              <div className="space-y-4">
                <Input
                  label="Course Title"
                  name="title"
                  value={formData.title}
                  onChange={handleInputChange}
                  placeholder="e.g., Classroom Management 101"
                  required
                />

                <div>
                  <label htmlFor="course-description" className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <textarea
                    id="course-description"
                    name="description"
                    value={formData.description}
                    onChange={handleInputChange}
                    rows={4}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                    placeholder="Describe what teachers will learn..."
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <Input
                    label="Estimated Hours"
                    name="estimated_hours"
                    type="number"
                    min="0"
                    step="0.5"
                    value={formData.estimated_hours}
                    onChange={handleInputChange}
                  />

                  <Input
                    label="Deadline (Optional)"
                    name="deadline"
                    type="date"
                    value={formData.deadline}
                    onChange={handleInputChange}
                  />
                </div>

                <div className="flex items-center">
                  <input
                    type="checkbox"
                    id="is_mandatory"
                    name="is_mandatory"
                    checked={formData.is_mandatory}
                    onChange={handleInputChange}
                    className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                  />
                  <label htmlFor="is_mandatory" className="ml-2 text-sm text-gray-700">
                    This is a mandatory course for assigned teachers
                  </label>
                </div>
              </div>
            </div>
          </div>

          {/* Thumbnail */}
          <div className="lg:col-span-1">
            <div className="bg-white rounded-xl border border-gray-200 p-6">
              <h2 className="text-lg font-semibold text-gray-900 mb-4">Thumbnail</h2>
              
              <div
                className="aspect-video border-2 border-dashed border-gray-300 rounded-lg flex items-center justify-center overflow-hidden bg-gray-50 cursor-pointer hover:border-primary-500 transition-colors"
                onClick={() => thumbnailInputRef.current?.click()}
              >
                {thumbnailPreview ? (
                  <img
                    src={thumbnailPreview}
                    alt="Thumbnail preview"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="text-center">
                    <PhotoIcon className="h-12 w-12 mx-auto text-gray-400 mb-2" />
                    <p className="text-sm text-gray-500">Click to upload</p>
                    <p className="text-xs text-gray-400">PNG, JPG up to 2MB</p>
                  </div>
                )}
              </div>
              <input
                ref={thumbnailInputRef}
                id="course-thumbnail-upload"
                name="course_thumbnail"
                type="file"
                accept="image/png,image/jpeg,image/jpg"
                onChange={handleThumbnailChange}
                className="hidden"
              />
            </div>
          </div>
        </div>
      )}

      {/* Content Tab */}
      {activeTab === 'content' && isEditing && (
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
              <h3 className="text-lg font-medium text-gray-900 mb-1">No modules yet</h3>
              <p className="text-gray-500">Add your first module to start building lessons</p>
            </div>
          ) : (
            <div className="space-y-3">
              {course?.modules?.map((module, moduleIndex) => {
                const moduleLabel = module.title?.trim() || `Untitled Module ${moduleIndex + 1}`;
                return (
                  <div key={module.id} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
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
                                data: { title: (e.target as HTMLInputElement).value },
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
                    
                    <div className="flex items-center space-x-2" onClick={(e) => e.stopPropagation()}>
                      <span className="text-sm text-gray-500">
                        {module.contents?.length || 0} items
                      </span>
                      <button
                        onClick={() => setEditingModule(editingModule === module.id ? null : module.id)}
                        className="p-1 text-gray-400 hover:text-primary-600 rounded"
                      >
                        <PencilIcon className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setConfirmDelete({ type: 'module', moduleId: module.id, label: moduleLabel })}
                        className="p-1 text-gray-400 hover:text-red-600 rounded"
                      >
                        <TrashIcon className="h-4 w-4" />
                      </button>
                    </div>
                  </div>

                  {/* Module Content */}
                  {expandedModules.includes(module.id) && (
                    <div className="p-4 space-y-3">
                      <div className="rounded-lg border border-gray-200 bg-white p-4">
                        <div className="mb-3 flex items-center justify-between">
                          <h4 className="text-sm font-semibold text-gray-900">Module Description</h4>
                          <div className="flex items-center gap-2">
                            {editingModuleDescriptionId === module.id ? (
                              <>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => cancelModuleDescriptionEdit(module.id)}
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
                              setModuleDescriptionDrafts((prev) => ({ ...prev, [module.id]: html }))
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
                                dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(module.description) }}
                              />
                            ) : (
                              <p className="text-sm text-gray-500">Optional module summary (shown above lesson items).</p>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Content Items */}
                      {module.contents?.map((content) => {
                        const isEditingText = editingTextContentId === content.id && editingTextModuleId === module.id;
                        if (isEditingText && content.content_type === 'TEXT') {
                          return (
                            <div key={content.id} className="rounded-lg border border-blue-200 bg-blue-50 p-4">
                              <div className="mb-2 flex items-center justify-between">
                                <span className="text-sm font-medium text-blue-900">Editing text lesson: {content.title}</span>
                                <div className="flex items-center gap-2">
                                  <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => setShowEditingTextPreview((prev) => !prev)}
                                  >
                                    <EyeIcon className="mr-1 h-4 w-4" />
                                    {showEditingTextPreview ? 'Back to Editor' : 'Preview'}
                                  </Button>
                                  <Button variant="outline" size="sm" onClick={cancelTextContentEdit}>
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
                                Use the toolbar to add links, images, and indentation for clean lesson content.
                              </p>
                              {showEditingTextPreview ? (
                                <div className="rounded-md border border-blue-100 bg-white p-3">
                                  {textContentDraft ? (
                                    <div
                                      className="prose prose-sm max-w-none text-gray-700"
                                      dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(textContentDraft) }}
                                    />
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
                          <div
                            key={content.id}
                            className="flex items-center justify-between rounded-lg bg-gray-50 p-3 transition-colors hover:bg-gray-100"
                          >
                            <div className="min-w-0 flex items-center">
                              {getContentIcon(content.content_type)}
                              <span className="ml-3 truncate text-sm text-gray-900">{content.title}</span>
                              <span className="ml-2 flex-shrink-0 text-xs uppercase text-gray-500">
                                {content.content_type}
                              </span>
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
                                <button
                                  type="button"
                                  onClick={() => startTextContentEdit(module.id, content)}
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
                                onClick={() => setConfirmDelete({ type: 'content', moduleId: module.id, contentId: content.id, label: content.title || 'this content' })}
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
                            <label htmlFor={`new-content-title-${module.id}`} className="sr-only">
                              Content title
                            </label>
                            <input
                              id={`new-content-title-${module.id}`}
                              name="new_content_title"
                              type="text"
                              value={newContentData.title}
                              onChange={(e) => setNewContentData(prev => ({ ...prev, title: e.target.value }))}
                              placeholder="Content title"
                              className="px-3 py-2 border border-gray-300 rounded-lg"
                            />
                            <label htmlFor={`new-content-type-${module.id}`} className="sr-only">
                              Content type
                            </label>
                            <select
                              id={`new-content-type-${module.id}`}
                              name="new_content_type"
                              value={newContentData.content_type}
                              onChange={(e) => {
                                const newType = e.target.value as Content['content_type'];
                                setNewContentData(prev => ({
                                  ...prev,
                                  content_type: newType,
                                  // Clear file_url when switching types to prevent stale values
                                  file_url: '',
                                  text_content: newType === 'TEXT' ? prev.text_content : '',
                                }));
                                setContentFile(null);
                                setShowNewTextPreview(false);
                              }}
                              className="px-3 py-2 border border-gray-300 rounded-lg"
                            >
                              <option value="VIDEO" disabled={!canUploadVideo}>Video{!canUploadVideo ? ' (Upgrade)' : ''}</option>
                              <option value="DOCUMENT">Document</option>
                              <option value="TEXT">Text</option>
                              <option value="LINK">Link</option>
                            </select>
                          </div>

                          {newContentData.content_type === 'TEXT' && (
                            <>
                              <div className="flex items-center justify-between">
                                <p className="text-xs text-blue-700">
                                  Add rich text with links, images, and formatting. Use preview before saving.
                                </p>
                                <Button
                                  variant="outline"
                                  size="sm"
                                  onClick={() => setShowNewTextPreview((prev) => !prev)}
                                >
                                  <EyeIcon className="mr-1 h-4 w-4" />
                                  {showNewTextPreview ? 'Back to Editor' : 'Preview'}
                                </Button>
                              </div>
                              {showNewTextPreview ? (
                                <div className="rounded-md border border-gray-200 bg-white p-3">
                                  {newContentData.text_content ? (
                                    <div
                                      className="prose prose-sm max-w-none text-gray-700"
                                      dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(newContentData.text_content) }}
                                    />
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
                              <label htmlFor={`new-content-link-${module.id}`} className="sr-only">
                                Link URL
                              </label>
                              <input
                                id={`new-content-link-${module.id}`}
                                name="new_content_link"
                                type="url"
                                value={newContentData.file_url}
                                onChange={(e) => setNewContentData(prev => ({ ...prev, file_url: e.target.value }))}
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
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => contentFileInputRef.current?.click()}
                              >
                                {contentFile ? contentFile.name : newContentData.file_url ? 'From Library' : 'Choose File'}
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => openLibraryPicker(newContentData.content_type === 'VIDEO' ? 'VIDEO' : 'DOCUMENT')}
                              >
                                <FolderIcon className="h-4 w-4 mr-1" />
                                From Library
                              </Button>
                            </div>
                          )}

                          {newContentData.content_type === 'LINK' && (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => openLibraryPicker('LINK')}
                            >
                              <FolderIcon className="h-4 w-4 mr-1" />
                              From Library
                            </Button>
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
                              disabled={uploadPhase === 'uploading' || uploadPhase === 'processing'}
                            >
                              <XMarkIcon className="h-4 w-4 mr-1" />
                              Cancel
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
                      ) : (
                        <button
                          onClick={() => {
                            setAddingContentToModule(module.id);
                            setShowNewTextPreview(false);
                          }}
                          className="flex items-center justify-center w-full p-3 border-2 border-dashed border-gray-300 rounded-lg text-gray-500 hover:border-primary-500 hover:text-primary-600 transition-colors"
                        >
                          <PlusIcon className="h-5 w-5 mr-2" />
                          Add Content
                        </button>
                      )}
                    </div>
                  )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Assignment Builder Tab */}
      {activeTab === 'assignments' && canManageAssignments && isEditing && (
        <div data-tour="admin-course-assignment-builder-panel" className="grid grid-cols-1 gap-6 xl:grid-cols-5">
          <div className="xl:col-span-2 bg-white rounded-xl border border-gray-200 p-4 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-gray-900">Assignment Builder</h2>
              <Button variant="outline" size="sm" onClick={resetAssignmentBuilder}>
                + New
              </Button>
            </div>
            <div className="flex items-center gap-2">
              {(['ALL', 'COURSE', 'MODULE'] as const).map((scope) => (
                <button
                  key={scope}
                  type="button"
                  onClick={() => setAssignmentScopeFilter(scope)}
                  className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                    assignmentScopeFilter === scope
                      ? 'bg-primary-600 text-white'
                      : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                >
                  {scope}
                </button>
              ))}
            </div>
            <div className="max-h-[560px] overflow-y-auto space-y-2">
              {assignmentListLoading ? (
                <div className="py-8 text-center text-sm text-gray-500">Loading assignments…</div>
              ) : assignmentList.length === 0 ? (
                <div className="rounded-lg border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
                  No assignments yet. Create your first one.
                </div>
              ) : (
                assignmentList.map((assignment: AdminAssignment) => (
                  <button
                    key={assignment.id}
                    type="button"
                    onClick={() => {
                      setIsCreatingNewAssignment(false);
                      setSelectedAssignmentId(assignment.id);
                    }}
                    className={`w-full rounded-lg border p-3 text-left transition-colors ${
                      selectedAssignmentId === assignment.id
                        ? 'border-primary-500 bg-primary-50'
                        : 'border-gray-200 hover:border-gray-300'
                    }`}
                  >
                    <p className="text-sm font-semibold text-gray-900 truncate">{assignment.title}</p>
                    <p className="mt-1 text-xs text-gray-500">
                      {assignment.assignment_type === 'QUIZ' ? 'Quiz' : 'Written'} • {assignment.scope_type === 'MODULE' ? assignment.module_title || 'Module' : 'Course'}
                    </p>
                  </button>
                ))
              )}
            </div>
          </div>

          <div className="xl:col-span-3 bg-white rounded-xl border border-gray-200 p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-gray-900">
                {selectedAssignmentId ? 'Edit Assignment' : 'Create Assignment'}
              </h3>
              {selectedAssignmentId && (
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => deleteAssignmentMutation.mutate(selectedAssignmentId)}
                  loading={deleteAssignmentMutation.isPending}
                >
                  Delete
                </Button>
              )}
            </div>

            {selectedAssignmentLoading ? (
              <div className="py-8 text-center text-sm text-gray-500">Loading assignment details…</div>
            ) : (
              <>
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <Input
                    label="Assignment Title"
                    name="assignment_title"
                    value={assignmentForm.title}
                    onChange={(e) => setAssignmentForm((prev) => ({ ...prev, title: e.target.value }))}
                    placeholder="Assignment title"
                    required
                  />
                  <div>
                    <label htmlFor="assignment-type" className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                    <select
                      id="assignment-type"
                      name="assignment_type"
                      value={assignmentForm.assignment_type}
                      onChange={(e) => {
                        const nextType = e.target.value as AdminAssignmentType;
                        setAssignmentForm((prev) => ({
                          ...prev,
                          assignment_type: nextType,
                          questions: nextType === 'QUIZ' ? (prev.questions?.length ? prev.questions : [buildEmptyQuestion(1)]) : [],
                        }));
                      }}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    >
                      <option value="QUIZ">Quiz (Objective)</option>
                      <option value="WRITTEN">Written Assignment</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor="assignment-scope" className="block text-sm font-medium text-gray-700 mb-1">Scope</label>
                    <select
                      id="assignment-scope"
                      name="assignment_scope"
                      value={assignmentForm.scope_type}
                      onChange={(e) => {
                        const scope = e.target.value as 'COURSE' | 'MODULE';
                        setAssignmentForm((prev) => ({
                          ...prev,
                          scope_type: scope,
                          module_id: scope === 'MODULE' ? prev.module_id || course?.modules?.[0]?.id || null : null,
                        }));
                      }}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    >
                      <option value="COURSE">Course level</option>
                      <option value="MODULE">Module level</option>
                    </select>
                  </div>
                  {assignmentForm.scope_type === 'MODULE' && (
                    <div>
                      <label htmlFor="assignment-module" className="block text-sm font-medium text-gray-700 mb-1">Module</label>
                      <select
                        id="assignment-module"
                        name="assignment_module"
                        value={assignmentForm.module_id || ''}
                        onChange={(e) => setAssignmentForm((prev) => ({ ...prev, module_id: e.target.value || null }))}
                        className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                      >
                        <option value="">Select module</option>
                        {course?.modules?.map((module) => (
                          <option key={module.id} value={module.id}>{module.title}</option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>

                <div>
                  <label htmlFor="assignment-description" className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                  <textarea
                    id="assignment-description"
                    value={assignmentForm.description}
                    onChange={(e) => setAssignmentForm((prev) => ({ ...prev, description: e.target.value }))}
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    placeholder="Assignment description"
                  />
                </div>

                <div>
                  <label htmlFor="assignment-instructions" className="block text-sm font-medium text-gray-700 mb-1">Instructions</label>
                  <textarea
                    id="assignment-instructions"
                    value={assignmentForm.instructions}
                    onChange={(e) => setAssignmentForm((prev) => ({ ...prev, instructions: e.target.value }))}
                    rows={3}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    placeholder="What should teachers submit?"
                  />
                </div>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
                  <Input
                    label="Due Date"
                    name="assignment_due_date"
                    type="datetime-local"
                    value={assignmentForm.due_date ? assignmentForm.due_date.slice(0, 16) : ''}
                    onChange={(e) => setAssignmentForm((prev) => ({ ...prev, due_date: e.target.value || null }))}
                  />
                  <Input
                    label="Max Score"
                    name="assignment_max_score"
                    type="number"
                    min="0"
                    value={assignmentForm.max_score}
                    onChange={(e) => setAssignmentForm((prev) => ({ ...prev, max_score: Number(e.target.value || 0) }))}
                  />
                  <Input
                    label="Passing Score"
                    name="assignment_passing_score"
                    type="number"
                    min="0"
                    value={assignmentForm.passing_score}
                    onChange={(e) => setAssignmentForm((prev) => ({ ...prev, passing_score: Number(e.target.value || 0) }))}
                  />
                  <div className="flex items-end pb-2">
                    <label className="inline-flex items-center text-sm text-gray-700">
                      <input
                        type="checkbox"
                        checked={assignmentForm.is_mandatory}
                        onChange={(e) => setAssignmentForm((prev) => ({ ...prev, is_mandatory: e.target.checked }))}
                        className="mr-2 h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                      />
                      Mandatory
                    </label>
                  </div>
                </div>

                {assignmentForm.assignment_type === 'QUIZ' && (
                  <div className="space-y-4 rounded-xl border border-gray-200 p-4">
                    <div className="flex items-center justify-between">
                      <h4 className="text-sm font-semibold text-gray-900">Quiz Questions</h4>
                      <Button variant="outline" size="sm" onClick={addAssignmentQuestion}>+ Add Question</Button>
                    </div>
                    {(assignmentForm.questions || []).map((question, questionIndex) => (
                      <div key={`${question.order}-${questionIndex}`} className="rounded-lg border border-gray-200 p-4 space-y-3">
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-medium text-gray-700">Question {questionIndex + 1}</p>
                          {(assignmentForm.questions || []).length > 1 && (
                            <button
                              type="button"
                              onClick={() => removeAssignmentQuestion(questionIndex)}
                              className="text-xs font-medium text-red-600 hover:text-red-700"
                            >
                              Remove
                            </button>
                          )}
                        </div>
                        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                          <div className="md:col-span-2">
                            <label className="block text-xs font-medium text-gray-600 mb-1">Prompt</label>
                            <textarea
                              value={question.prompt}
                              onChange={(e) => updateAssignmentQuestion(questionIndex, (q) => ({ ...q, prompt: e.target.value }))}
                              rows={2}
                              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                            />
                          </div>
                          <div>
                            <label className="block text-xs font-medium text-gray-600 mb-1">Type</label>
                            <select
                              value={question.question_type}
                              onChange={(e) => {
                                const qType = e.target.value as AdminQuizQuestion['question_type'];
                                updateAssignmentQuestion(questionIndex, (q) => ({
                                  ...q,
                                  question_type: qType,
                                  selection_mode: qType === 'MCQ' ? q.selection_mode : 'SINGLE',
                                  options: qType === 'MCQ' ? (q.options.length ? q.options : ['Option 1', 'Option 2']) : qType === 'TRUE_FALSE' ? ['True', 'False'] : [],
                                  correct_answer:
                                    qType === 'MCQ'
                                      ? { option_index: 0 }
                                      : qType === 'TRUE_FALSE'
                                      ? { value: true }
                                      : {},
                                  points: qType === 'SHORT_ANSWER' ? 2 : 1,
                                }));
                              }}
                              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
                            >
                              <option value="MCQ">MCQ</option>
                              <option value="TRUE_FALSE">True / False</option>
                              <option value="SHORT_ANSWER">Short Answer</option>
                            </select>
                          </div>
                        </div>

                        {question.question_type === 'MCQ' && (
                          <div className="space-y-3">
                            <div className="flex items-center gap-3">
                              <label className="text-xs font-medium text-gray-600">Mode</label>
                              <select
                                value={question.selection_mode}
                                onChange={(e) => {
                                  const mode = e.target.value as 'SINGLE' | 'MULTIPLE';
                                  updateAssignmentQuestion(questionIndex, (q) => ({
                                    ...q,
                                    selection_mode: mode,
                                    correct_answer: mode === 'MULTIPLE' ? { option_indices: [0, 1] } : { option_index: 0 },
                                  }));
                                }}
                                className="px-2 py-1 border border-gray-300 rounded text-xs"
                              >
                                <option value="SINGLE">Single Choice</option>
                                <option value="MULTIPLE">Multiple Choice</option>
                              </select>
                            </div>
                            {(question.options || []).map((option, optionIndex) => (
                              <div key={optionIndex} className="flex items-center gap-2">
                                {question.selection_mode === 'SINGLE' ? (
                                  <input
                                    type="radio"
                                    name={`q-${questionIndex}-single`}
                                    checked={question.correct_answer?.option_index === optionIndex}
                                    onChange={() => updateAssignmentQuestion(questionIndex, (q) => ({ ...q, correct_answer: { option_index: optionIndex } }))}
                                    className="h-4 w-4 text-primary-600"
                                  />
                                ) : (
                                  <input
                                    type="checkbox"
                                    checked={Array.isArray(question.correct_answer?.option_indices) && question.correct_answer.option_indices.includes(optionIndex)}
                                    onChange={(e) => {
                                      const current = Array.isArray(question.correct_answer?.option_indices)
                                        ? question.correct_answer.option_indices
                                        : [];
                                      const next = e.target.checked
                                        ? [...current, optionIndex]
                                        : current.filter((value: number) => value !== optionIndex);
                                      updateAssignmentQuestion(questionIndex, (q) => ({ ...q, correct_answer: { option_indices: next } }));
                                    }}
                                    className="h-4 w-4 text-primary-600 rounded"
                                  />
                                )}
                                <input
                                  type="text"
                                  value={option}
                                  onChange={(e) => updateAssignmentQuestion(questionIndex, (q) => {
                                    const options = [...(q.options || [])];
                                    options[optionIndex] = e.target.value;
                                    return { ...q, options };
                                  })}
                                  className="flex-1 px-2 py-1 border border-gray-300 rounded text-sm"
                                />
                              </div>
                            ))}
                            <button
                              type="button"
                              onClick={() => updateAssignmentQuestion(questionIndex, (q) => ({ ...q, options: [...(q.options || []), `Option ${(q.options?.length || 0) + 1}`] }))}
                              className="text-xs font-medium text-primary-700 hover:text-primary-800"
                            >
                              + Add option
                            </button>
                          </div>
                        )}

                        {question.question_type === 'TRUE_FALSE' && (
                          <div className="flex items-center gap-4">
                            {[true, false].map((value) => (
                              <label key={String(value)} className="inline-flex items-center gap-2 text-sm text-gray-700">
                                <input
                                  type="radio"
                                  name={`q-${questionIndex}-bool`}
                                  checked={question.correct_answer?.value === value}
                                  onChange={() => updateAssignmentQuestion(questionIndex, (q) => ({ ...q, correct_answer: { value } }))}
                                  className="h-4 w-4 text-primary-600"
                                />
                                {value ? 'True' : 'False'}
                              </label>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                <div className="rounded-xl border border-dashed border-gray-300 bg-gray-50 p-4 space-y-3">
                  <div className="flex items-center gap-2">
                    <SparklesIcon className="h-5 w-5 text-primary-600" />
                    <h4 className="text-sm font-semibold text-gray-900">AI Assignment Generation</h4>
                  </div>
                  <p className="text-xs text-gray-600">
                    {aiSourceState.summary}. Uses video transcripts for video lessons and text extraction for document/text content.
                  </p>
                  <p className="text-xs text-gray-500">Model: {aiModelLabel}</p>
                  {!aiSourceState.enabled && (
                    <p className="text-xs font-medium text-amber-700">{aiSourceState.reason}</p>
                  )}
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                    <Input
                      label="Question Count"
                      name="ai_question_count"
                      type="number"
                      min="2"
                      max="20"
                      value={aiQuestionCount}
                      onChange={(e) => {
                        const parsed = Number(e.target.value || 6);
                        const normalized = Number.isFinite(parsed) ? Math.max(2, Math.min(20, parsed)) : 6;
                        setAiQuestionCount(normalized);
                      }}
                    />
                    <Input
                      label="Title Hint (Optional)"
                      name="ai_title_hint"
                      value={aiTitleHint}
                      onChange={(e) => setAiTitleHint(e.target.value)}
                      placeholder="e.g., Module Assessment"
                    />
                    <div className="flex items-end pb-2">
                      <label className="inline-flex items-center text-sm text-gray-700">
                        <input
                          type="checkbox"
                          checked={aiIncludeShortAnswer}
                          onChange={(e) => setAiIncludeShortAnswer(e.target.checked)}
                          className="mr-2 h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                        />
                        Include short-answer
                      </label>
                    </div>
                  </div>
                  <div className="flex justify-end">
                    <Button
                      variant="outline"
                      onClick={() => aiGenerateMutation.mutate()}
                      loading={aiGenerateMutation.isPending}
                      disabled={!aiSourceState.enabled}
                    >
                      Generate with AI
                    </Button>
                  </div>
                </div>

                <div className="rounded-lg border border-gray-200 p-3">
                  <p className="text-xs font-semibold text-gray-600 mb-2">Coming next</p>
                  <div className="flex flex-wrap gap-2">
                    <span className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-600">Drag-and-drop</span>
                    <span className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-600">Match-the-pairs</span>
                  </div>
                </div>

                <div className="flex justify-end gap-3">
                  <Button variant="outline" onClick={resetAssignmentBuilder}>
                    Reset
                  </Button>
                  <Button
                    variant="primary"
                    onClick={handleSaveAssignmentBuilder}
                    loading={createAssignmentMutation.isPending || updateAssignmentMutation.isPending}
                  >
                    {selectedAssignmentId ? 'Save Assignment' : 'Create Assignment'}
                  </Button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Course Audience Tab */}
      {activeTab === 'audience' && canManageAssignments && (
        <div data-tour="admin-course-assignment-panel" className="bg-white rounded-xl border border-gray-200 p-6 space-y-6">
          <h2 className="text-lg font-semibold text-gray-900">Course Audience</h2>
          
          {/* Assign to All */}
          <div className="flex items-center justify-between p-4 bg-gray-50 rounded-lg">
            <div className="flex items-center">
              <UsersIcon className="h-6 w-6 text-primary-600 mr-3" />
              <div>
                <p className="font-medium text-gray-900">Assign to All Teachers</p>
                <p className="text-sm text-gray-500">
                  All current and future teachers will have access
                </p>
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                name="assigned_to_all"
                checked={formData.assigned_to_all}
                onChange={handleInputChange}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-primary-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary-600"></div>
            </label>
          </div>

          {/* Specific Audience */}
          {!formData.assigned_to_all && (
            <>
              {/* Groups */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <label className="flex items-center text-sm font-medium text-gray-700">
                    <UserGroupIcon className="h-5 w-5 mr-2 text-gray-400" />
                    Assign to Groups
                  </label>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setCreateGroupOpen(true)}
                  >
                    + Create group
                  </Button>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
                  {groups?.map((group) => (
                    <label
                      key={group.id}
                      className={`flex items-center p-3 border rounded-lg cursor-pointer transition-colors ${
                        formData.assigned_groups.includes(group.id)
                          ? 'border-primary-500 bg-primary-50'
                          : 'border-gray-200 hover:border-gray-300'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={formData.assigned_groups.includes(group.id)}
                        onChange={(e) => {
                          setFormData(prev => ({
                            ...prev,
                            assigned_groups: e.target.checked
                              ? [...prev.assigned_groups, group.id]
                              : prev.assigned_groups.filter(id => id !== group.id),
                          }));
                        }}
                        className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                      />
                      <span className="ml-2 text-sm text-gray-900">{group.name}</span>
                    </label>
                  ))}
                </div>
                {groups?.length === 0 && (
                  <p className="text-sm text-gray-500">No groups created yet</p>
                )}
              </div>

              {/* Individual Teachers */}
              <div>
                <label className="flex items-center text-sm font-medium text-gray-700 mb-2">
                  <UsersIcon className="h-5 w-5 mr-2 text-gray-400" />
                  Assign to Individual Teachers
                </label>
                <div className="max-h-60 overflow-y-auto border border-gray-200 rounded-lg">
                  {teachers?.map((teacher) => (
                    <label
                      key={teacher.id}
                      className={`flex items-center p-3 border-b last:border-b-0 cursor-pointer hover:bg-gray-50 ${
                        formData.assigned_teachers.includes(teacher.id) ? 'bg-primary-50' : ''
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={formData.assigned_teachers.includes(teacher.id)}
                        onChange={(e) => {
                          setFormData(prev => ({
                            ...prev,
                            assigned_teachers: e.target.checked
                              ? [...prev.assigned_teachers, teacher.id]
                              : prev.assigned_teachers.filter(id => id !== teacher.id),
                          }));
                        }}
                        className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 rounded"
                      />
                      <div className="ml-3">
                        <p className="text-sm font-medium text-gray-900">
                          {teacher.first_name} {teacher.last_name}
                        </p>
                        <p className="text-xs text-gray-500">{teacher.email}</p>
                      </div>
                    </label>
                  ))}
                </div>
                {teachers?.length === 0 && (
                  <p className="text-sm text-gray-500">No teachers found</p>
                )}
              </div>
            </>
          )}

          {/* Summary */}
          <div className="p-4 bg-blue-50 rounded-lg">
            <p className="text-sm text-blue-800">
              <strong>Audience Summary:</strong>{' '}
              {formData.assigned_to_all
                ? 'All teachers in your school will have access to this course.'
                : `${formData.assigned_groups.length} group(s) and ${formData.assigned_teachers.length} individual teacher(s) selected.`}
            </p>
          </div>

          {/* Inline Create Group Modal */}
          {createGroupOpen && (
            <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
              <div className="bg-white rounded-xl p-6 max-w-lg w-full mx-4">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-gray-900">Create Group</h3>
                  <button
                    onClick={() => setCreateGroupOpen(false)}
                    className="text-gray-400 hover:text-gray-600"
                  >
                    <XMarkIcon className="h-6 w-6" />
                  </button>
                </div>

                <div className="space-y-4">
                  <Input
                    label="Group name"
                    name="group_name"
                    value={createGroupForm.name}
                    onChange={(e) => setCreateGroupForm({ ...createGroupForm, name: e.target.value })}
                    placeholder="e.g., Grade 9, Math Teachers"
                  />
                  <Input
                    label="Description"
                    name="group_description"
                    value={createGroupForm.description}
                    onChange={(e) => setCreateGroupForm({ ...createGroupForm, description: e.target.value })}
                    placeholder="Optional"
                  />
                  <div>
                    <label htmlFor="group-type" className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                    <select
                      id="group-type"
                      name="group_type"
                      value={createGroupForm.group_type}
                      onChange={(e) => setCreateGroupForm({ ...createGroupForm, group_type: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                    >
                      <option value="CUSTOM">Custom</option>
                      <option value="SUBJECT">Subject</option>
                      <option value="GRADE">Grade</option>
                      <option value="DEPARTMENT">Department</option>
                    </select>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-3 mt-6">
                  <Button variant="outline" onClick={() => setCreateGroupOpen(false)}>
                    Cancel
                  </Button>
                  <Button
                    variant="primary"
                    onClick={() =>
                      createGroupMutation.mutate({
                        name: createGroupForm.name,
                        description: createGroupForm.description,
                        group_type: createGroupForm.group_type,
                      })
                    }
                    disabled={!createGroupForm.name.trim()}
                    loading={createGroupMutation.isPending}
                  >
                    Create
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Content Preview Modal - outside tab conditionals so it can render from any tab */}
      {previewContent && (() => {
        const backendOrigin = (process.env.REACT_APP_API_URL || 'http://localhost:8000/api').replace(/\/api\/?$/, '');
        const resolveUrl = (u: string | null) => {
          if (!u) return '';
          if (u.startsWith('http')) return u;
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
                    <HlsVideoPlayer
                      src={resolveUrl(c.file_url)}
                      className="w-full rounded-lg bg-black aspect-video"
                    />
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
                      <a
                        href={c.file_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700"
                      >
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
                      <div
                        className="p-4 bg-gray-50 rounded-lg text-gray-700 leading-relaxed"
                        dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(c.text_content) }}
                      />
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

      {/* Media Library Picker Modal */}
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
                    onClick={() => {
                      setLibraryFilter(filter);
                      void fetchLibraryAssets(librarySearch, filter);
                    }}
                    className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      libraryFilter === filter
                        ? 'bg-primary-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
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
                  onChange={async (e) => {
                    const v = e.target.value;
                    setLibrarySearch(v);
                    await fetchLibraryAssets(v, libraryFilter);
                  }}
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
                        // Fill content form from library asset
                        setNewContentData(prev => ({
                          ...prev,
                          content_type: asset.media_type,
                          title: prev.title || asset.title,
                          file_url: asset.file_url,
                        }));
                        setContentFile(null); // clear any uploaded file
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
