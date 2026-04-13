// src/pages/student/CourseListPage.tsx
//
// Student course catalog — grid/list view with filters.

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Search,
  BookOpen,
  Grid3X3,
  List,
  Clock,
  Play,
  CheckCircle2,
  Circle,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';
import { studentService } from '../../services/studentService';
import { usePageTitle } from '../../hooks/usePageTitle';

type StatusFilter = 'ALL' | 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';
type ViewMode = 'grid' | 'list';

const STATUS_LABELS: Record<StatusFilter, string> = {
  ALL: 'All',
  NOT_STARTED: 'Not Started',
  IN_PROGRESS: 'In Progress',
  COMPLETED: 'Completed',
};

export const CourseListPage: React.FC = () => {
  usePageTitle('My Courses');
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL');
  const [viewMode, setViewMode] = useState<ViewMode>('grid');

  const { data: courses = [], isLoading } = useQuery({
    queryKey: ['studentCourses'],
    queryFn: studentService.getStudentCourses,
  });

  const getStatus = (progress: number): 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED' => {
    if (progress >= 100) return 'COMPLETED';
    if (progress > 0) return 'IN_PROGRESS';
    return 'NOT_STARTED';
  };

  const filtered = courses.filter((c) => {
    const matchesSearch =
      c.title.toLowerCase().includes(search.toLowerCase()) ||
      c.description.toLowerCase().includes(search.toLowerCase());
    const progress = Number(c.progress_percentage || 0);
    const status = getStatus(progress);
    const matchesStatus = statusFilter === 'ALL' || status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const counts = {
    ALL: courses.length,
    NOT_STARTED: courses.filter((c) => Number(c.progress_percentage || 0) === 0).length,
    IN_PROGRESS: courses.filter((c) => {
      const p = Number(c.progress_percentage || 0);
      return p > 0 && p < 100;
    }).length,
    COMPLETED: courses.filter((c) => Number(c.progress_percentage || 0) >= 100).length,
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-[22px] font-bold text-tp-text tracking-tight">My Courses</h1>
        <p className="mt-0.5 text-[13px] text-gray-400">
          Browse and continue your enrolled courses
        </p>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex-1 max-w-sm relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-[14px] w-[14px] text-gray-400" />
          <input
            type="text"
            placeholder="Search courses..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-[7px] rounded-lg text-[13px] bg-white border border-gray-200 text-tp-text placeholder:text-gray-400 focus:border-indigo-400/40 focus:ring-2 focus:ring-indigo-400/10 transition-all"
          />
        </div>

        <div className="flex items-center gap-1.5 overflow-x-auto">
          {(Object.keys(STATUS_LABELS) as StatusFilter[]).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={cn(
                'px-3 py-[6px] rounded-lg text-[11px] font-semibold whitespace-nowrap transition-all',
                statusFilter === s
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-white border border-gray-200 text-gray-500 hover:text-tp-text hover:border-gray-300',
              )}
            >
              {STATUS_LABELS[s]}
              <span className={cn(
                'ml-1.5 tabular-nums',
                statusFilter === s ? 'text-white/70' : 'text-gray-400',
              )}>
                {counts[s]}
              </span>
            </button>
          ))}
        </div>

        <div className="hidden sm:flex rounded-lg overflow-hidden border border-gray-200">
          <button
            onClick={() => setViewMode('grid')}
            className={cn(
              'p-[7px] transition-colors',
              viewMode === 'grid'
                ? 'bg-indigo-600 text-white'
                : 'text-gray-400 hover:text-tp-text bg-white',
            )}
          >
            <Grid3X3 className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setViewMode('list')}
            className={cn(
              'p-[7px] transition-colors',
              viewMode === 'list'
                ? 'bg-indigo-600 text-white'
                : 'text-gray-400 hover:text-tp-text bg-white',
            )}
          >
            <List className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div
          className={cn(
            viewMode === 'grid'
              ? 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4'
              : 'space-y-2',
          )}
        >
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-48 tp-skeleton rounded-2xl" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20">
          <BookOpen className="h-10 w-10 mx-auto text-gray-200 mb-3" />
          <h3 className="text-[15px] font-semibold text-tp-text mb-1">No courses found</h3>
          <p className="text-[13px] text-gray-400">
            {search
              ? 'Try adjusting your search or filters'
              : 'No courses have been enrolled yet'}
          </p>
        </div>
      ) : viewMode === 'grid' ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((course) => {
            const progress = Number(course.progress_percentage || 0);
            const status = getStatus(progress);
            return (
              <button
                key={course.id}
                onClick={() => navigate(`/student/courses/${course.id}`)}
                className="text-left bg-white rounded-2xl border border-gray-100 overflow-hidden hover:border-indigo-200 hover:shadow-md transition-all group shadow-sm"
              >
                <div className="h-32 bg-gray-50 relative overflow-hidden">
                  {course.thumbnail ? (
                    <img
                      src={course.thumbnail}
                      alt=""
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="h-full w-full flex items-center justify-center bg-gradient-to-br from-gray-50 to-gray-100">
                      <BookOpen className="h-8 w-8 text-gray-200" />
                    </div>
                  )}
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/30 flex items-center justify-center transition-all duration-300">
                    <Play className="h-8 w-8 text-white opacity-0 group-hover:opacity-100 transition-opacity duration-300 drop-shadow-lg" />
                  </div>
                  <div className="absolute top-2.5 right-2.5">
                    <span
                      className={cn(
                        'px-2 py-[3px] rounded-md text-[10px] font-semibold uppercase tracking-wide leading-none shadow-sm',
                        status === 'COMPLETED'
                          ? 'bg-emerald-500 text-white'
                          : status === 'IN_PROGRESS'
                            ? 'bg-indigo-600 text-white'
                            : 'bg-white/95 text-gray-500 border border-gray-200/50',
                      )}
                    >
                      {STATUS_LABELS[status]}
                    </span>
                  </div>
                </div>

                <div className="p-4">
                  <h3 className="text-[13px] font-semibold text-tp-text mb-0.5 truncate leading-tight">
                    {course.title}
                  </h3>
                  <p className="text-[11px] text-gray-400 line-clamp-2 mb-3 leading-relaxed">
                    {course.description || `${course.total_content_count} lessons`}
                  </p>
                  <div className="flex items-center gap-2.5">
                    <div className="flex-1 h-[5px] bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-indigo-500 to-violet-400 rounded-full transition-all duration-700"
                        style={{ width: `${Math.min(100, progress)}%` }}
                      />
                    </div>
                    <span className="text-[11px] text-tp-text-secondary font-semibold tabular-nums">
                      {Math.round(progress)}%
                    </span>
                  </div>
                  <div className="flex items-center gap-3 mt-3 text-[11px] text-gray-400">
                    <span className="flex items-center gap-1">
                      <BookOpen className="h-3 w-3" />
                      {course.total_content_count} lessons
                    </span>
                    {course.estimated_hours && Number(course.estimated_hours) > 0 && (
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {course.estimated_hours}h
                      </span>
                    )}
                    {course.deadline && (
                      <span className="flex items-center gap-1 text-amber-500">
                        <Clock className="h-3 w-3" />
                        {new Date(course.deadline).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                        })}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      ) : (
        <div className="bg-white rounded-2xl border border-gray-100 overflow-hidden shadow-sm">
          {/* List header */}
          <div className="hidden sm:grid grid-cols-12 gap-4 px-5 py-2.5 bg-gray-50/80 text-[10px] uppercase tracking-wider font-semibold text-gray-400 border-b border-gray-50">
            <div className="col-span-5">Course</div>
            <div className="col-span-3">Progress</div>
            <div className="col-span-2">Status</div>
            <div className="col-span-2 text-right">Deadline</div>
          </div>
          <div className="divide-y divide-gray-50">
            {filtered.map((course) => {
              const progress = Number(course.progress_percentage || 0);
              const status = getStatus(progress);
              const StatusIcon =
                status === 'COMPLETED'
                  ? CheckCircle2
                  : status === 'IN_PROGRESS'
                    ? Play
                    : Circle;
              const statusColor =
                status === 'COMPLETED'
                  ? 'text-emerald-500'
                  : status === 'IN_PROGRESS'
                    ? 'text-indigo-600'
                    : 'text-gray-400';

              return (
                <button
                  key={course.id}
                  onClick={() => navigate(`/student/courses/${course.id}`)}
                  className="w-full text-left grid grid-cols-12 gap-4 px-5 py-3 hover:bg-gray-50/50 transition-colors items-center"
                >
                  <div className="col-span-5 flex items-center gap-3 min-w-0">
                    <div className="h-9 w-9 rounded-lg bg-gray-50 border border-gray-100 flex items-center justify-center flex-shrink-0 overflow-hidden">
                      {course.thumbnail ? (
                        <img
                          src={course.thumbnail}
                          alt=""
                          className="h-9 w-9 object-cover"
                        />
                      ) : (
                        <BookOpen className="h-4 w-4 text-gray-300" />
                      )}
                    </div>
                    <div className="min-w-0">
                      <p className="text-[13px] font-medium text-tp-text truncate">
                        {course.title}
                      </p>
                      <p className="text-[11px] text-gray-400">
                        {course.total_content_count} lessons
                      </p>
                    </div>
                  </div>
                  <div className="col-span-3 flex items-center gap-2.5">
                    <div className="flex-1 h-[5px] bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-gradient-to-r from-indigo-500 to-violet-400 rounded-full"
                        style={{ width: `${progress}%` }}
                      />
                    </div>
                    <span className="text-[11px] text-tp-text-secondary font-semibold w-8 text-right tabular-nums">
                      {Math.round(progress)}%
                    </span>
                  </div>
                  <div className="col-span-2 flex items-center gap-1.5">
                    <StatusIcon className={cn('h-3.5 w-3.5', statusColor)} />
                    <span className={cn('text-[11px] font-medium', statusColor)}>
                      {STATUS_LABELS[status]}
                    </span>
                  </div>
                  <div className="col-span-2 text-right text-[11px] text-gray-400">
                    {course.deadline
                      ? new Date(course.deadline).toLocaleDateString('en-US', {
                          month: 'short',
                          day: 'numeric',
                        })
                      : 'No deadline'}
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};
