// src/pages/admin/CourseEditorPage.tsx

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Input, Loading, useToast, HlsVideoPlayer } from '../../components/common';
import { useTenantStore } from '../../stores/tenantStore';
import { adminService } from '../../services/adminService';
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
  is_mandatory: boolean;
  deadline: string | null;
  estimated_hours: number;
  assigned_to_all: boolean;
  assigned_groups: string[];
  assigned_teachers: string[];
  is_published: boolean;
  modules: Module[];
}

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
  const response = await api.post('/courses/', data, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

const updateCourse = async ({ id, data }: { id: string; data: FormData }): Promise<Course> => {
  const response = await api.patch(`/courses/${id}/`, data, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
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
  const response = await api.post(`/courses/${courseId}/modules/${moduleId}/contents/`, data, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data;
};

// TODO: implement inline content editing
// const updateContent = async ({ courseId, moduleId, contentId, data }: { courseId: string; moduleId: string; contentId: string; data: FormData }): Promise<Content> => {
//   const response = await api.patch(`/courses/${courseId}/modules/${moduleId}/contents/${contentId}/`, data, {
//     headers: { 'Content-Type': 'multipart/form-data' },
//   });
//   return response.data;
// };

const deleteContent = async ({ courseId, moduleId, contentId }: { courseId: string; moduleId: string; contentId: string }): Promise<void> => {
  await api.delete(`/courses/${courseId}/modules/${moduleId}/contents/${contentId}/`);
};

const uploadFile = async (file: File, type: 'thumbnail' | 'content'): Promise<string> => {
  const formData = new FormData();
  formData.append('file', file);
  
  const endpoint = type === 'thumbnail' ? '/uploads/course-thumbnail/' : '/uploads/content-file/';
  const response = await api.post(endpoint, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return response.data.url;
};

export const CourseEditorPage: React.FC = () => {
  const toast = useToast();
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const thumbnailInputRef = useRef<HTMLInputElement>(null);
  const contentFileInputRef = useRef<HTMLInputElement>(null);
  const { hasFeature } = useTenantStore();
  const canUploadVideo = hasFeature('video_upload');

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

  useEffect(() => {
    if (!pollingContentId || !pollingModuleId || !courseId) return;
    pollingRef.current = setInterval(async () => {
      try {
        const data = await adminService.getVideoStatus(courseId, pollingModuleId, pollingContentId);
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
      } catch { /* ignore polling errors */ }
    }, 5000);
    return () => stopPolling();
  }, [pollingContentId, pollingModuleId, courseId, stopPolling, toast, queryClient]);
  
  const [activeTab, setActiveTab] = useState<'details' | 'content' | 'assignment'>('details');
  const [thumbnailPreview, setThumbnailPreview] = useState<string | null>(null);
  const [thumbnailFile, setThumbnailFile] = useState<File | null>(null);
  const [expandedModules, setExpandedModules] = useState<string[]>([]);
  const [editingModule, setEditingModule] = useState<string | null>(null);
  // const [editingContent, setEditingContent] = useState<string | null>(null); // TODO: implement inline content editing
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

  // Fetch course if editing
  const { data: course, isLoading: courseLoading } = useQuery({
    queryKey: ['adminCourse', courseId],
    queryFn: () => fetchCourse(courseId!),
    enabled: isEditing,
  });

  // Fetch teachers and groups for assignment
  const { data: teachers } = useQuery({
    queryKey: ['adminTeachers'],
    queryFn: fetchTeachers,
  });

  const { data: groups } = useQuery({
    queryKey: ['adminGroups'],
    queryFn: fetchGroups,
  });

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
      if (course.thumbnail) {
        setThumbnailPreview(course.thumbnail);
      }
      // Expand all modules by default when editing
      if (course.modules) {
        setExpandedModules(course.modules.map(m => m.id));
      }
    }
  }, [course]);

  // Mutations
  const createCourseMutation = useMutation({
    mutationFn: createCourse,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['adminCourses'] });
      queryClient.invalidateQueries({ queryKey: ['adminDashboardStats'] });
      toast.success('Course created', 'Now add modules and content.');
      navigate(`/admin/courses/${data.id}/edit`);
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

  const moduleMutation = useMutation({
    mutationFn: createModule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
      setNewModuleTitle('');
      toast.success('Module added', 'Now add content to this module.');
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
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
      toast.success('Content added', 'Content has been added to the module.');
    },
    onError: () => {
      toast.error('Failed to add content', 'Please try again.');
    },
  });

  // TODO: implement inline content editing
  // const updateContentMutation = useMutation({
  //   mutationFn: updateContent,
  //   onSuccess: () => {
  //     queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
  //   },
  // });

  const deleteContentMutation = useMutation({
    mutationFn: deleteContent,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminCourse', courseId] });
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
  const [libraryAssets, setLibraryAssets] = useState<MediaAsset[]>([]);

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

  const handleSaveCourse = async () => {
    const data = new FormData();
    data.append('title', formData.title);
    data.append('description', formData.description);
    data.append('is_mandatory', String(formData.is_mandatory));
    if (formData.deadline) data.append('deadline', formData.deadline);
    data.append('estimated_hours', String(formData.estimated_hours));
    data.append('assigned_to_all', String(formData.assigned_to_all));
    
    if (!formData.assigned_to_all) {
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
    if (!newModuleTitle.trim() || !courseId) return;
    moduleMutation.mutate({
      courseId,
      data: {
        title: newModuleTitle,
        description: '',
        order: (course?.modules?.length || 0) + 1,
      },
    });
  };

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
        const res = await api.post(`/courses/${courseId}/modules/${moduleId}/contents/video-upload/`, fd, {
          headers: { 'Content-Type': 'multipart/form-data' },
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

    if (newContentData.content_type === 'TEXT') {
      data.append('text_content', newContentData.text_content);
    } else if (newContentData.content_type === 'LINK') {
      data.append('file_url', newContentData.file_url);
    } else if (contentFile) {
      // Upload file first
      const fileUrl = await uploadFile(contentFile, 'content');
      data.append('file_url', fileUrl);
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
            onClick={() => navigate('/admin/courses')}
            className="mr-4 p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {isEditing ? 'Edit Course' : 'Create Course'}
            </h1>
            <p className="mt-1 text-gray-500">
              {isEditing ? 'Update course details and content' : 'Set up a new training course'}
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {isEditing && (
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

      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          {[
            { key: 'details', label: 'Details' },
            { key: 'content', label: 'Content', disabled: !isEditing },
            { key: 'assignment', label: 'Assignment' },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => !tab.disabled && setActiveTab(tab.key as any)}
              disabled={tab.disabled}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
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
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
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
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <textarea
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
        <div className="space-y-4">
          {/* Add Module */}
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <div className="flex items-center space-x-3">
              <input
                type="text"
                value={newModuleTitle}
                onChange={(e) => setNewModuleTitle(e.target.value)}
                placeholder="New module title..."
                className="flex-1 px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                onKeyPress={(e) => e.key === 'Enter' && handleAddModule()}
              />
              <Button
                variant="primary"
                onClick={handleAddModule}
                disabled={!newModuleTitle.trim()}
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
              <p className="text-gray-500">Start by adding your first module above</p>
            </div>
          ) : (
            <div className="space-y-3">
              {course?.modules?.map((module, moduleIndex) => (
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
                          type="text"
                          defaultValue={module.title}
                          className="px-2 py-1 border border-gray-300 rounded"
                          onClick={(e) => e.stopPropagation()}
                          onKeyPress={(e) => {
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
                          Module {moduleIndex + 1}: {module.title}
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
                        onClick={() => {
                          if (window.confirm('Delete this module and all its content?')) {
                            deleteModuleMutation.mutate({ courseId: courseId!, moduleId: module.id });
                          }
                        }}
                        className="p-1 text-gray-400 hover:text-red-600 rounded"
                      >
                        <TrashIcon className="h-4 w-4" />
                      </button>
                    </div>
                  </div>

                  {/* Module Content */}
                  {expandedModules.includes(module.id) && (
                    <div className="p-4 space-y-3">
                      {/* Content Items */}
                      {module.contents?.map((content, contentIndex) => (
                        <div
                          key={content.id}
                          className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                        >
                          <div className="flex items-center min-w-0">
                            {getContentIcon(content.content_type)}
                            <span className="ml-3 text-sm text-gray-900 truncate">{content.title}</span>
                            <span className="ml-2 text-xs text-gray-500 uppercase flex-shrink-0">
                              {content.content_type}
                            </span>
                            {/* Video processing status badge */}
                            {content.content_type === 'VIDEO' && content.video_status && (
                              content.video_status === 'READY' ? (
                                <span className="ml-2 inline-flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-50 rounded-full px-2 py-0.5">
                                  <CheckCircleIcon className="h-3 w-3" /> Ready
                                </span>
                              ) : content.video_status === 'FAILED' ? (
                                <span className="ml-2 inline-flex items-center gap-1 text-xs font-medium text-red-700 bg-red-50 rounded-full px-2 py-0.5" title="Processing failed">
                                  <ExclamationCircleIcon className="h-3 w-3" /> Failed
                                </span>
                              ) : (
                                <span className="ml-2 inline-flex items-center gap-1 text-xs font-medium text-amber-700 bg-amber-50 rounded-full px-2 py-0.5 animate-pulse">
                                  <ArrowPathIcon className="h-3 w-3 animate-spin" /> Processing
                                </span>
                              )
                            )}
                          </div>
                          <div className="flex items-center space-x-1 flex-shrink-0">
                            <button
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                setPreviewContent(content);
                              }}
                              className="p-1 text-gray-400 hover:text-primary-600 rounded"
                              title="Preview"
                            >
                              <EyeIcon className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => {
                                if (window.confirm('Delete this content?')) {
                                  deleteContentMutation.mutate({
                                    courseId: courseId!,
                                    moduleId: module.id,
                                    contentId: content.id,
                                  });
                                }
                              }}
                              className="p-1 text-gray-400 hover:text-red-600 rounded"
                            >
                              <TrashIcon className="h-4 w-4" />
                            </button>
                          </div>
                        </div>
                      ))}

                      {/* Add Content Form */}
                      {addingContentToModule === module.id ? (
                        <div className="p-4 bg-blue-50 rounded-lg space-y-3">
                          <div className="grid grid-cols-2 gap-3">
                            <input
                              type="text"
                              value={newContentData.title}
                              onChange={(e) => setNewContentData(prev => ({ ...prev, title: e.target.value }))}
                              placeholder="Content title"
                              className="px-3 py-2 border border-gray-300 rounded-lg"
                            />
                            <select
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
                            <textarea
                              value={newContentData.text_content}
                              onChange={(e) => setNewContentData(prev => ({ ...prev, text_content: e.target.value }))}
                              placeholder="Enter text content..."
                              rows={4}
                              className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                            />
                          )}

                          {newContentData.content_type === 'LINK' && (
                            <input
                              type="url"
                              value={newContentData.file_url}
                              onChange={(e) => setNewContentData(prev => ({ ...prev, file_url: e.target.value }))}
                              placeholder="https://..."
                              className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                            />
                          )}

                          {(newContentData.content_type === 'VIDEO' || newContentData.content_type === 'DOCUMENT') && (
                            <div className="flex items-center gap-2">
                              <input
                                ref={contentFileInputRef}
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
                                onClick={async () => {
                                  const mediaType = newContentData.content_type === 'VIDEO' ? 'VIDEO' : 'DOCUMENT';
                                  try {
                                    const res = await adminMediaService.listMedia({ media_type: mediaType, page_size: 50 });
                                    setLibraryAssets(res.results);
                                  } catch { setLibraryAssets([]); }
                                  setLibraryOpen(true);
                                }}
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
                              onClick={async () => {
                                try {
                                  const res = await adminMediaService.listMedia({ media_type: 'LINK', page_size: 50 });
                                  setLibraryAssets(res.results);
                                } catch { setLibraryAssets([]); }
                                setLibraryOpen(true);
                              }}
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
                          onClick={() => setAddingContentToModule(module.id)}
                          className="flex items-center justify-center w-full p-3 border-2 border-dashed border-gray-300 rounded-lg text-gray-500 hover:border-primary-500 hover:text-primary-600 transition-colors"
                        >
                          <PlusIcon className="h-5 w-5 mr-2" />
                          Add Content
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Assignment Tab */}
      {activeTab === 'assignment' && (
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-6">
          <h2 className="text-lg font-semibold text-gray-900">Course Assignment</h2>
          
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

          {/* Specific Assignment */}
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
              <strong>Assignment Summary:</strong>{' '}
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
                    value={createGroupForm.name}
                    onChange={(e) => setCreateGroupForm({ ...createGroupForm, name: e.target.value })}
                    placeholder="e.g., Grade 9, Math Teachers"
                  />
                  <Input
                    label="Description"
                    value={createGroupForm.description}
                    onChange={(e) => setCreateGroupForm({ ...createGroupForm, description: e.target.value })}
                    placeholder="Optional"
                  />
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
                    <select
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
                    <div className="space-y-4">
                      {c.file_url.match(/\.pdf(\?|$)/i) ? (
                        <iframe
                          src={resolveUrl(c.file_url)}
                          className="w-full h-[60vh] rounded-lg border border-gray-200"
                          title={c.title}
                        />
                      ) : (
                        <div className="flex flex-col items-center justify-center py-16">
                          <DocumentTextIcon className="h-12 w-12 text-orange-400 mb-3" />
                          <p className="font-medium text-gray-900">{c.title}</p>
                          <a
                            href={resolveUrl(c.file_url)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="mt-3 inline-flex items-center gap-1.5 text-sm text-primary-600 hover:text-primary-700 font-medium"
                          >
                            Open document in new tab
                          </a>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="text-gray-400 text-center py-8">No file uploaded</p>
                  )
                ) : c.content_type === 'LINK' ? (
                  c.file_url ? (
                    <div className="space-y-4">
                      <div className="p-4 bg-purple-50 rounded-lg">
                        <div className="flex items-center gap-2 mb-2">
                          <LinkIcon className="h-5 w-5 text-purple-500" />
                          <span className="font-medium text-gray-900">{c.title}</span>
                        </div>
                        <a
                          href={c.file_url.startsWith('http') ? c.file_url : `https://${c.file_url}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-primary-600 hover:underline break-all"
                        >
                          {c.file_url}
                        </a>
                      </div>
                      <iframe
                        src={c.file_url.startsWith('http') ? c.file_url : `https://${c.file_url}`}
                        className="w-full h-[50vh] rounded-lg border border-gray-200"
                        title={c.title}
                        sandbox="allow-scripts allow-same-origin"
                      />
                    </div>
                  ) : (
                    <p className="text-gray-400 text-center py-8">No URL provided</p>
                  )
                ) : c.content_type === 'TEXT' ? (
                  <div className="prose prose-sm max-w-none">
                    <div className="p-4 bg-gray-50 rounded-lg whitespace-pre-wrap text-gray-700 leading-relaxed">
                      {c.text_content || 'No text content'}
                    </div>
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
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => { setLibraryOpen(false); setLibrarySearch(''); }}>
          <div className="bg-white rounded-xl max-w-2xl w-full mx-4 max-h-[80vh] overflow-hidden flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-4 border-b border-gray-200">
              <h3 className="text-lg font-semibold text-gray-900">Choose from Media Library</h3>
              <button onClick={() => { setLibraryOpen(false); setLibrarySearch(''); }} className="p-1 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>
            <div className="p-4 border-b border-gray-200">
              <div className="relative">
                <MagnifyingGlassIcon className="h-5 w-5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={librarySearch}
                  onChange={async (e) => {
                    const v = e.target.value;
                    setLibrarySearch(v);
                    const mediaType = newContentData.content_type === 'LINK' ? 'LINK' : newContentData.content_type === 'VIDEO' ? 'VIDEO' : 'DOCUMENT';
                    try {
                      const res = await adminMediaService.listMedia({ media_type: mediaType, search: v, page_size: 50 });
                      setLibraryAssets(res.results);
                    } catch { /* ignore */ }
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
                          title: prev.title || asset.title,
                          file_url: asset.file_url,
                        }));
                        setContentFile(null); // clear any uploaded file
                        setLibraryOpen(false);
                        setLibrarySearch('');
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
    </div>
  );
};
