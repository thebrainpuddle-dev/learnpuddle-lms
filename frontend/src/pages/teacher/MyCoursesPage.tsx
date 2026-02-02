// src/pages/teacher/MyCoursesPage.tsx

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CourseCard } from '../../components/teacher';
import { MagnifyingGlassIcon, FunnelIcon } from '@heroicons/react/24/outline';
import { teacherService } from '../../services/teacherService';

type StatusFilter = 'ALL' | 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';

export const MyCoursesPage: React.FC = () => {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL');
  
  // Fetch all courses
  const { data: courses, isLoading } = useQuery({
    queryKey: ['teacherCourses', 'all'],
    queryFn: teacherService.listCourses,
  });

  const toCourseCard = (c: any) => {
    const total = Number(c.total_content_count || 0);
    const completed = Number(c.completed_content_count || 0);
    const progress = Number(c.progress_percentage || 0);
    const status =
      progress >= 100 ? 'COMPLETED' : progress > 0 ? 'IN_PROGRESS' : 'NOT_STARTED';
    return {
      id: c.id,
      title: c.title,
      description: c.description,
      thumbnail: c.thumbnail || undefined,
      progress,
      totalModules: total,
      completedModules: completed,
      estimatedHours: Number(c.estimated_hours || 0),
      deadline: c.deadline || undefined,
      status,
    } as const;
  };
  
  // Filter courses
  const filteredCourses = courses?.filter(course => {
    const matchesSearch = course.title.toLowerCase().includes(search.toLowerCase()) ||
                          course.description.toLowerCase().includes(search.toLowerCase());
    const progress = Number(course.progress_percentage || 0);
    const derivedStatus =
      progress >= 100 ? 'COMPLETED' : progress > 0 ? 'IN_PROGRESS' : 'NOT_STARTED';
    const matchesStatus = statusFilter === 'ALL' || derivedStatus === statusFilter;
    return matchesSearch && matchesStatus;
  });
  
  // Count by status
  const statusCounts = {
    ALL: courses?.length || 0,
    NOT_STARTED: courses?.filter(c => Number(c.progress_percentage || 0) === 0).length || 0,
    IN_PROGRESS: courses?.filter(c => {
      const p = Number(c.progress_percentage || 0);
      return p > 0 && p < 100;
    }).length || 0,
    COMPLETED: courses?.filter(c => Number(c.progress_percentage || 0) >= 100).length || 0,
  };
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">My Courses</h1>
        <p className="mt-1 text-gray-500">
          Browse and continue your assigned courses
        </p>
      </div>
      
      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        {/* Search */}
        <div className="flex-1">
          <div className="relative">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
            <input
              type="text"
              placeholder="Search courses..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500"
            />
          </div>
        </div>
        
        {/* Status filter */}
        <div className="flex items-center space-x-2">
          <FunnelIcon className="h-5 w-5 text-gray-400" />
          <div className="flex rounded-lg border border-gray-300 overflow-hidden">
            {(['ALL', 'NOT_STARTED', 'IN_PROGRESS', 'COMPLETED'] as StatusFilter[]).map((status) => (
              <button
                key={status}
                onClick={() => setStatusFilter(status)}
                className={`px-3 py-2 text-sm font-medium transition-colors ${
                  statusFilter === status
                    ? 'bg-emerald-600 text-white'
                    : 'bg-white text-gray-700 hover:bg-gray-50'
                }`}
              >
                {status === 'ALL' ? 'All' : 
                 status === 'NOT_STARTED' ? 'Not Started' :
                 status === 'IN_PROGRESS' ? 'In Progress' : 'Completed'}
                <span className="ml-1 text-xs">({statusCounts[status]})</span>
              </button>
            ))}
          </div>
        </div>
      </div>
      
      {/* Course Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <CourseCard key={i} loading id="" title="" description="" progress={0} totalModules={0} completedModules={0} estimatedHours={0} status="NOT_STARTED" />
          ))}
        </div>
      ) : filteredCourses && filteredCourses.length > 0 ? (
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {filteredCourses.map((course) => (
            <CourseCard key={course.id} {...toCourseCard(course)} />
          ))}
        </div>
      ) : (
        <div className="text-center py-12">
          <div className="text-gray-400 mb-4">
            <MagnifyingGlassIcon className="h-12 w-12 mx-auto" />
          </div>
          <h3 className="text-lg font-medium text-gray-900 mb-1">No courses found</h3>
          <p className="text-gray-500">
            {search ? 'Try adjusting your search or filters' : 'No courses have been assigned yet'}
          </p>
        </div>
      )}
    </div>
  );
};
