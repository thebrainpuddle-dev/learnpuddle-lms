// src/pages/admin/CoursesPage.tsx

import React, { useEffect, useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { usePageTitle } from '../../hooks/usePageTitle';
import { Button, Loading, useToast, BulkActionsBar, BulkAction } from '../../components/common';
import api from '../../config/api';
import {
  PlusIcon,
  MagnifyingGlassIcon,
  PencilSquareIcon,
  TrashIcon,
  DocumentDuplicateIcon,
  EyeIcon,
  EyeSlashIcon,
  FunnelIcon,
  AcademicCapIcon,
  UserGroupIcon,
  CalendarIcon,
  ClockIcon,
  TableCellsIcon,
  ViewColumnsIcon,
} from '@heroicons/react/24/outline';

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
  is_published: boolean;
  is_active: boolean;
  module_count: number;
  content_count: number;
  assigned_teacher_count: number;
  created_at: string;
  updated_at: string;
}

interface PaginatedResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Course[];
}

const fetchCourses = async (params: {
  search?: string;
  is_published?: string;
  is_mandatory?: string;
  page?: number;
}): Promise<PaginatedResponse> => {
  const queryParams = new URLSearchParams();
  if (params.search) queryParams.append('search', params.search);
  if (params.is_published) queryParams.append('is_published', params.is_published);
  if (params.is_mandatory) queryParams.append('is_mandatory', params.is_mandatory);
  if (params.page) queryParams.append('page', params.page.toString());
  
  const response = await api.get(`/courses/?${queryParams.toString()}`);
  return response.data;
};

const deleteCourse = async (id: string): Promise<void> => {
  await api.delete(`/courses/${id}/`);
};

const duplicateCourse = async (id: string): Promise<Course> => {
  const response = await api.post(`/courses/${id}/duplicate/`);
  return response.data;
};

const togglePublish = async (course: Course): Promise<Course> => {
  const response = await api.patch(`/courses/${course.id}/`, {
    is_published: !course.is_published,
  });
  return response.data;
};

const bulkActionCourses = async (action: 'publish' | 'unpublish' | 'delete', courseIds: string[]) => {
  const response = await api.post('/courses/bulk-action/', { action, course_ids: courseIds });
  return response.data as { message: string; affected_count: number; requested_count: number };
};

/* ── Thumbnail helper ─────────────────────────────────────────────── */
function thumbSrc(course: Course): string | null {
  if (course.thumbnail_url) return course.thumbnail_url;
  if (!course.thumbnail) return null;
  // If thumbnail is a relative path, prepend the backend origin
  if (course.thumbnail.startsWith('http')) return course.thumbnail;
  const backendOrigin = (process.env.REACT_APP_API_URL || 'http://localhost:8000/api').replace(/\/api\/?$/, '');
  return `${backendOrigin}${course.thumbnail.startsWith('/') ? '' : '/'}${course.thumbnail}`;
}

/* ── Kanban card ──────────────────────────────────────────────────── */
const KanbanCard: React.FC<{
  course: Course;
  onEdit: () => void;
  onPublish: () => void;
  onDelete: () => void;
  onDragStart: (e: React.DragEvent) => void;
}> = ({ course, onEdit, onPublish, onDelete, onDragStart }) => {
  const src = thumbSrc(course);
  return (
    <div
      draggable
      onDragStart={onDragStart}
      className="bg-white rounded-lg border border-gray-200 shadow-sm hover:shadow-md transition-shadow cursor-grab active:cursor-grabbing"
    >
      {/* Thumbnail strip */}
      <div className="h-28 rounded-t-lg bg-gradient-to-br from-primary-50 to-primary-100 relative overflow-hidden">
        {src ? (
          <img src={src} alt="" className="w-full h-full object-cover" />
        ) : (
          <div className="flex items-center justify-center h-full">
            <AcademicCapIcon className="h-10 w-10 text-primary-300" />
          </div>
        )}
        {course.is_mandatory && (
          <span className="absolute top-2 left-2 px-1.5 py-0.5 rounded text-[10px] font-bold bg-red-500 text-white uppercase">
            Mandatory
          </span>
        )}
      </div>
      <div className="p-3 space-y-2">
        <h4 className="text-sm font-semibold text-gray-900 truncate" title={course.title}>{course.title}</h4>
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-0.5"><ClockIcon className="h-3 w-3" />{course.estimated_hours}h</span>
          <span>{course.module_count} mod</span>
          <span>{course.content_count ?? 0} items</span>
        </div>
        <div className="flex items-center gap-1 text-xs text-gray-500">
          <UserGroupIcon className="h-3 w-3" />
          {course.assigned_to_all ? 'All teachers' : `${course.assigned_teacher_count} teachers`}
        </div>
        {course.deadline && (
          <div className="flex items-center gap-1 text-xs text-gray-500">
            <CalendarIcon className="h-3 w-3" />
            {new Date(course.deadline).toLocaleDateString()}
          </div>
        )}
        <div className="flex items-center justify-end gap-1 pt-1 border-t border-gray-100">
          <button onClick={onPublish} className="p-1 text-gray-400 hover:text-gray-600 rounded" title={course.is_published ? 'Unpublish' : 'Publish'}>
            {course.is_published ? <EyeSlashIcon className="h-4 w-4" /> : <EyeIcon className="h-4 w-4" />}
          </button>
          <button onClick={onEdit} className="p-1 text-gray-400 hover:text-primary-600 rounded" title="Edit">
            <PencilSquareIcon className="h-4 w-4" />
          </button>
          <button onClick={onDelete} className="p-1 text-gray-400 hover:text-red-600 rounded" title="Delete">
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

export const CoursesPage: React.FC = () => {
  usePageTitle('Courses');
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  
  const [search, setSearch] = useState('');
  const [publishedFilter, setPublishedFilter] = useState<string>('');
  const [mandatoryFilter, setMandatoryFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<'table' | 'board'>('table');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const dragCourseRef = useRef<Course | null>(null);

  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
      return;
    }
    const media = window.matchMedia('(max-width: 767px)');
    const updateViewMode = (matches: boolean) => {
      if (matches) setViewMode('board');
    };
    updateViewMode(media.matches);
    const onChange = (event: MediaQueryListEvent) => updateViewMode(event.matches);

    if (media.addEventListener) {
      media.addEventListener('change', onChange);
      return () => media.removeEventListener('change', onChange);
    }

    media.addListener(onChange);
    return () => media.removeListener(onChange);
  }, []);

  const { data, isLoading, error } = useQuery({
    queryKey: ['adminCourses', search, publishedFilter, mandatoryFilter, page],
    queryFn: () => fetchCourses({
      search: search || undefined,
      is_published: publishedFilter || undefined,
      is_mandatory: mandatoryFilter || undefined,
      page,
    }),
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCourse,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['adminCourses'] });
      queryClient.invalidateQueries({ queryKey: ['adminDashboardStats'] });
      setDeleteConfirm(null);
      toast.success('Course deleted', 'The course has been removed.');
    },
    onError: () => {
      toast.error('Failed to delete course', 'Please try again.');
    },
  });

  const duplicateMutation = useMutation({
    mutationFn: duplicateCourse,
    onSuccess: (newCourse) => {
      queryClient.invalidateQueries({ queryKey: ['adminCourses'] });
      queryClient.invalidateQueries({ queryKey: ['adminDashboardStats'] });
      toast.success('Course duplicated', 'You can now edit the copy.');
      navigate(`/admin/courses/${newCourse.id}/edit`);
    },
    onError: () => {
      toast.error('Failed to duplicate course', 'Please try again.');
    },
  });

  const publishMutation = useMutation({
    mutationFn: togglePublish,
    onSuccess: (updatedCourse) => {
      queryClient.invalidateQueries({ queryKey: ['adminCourses'] });
      queryClient.invalidateQueries({ queryKey: ['adminDashboardStats'] });
      toast.success(
        updatedCourse.is_published ? 'Course published' : 'Course unpublished',
        updatedCourse.is_published ? 'Teachers can now access this course.' : 'Course is now in draft mode.'
      );
    },
    onError: () => {
      toast.error('Failed to update course', 'Please try again.');
    },
  });

  const bulkActionMutation = useMutation({
    mutationFn: ({ action, courseIds }: { action: 'publish' | 'unpublish' | 'delete'; courseIds: string[] }) =>
      bulkActionCourses(action, courseIds),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['adminCourses'] });
      queryClient.invalidateQueries({ queryKey: ['adminDashboardStats'] });
      toast.success('Bulk action complete', result.message);
      setSelectedIds(new Set());
    },
    onError: () => {
      toast.error('Bulk action failed', 'Please try again.');
    },
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
  };

  // Selection helpers
  const courses = data?.results || [];
  const toggleSelection = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === courses.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(courses.map((c) => c.id)));
    }
  };

  const clearSelection = () => setSelectedIds(new Set());

  const handleBulkAction = (actionId: string) => {
    const courseIds = Array.from(selectedIds);
    bulkActionMutation.mutate({ action: actionId as 'publish' | 'unpublish' | 'delete', courseIds });
  };

  const bulkActions: BulkAction[] = [
    { id: 'publish', label: 'Publish', icon: EyeIcon, variant: 'success' },
    { id: 'unpublish', label: 'Unpublish', icon: EyeSlashIcon, variant: 'default' },
    { id: 'delete', label: 'Delete', icon: TrashIcon, variant: 'danger', requiresConfirmation: true },
  ];

  /* ── Kanban drag handlers ─────────────────────────────────────── */
  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); e.currentTarget.classList.add('ring-2', 'ring-primary-400'); };
  const handleDragLeave = (e: React.DragEvent) => { e.currentTarget.classList.remove('ring-2', 'ring-primary-400'); };
  const handleDrop = (targetPublished: boolean) => (e: React.DragEvent) => {
    e.preventDefault();
    e.currentTarget.classList.remove('ring-2', 'ring-primary-400');
    const c = dragCourseRef.current;
    if (c && c.is_published !== targetPublished) {
      publishMutation.mutate(c);
    }
    dragCourseRef.current = null;
  };

  if (error) {
    const isAuthError = (error as { response?: { status?: number } })?.response?.status === 401;
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-700">
          {isAuthError
            ? 'Your session has expired. Redirecting to login…'
            : 'Failed to load courses. Please try again.'}
        </p>
        {!isAuthError && (
          <Button variant="outline" size="sm" className="mt-3" onClick={() => window.location.reload()}>
            Retry
          </Button>
        )}
      </div>
    );
  }

  const draftCourses = data?.results.filter(c => !c.is_published) || [];
  const publishedCourses = data?.results.filter(c => c.is_published) || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Courses</h1>
          <p className="mt-1 text-gray-500">Manage your training courses</p>
        </div>
        <Button data-tour="admin-courses-create" variant="primary" onClick={() => navigate('/admin/courses/new')}>
          <PlusIcon className="h-5 w-5 mr-2" />
          Create Course
        </Button>
      </div>

      {/* Filters + View Toggle */}
      <div data-tour="admin-courses-filters" className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex flex-col gap-4 lg:flex-row">
          <form onSubmit={handleSearch} className="flex-1">
            <div className="relative">
              <label htmlFor="admin-courses-search" className="sr-only">
                Search courses
              </label>
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                id="admin-courses-search"
                name="courses_search"
                type="search"
                autoComplete="off"
                placeholder="Search courses..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>
          </form>

          <div className="flex flex-wrap items-center gap-3">
            <FunnelIcon className="h-5 w-5 text-gray-400" />
            <select
              name="published_filter"
              value={publishedFilter}
              onChange={(e) => { setPublishedFilter(e.target.value); setPage(1); }}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">All Status</option>
              <option value="true">Published</option>
              <option value="false">Draft</option>
            </select>
            <select
              name="mandatory_filter"
              value={mandatoryFilter}
              onChange={(e) => { setMandatoryFilter(e.target.value); setPage(1); }}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">All Types</option>
              <option value="true">Mandatory</option>
              <option value="false">Optional</option>
            </select>

            {/* View toggle */}
            <div className="flex bg-gray-100 rounded-lg p-0.5 ml-2">
              <button
                type="button"
                onClick={() => setViewMode('table')}
                className={`p-1.5 rounded-md ${viewMode === 'table' ? 'bg-white shadow text-primary-600' : 'text-gray-400 hover:text-gray-600'}`}
                title="Table view"
              >
                <TableCellsIcon className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={() => setViewMode('board')}
                className={`p-1.5 rounded-md ${viewMode === 'board' ? 'bg-white shadow text-primary-600' : 'text-gray-400 hover:text-gray-600'}`}
                title="Board view"
              >
                <ViewColumnsIcon className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12"><Loading /></div>
      ) : data?.results.length === 0 ? (
        <div data-tour="admin-courses-list" className="bg-white rounded-xl border border-gray-200 text-center py-12">
          <AcademicCapIcon className="h-12 w-12 mx-auto text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-1">No courses found</h3>
          <p className="text-gray-500 mb-4">
            {search ? 'Try adjusting your search or filters' : 'Get started by creating your first course'}
          </p>
          {!search && (
            <Button variant="primary" onClick={() => navigate('/admin/courses/new')}>
              <PlusIcon className="h-5 w-5 mr-2" /> Create Course
            </Button>
          )}
        </div>
      ) : viewMode === 'board' ? (
        /* ════════ BOARD VIEW (Kanban) ════════ */
        <div data-tour="admin-courses-list" className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Draft column */}
          <div
            className="rounded-xl border-2 border-dashed border-yellow-200 bg-yellow-50/50 p-4 min-h-[300px] transition-all"
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop(false)}
          >
            <div className="flex items-center gap-2 mb-4">
              <span className="h-2.5 w-2.5 rounded-full bg-yellow-400" />
              <h3 className="font-semibold text-gray-900">Draft</h3>
              <span className="ml-auto text-xs text-gray-500 bg-yellow-100 rounded-full px-2 py-0.5">{draftCourses.length}</span>
            </div>
            <div className="space-y-3">
              {draftCourses.map((course) => (
                <KanbanCard
                  key={course.id}
                  course={course}
                  onEdit={() => navigate(`/admin/courses/${course.id}/edit`)}
                  onPublish={() => publishMutation.mutate(course)}
                  onDelete={() => setDeleteConfirm(course.id)}
                  onDragStart={() => { dragCourseRef.current = course; }}
                />
              ))}
              {draftCourses.length === 0 && (
                <p className="text-center text-sm text-gray-400 py-8">Drop courses here to unpublish</p>
              )}
            </div>
          </div>

          {/* Published column */}
          <div
            className="rounded-xl border-2 border-dashed border-green-200 bg-green-50/50 p-4 min-h-[300px] transition-all"
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop(true)}
          >
            <div className="flex items-center gap-2 mb-4">
              <span className="h-2.5 w-2.5 rounded-full bg-green-500" />
              <h3 className="font-semibold text-gray-900">Published</h3>
              <span className="ml-auto text-xs text-gray-500 bg-green-100 rounded-full px-2 py-0.5">{publishedCourses.length}</span>
            </div>
            <div className="space-y-3">
              {publishedCourses.map((course) => (
                <KanbanCard
                  key={course.id}
                  course={course}
                  onEdit={() => navigate(`/admin/courses/${course.id}/edit`)}
                  onPublish={() => publishMutation.mutate(course)}
                  onDelete={() => setDeleteConfirm(course.id)}
                  onDragStart={() => { dragCourseRef.current = course; }}
                />
              ))}
              {publishedCourses.length === 0 && (
                <p className="text-center text-sm text-gray-400 py-8">Drop courses here to publish</p>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* ════════ TABLE VIEW ════════ */
        <div data-tour="admin-courses-list" className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-3 py-3 w-10">
                    <input
                      id="courses-select-all"
                      name="courses_select_all"
                      aria-label="Select all courses"
                      type="checkbox"
                      checked={courses.length > 0 && selectedIds.size === courses.length}
                      onChange={toggleSelectAll}
                      className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                    />
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Course</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Assignment</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Content</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Deadline</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {(data?.results ?? []).map((course) => {
                  const src = thumbSrc(course);
                  return (
                    <tr key={course.id} className={`hover:bg-gray-50 ${selectedIds.has(course.id) ? 'bg-emerald-50' : ''}`}>
                      <td className="px-3 py-4">
                        <input
                          id={`course-select-${course.id}`}
                          name={`course_select_${course.id}`}
                          aria-label={`Select ${course.title}`}
                          type="checkbox"
                          checked={selectedIds.has(course.id)}
                          onChange={() => toggleSelection(course.id)}
                          className="rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
                        />
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          <div className="flex-shrink-0 h-10 w-10 bg-primary-100 rounded-lg flex items-center justify-center overflow-hidden">
                            {src ? (
                              <img src={src} alt="" className="h-10 w-10 rounded-lg object-cover" />
                            ) : (
                              <AcademicCapIcon className="h-5 w-5 text-primary-600" />
                            )}
                          </div>
                          <div className="ml-4">
                            <div className="text-sm font-medium text-gray-900">{course.title}</div>
                            <div className="text-sm text-gray-500 flex items-center">
                              <ClockIcon className="h-3.5 w-3.5 mr-1" />
                              {course.estimated_hours} hrs
                              {course.is_mandatory && (
                                <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">Mandatory</span>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${course.is_published ? 'bg-green-100 text-green-800' : 'bg-yellow-100 text-yellow-800'}`}>
                          {course.is_published ? 'Published' : 'Draft'}
                        </span>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center text-sm text-gray-500">
                          <UserGroupIcon className="h-4 w-4 mr-1" />
                          {course.assigned_to_all ? (
                            <span className="text-primary-600 font-medium">All Teachers</span>
                          ) : (
                            `${course.assigned_teacher_count} teachers`
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {course.module_count} modules, {course.content_count ?? 0} items
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {course.deadline ? (
                          <div className="flex items-center">
                            <CalendarIcon className="h-4 w-4 mr-1" />
                            {new Date(course.deadline).toLocaleDateString()}
                          </div>
                        ) : (
                          <span className="text-gray-400">No deadline</span>
                        )}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                        <div className="flex items-center justify-end space-x-2">
                          <button onClick={() => publishMutation.mutate(course)} className="p-1.5 text-gray-400 hover:text-gray-600 rounded" title={course.is_published ? 'Unpublish' : 'Publish'}>
                            {course.is_published ? <EyeSlashIcon className="h-5 w-5" /> : <EyeIcon className="h-5 w-5" />}
                          </button>
                          <button onClick={() => navigate(`/admin/courses/${course.id}/edit`)} className="p-1.5 text-gray-400 hover:text-primary-600 rounded" title="Edit">
                            <PencilSquareIcon className="h-5 w-5" />
                          </button>
                          <button onClick={() => duplicateMutation.mutate(course.id)} className="p-1.5 text-gray-400 hover:text-blue-600 rounded" title="Duplicate" disabled={duplicateMutation.isPending}>
                            <DocumentDuplicateIcon className="h-5 w-5" />
                          </button>
                          <button onClick={() => setDeleteConfirm(course.id)} className="p-1.5 text-gray-400 hover:text-red-600 rounded" title="Delete">
                            <TrashIcon className="h-5 w-5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {data && (data.next || data.previous) && (
            <div className="bg-white px-4 py-3 flex items-center justify-between border-t border-gray-200 sm:px-6">
              <div className="flex-1 flex justify-between sm:hidden">
                <Button variant="outline" size="sm" disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>Previous</Button>
                <Button variant="outline" size="sm" disabled={!data.next} onClick={() => setPage((p) => p + 1)}>Next</Button>
              </div>
              <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
                <p className="text-sm text-gray-700">
                  Showing page <span className="font-medium">{page}</span> of{' '}
                  <span className="font-medium">{Math.ceil(data.count / 10)}</span>
                </p>
                <div className="flex space-x-2">
                  <Button variant="outline" size="sm" disabled={!data.previous} onClick={() => setPage((p) => p - 1)}>Previous</Button>
                  <Button variant="outline" size="sm" disabled={!data.next} onClick={() => setPage((p) => p + 1)}>Next</Button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Delete Course</h3>
            <p className="text-gray-600 mb-6">
              Are you sure you want to delete this course? This action cannot be undone.
            </p>
            <div className="flex justify-end space-x-3">
              <Button variant="outline" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
              <Button variant="primary" className="bg-red-600 hover:bg-red-700" loading={deleteMutation.isPending} onClick={() => deleteMutation.mutate(deleteConfirm)}>
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk Actions Bar */}
      <BulkActionsBar
        selectedCount={selectedIds.size}
        actions={bulkActions}
        onAction={handleBulkAction}
        onClearSelection={clearSelection}
        isLoading={bulkActionMutation.isPending}
      />
    </div>
  );
};
