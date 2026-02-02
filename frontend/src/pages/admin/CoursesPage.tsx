// src/pages/admin/CoursesPage.tsx

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Button, Loading, useToast } from '../../components/common';
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
} from '@heroicons/react/24/outline';

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

export const CoursesPage: React.FC = () => {
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  
  const [search, setSearch] = useState('');
  const [publishedFilter, setPublishedFilter] = useState<string>('');
  const [mandatoryFilter, setMandatoryFilter] = useState<string>('');
  const [page, setPage] = useState(1);
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

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

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
  };

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
        <p className="text-red-700">Failed to load courses. Please try again.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Courses</h1>
          <p className="mt-1 text-gray-500">
            Manage your training courses
          </p>
        </div>

        <Button
          variant="primary"
          onClick={() => navigate('/admin/courses/new')}
        >
          <PlusIcon className="h-5 w-5 mr-2" />
          Create Course
        </Button>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <div className="flex flex-col lg:flex-row gap-4">
          {/* Search */}
          <form onSubmit={handleSearch} className="flex-1">
            <div className="relative">
              <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search courses..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
              />
            </div>
          </form>

          {/* Status Filters */}
          <div className="flex items-center gap-3">
            <FunnelIcon className="h-5 w-5 text-gray-400" />
            
            <select
              value={publishedFilter}
              onChange={(e) => {
                setPublishedFilter(e.target.value);
                setPage(1);
              }}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">All Status</option>
              <option value="true">Published</option>
              <option value="false">Draft</option>
            </select>

            <select
              value={mandatoryFilter}
              onChange={(e) => {
                setMandatoryFilter(e.target.value);
                setPage(1);
              }}
              className="px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-primary-500 focus:border-primary-500"
            >
              <option value="">All Types</option>
              <option value="true">Mandatory</option>
              <option value="false">Optional</option>
            </select>
          </div>
        </div>
      </div>

      {/* Courses Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loading />
          </div>
        ) : data?.results.length === 0 ? (
          <div className="text-center py-12">
            <AcademicCapIcon className="h-12 w-12 mx-auto text-gray-400 mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-1">No courses found</h3>
            <p className="text-gray-500 mb-4">
              {search ? 'Try adjusting your search or filters' : 'Get started by creating your first course'}
            </p>
            {!search && (
              <Button variant="primary" onClick={() => navigate('/admin/courses/new')}>
                <PlusIcon className="h-5 w-5 mr-2" />
                Create Course
              </Button>
            )}
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Course
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Assignment
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Content
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Deadline
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {data?.results.map((course) => (
                    <tr key={course.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          <div className="flex-shrink-0 h-10 w-10 bg-primary-100 rounded-lg flex items-center justify-center">
                            {course.thumbnail ? (
                              <img
                                src={course.thumbnail}
                                alt=""
                                className="h-10 w-10 rounded-lg object-cover"
                              />
                            ) : (
                              <AcademicCapIcon className="h-5 w-5 text-primary-600" />
                            )}
                          </div>
                          <div className="ml-4">
                            <div className="text-sm font-medium text-gray-900">
                              {course.title}
                            </div>
                            <div className="text-sm text-gray-500 flex items-center">
                              <ClockIcon className="h-3.5 w-3.5 mr-1" />
                              {course.estimated_hours} hrs
                              {course.is_mandatory && (
                                <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
                                  Mandatory
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <span
                          className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                            course.is_published
                              ? 'bg-green-100 text-green-800'
                              : 'bg-yellow-100 text-yellow-800'
                          }`}
                        >
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
                        {course.module_count} modules, {course.content_count} items
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
                          <button
                            onClick={() => publishMutation.mutate(course)}
                            className="p-1.5 text-gray-400 hover:text-gray-600 rounded"
                            title={course.is_published ? 'Unpublish' : 'Publish'}
                          >
                            {course.is_published ? (
                              <EyeSlashIcon className="h-5 w-5" />
                            ) : (
                              <EyeIcon className="h-5 w-5" />
                            )}
                          </button>
                          <button
                            onClick={() => navigate(`/admin/courses/${course.id}/edit`)}
                            className="p-1.5 text-gray-400 hover:text-primary-600 rounded"
                            title="Edit"
                          >
                            <PencilSquareIcon className="h-5 w-5" />
                          </button>
                          <button
                            onClick={() => duplicateMutation.mutate(course.id)}
                            className="p-1.5 text-gray-400 hover:text-blue-600 rounded"
                            title="Duplicate"
                            disabled={duplicateMutation.isPending}
                          >
                            <DocumentDuplicateIcon className="h-5 w-5" />
                          </button>
                          <button
                            onClick={() => setDeleteConfirm(course.id)}
                            className="p-1.5 text-gray-400 hover:text-red-600 rounded"
                            title="Delete"
                          >
                            <TrashIcon className="h-5 w-5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {data && (data.next || data.previous) && (
              <div className="bg-white px-4 py-3 flex items-center justify-between border-t border-gray-200 sm:px-6">
                <div className="flex-1 flex justify-between sm:hidden">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!data.previous}
                    onClick={() => setPage((p) => p - 1)}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!data.next}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    Next
                  </Button>
                </div>
                <div className="hidden sm:flex-1 sm:flex sm:items-center sm:justify-between">
                  <div>
                    <p className="text-sm text-gray-700">
                      Showing page <span className="font-medium">{page}</span> of{' '}
                      <span className="font-medium">{Math.ceil(data.count / 10)}</span>
                    </p>
                  </div>
                  <div className="flex space-x-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!data.previous}
                      onClick={() => setPage((p) => p - 1)}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!data.next}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white rounded-xl p-6 max-w-md w-full mx-4">
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Delete Course</h3>
            <p className="text-gray-600 mb-6">
              Are you sure you want to delete this course? This action cannot be undone.
            </p>
            <div className="flex justify-end space-x-3">
              <Button variant="outline" onClick={() => setDeleteConfirm(null)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                className="bg-red-600 hover:bg-red-700"
                loading={deleteMutation.isPending}
                onClick={() => deleteMutation.mutate(deleteConfirm)}
              >
                Delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
