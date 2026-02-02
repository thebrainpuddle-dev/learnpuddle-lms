// src/pages/teacher/DashboardPage.tsx

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/authStore';
import { ProgressCard, CourseCard } from '../../components/teacher';
import { Button } from '../../components/common/Button';
import { teacherService } from '../../services/teacherService';
import {
  AcademicCapIcon,
  BookOpenIcon,
  CheckCircleIcon,
  ClockIcon,
  ArrowRightIcon,
  CalendarDaysIcon,
} from '@heroicons/react/24/outline';
import { PlayIcon } from '@heroicons/react/24/solid';

export const DashboardPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuthStore();
  
  const { data: dashboard, isLoading: statsLoading } = useQuery({
    queryKey: ['teacherDashboard'],
    queryFn: teacherService.getDashboard,
  });
  
  const { data: courses, isLoading: coursesLoading } = useQuery({
    queryKey: ['teacherCourses'],
    queryFn: teacherService.listCourses,
  });
  
  const deadlines = dashboard?.deadlines ?? [];
  const continueCourse = dashboard?.continue_learning;

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
  
  return (
    <div className="space-y-8">
      {/* Welcome Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            Welcome back, {user?.first_name}!
          </h1>
          <p className="mt-1 text-gray-500">
            Track your progress and continue learning
          </p>
        </div>
        
        {continueCourse && (
          <Button
            variant="primary"
            className="mt-4 sm:mt-0 bg-emerald-600 hover:bg-emerald-700"
            onClick={() => navigate(`/teacher/courses/${continueCourse.course_id}`)}
          >
            <PlayIcon className="h-4 w-4 mr-2" />
            Continue Learning
          </Button>
        )}
      </div>
      
      {/* Stats Grid */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <ProgressCard
          title="Overall Progress"
          value={`${dashboard?.stats.overall_progress || 0}%`}
          subtitle="Keep it up!"
          icon={<AcademicCapIcon className="h-6 w-6" />}
          progress={dashboard?.stats.overall_progress}
          color="emerald"
          loading={statsLoading}
        />
        
        <ProgressCard
          title="Total Courses"
          value={dashboard?.stats.total_courses || 0}
          subtitle="Assigned to you"
          icon={<BookOpenIcon className="h-6 w-6" />}
          color="blue"
          loading={statsLoading}
        />
        
        <ProgressCard
          title="Completed"
          value={dashboard?.stats.completed_courses || 0}
          subtitle="Courses finished"
          icon={<CheckCircleIcon className="h-6 w-6" />}
          color="purple"
          loading={statsLoading}
        />
        
        <ProgressCard
          title="Pending"
          value={dashboard?.stats.pending_assignments || 0}
          subtitle="Assignments due"
          icon={<ClockIcon className="h-6 w-6" />}
          color="amber"
          loading={statsLoading}
        />
      </div>
      
      {/* Continue Learning + Deadlines */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Continue Learning */}
        <div className="lg:col-span-2">
          <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">Continue Learning</h2>
              <button 
                onClick={() => navigate('/teacher/courses')}
                className="text-sm text-emerald-600 hover:text-emerald-700 flex items-center"
              >
                View All
                <ArrowRightIcon className="h-4 w-4 ml-1" />
              </button>
            </div>
            
            {continueCourse ? (
              <div 
                className="relative bg-gradient-to-r from-slate-800 to-slate-900 rounded-xl p-6 cursor-pointer group overflow-hidden"
                onClick={() => navigate(`/teacher/courses/${continueCourse.course_id}`)}
              >
                {/* Background pattern */}
                <div className="absolute inset-0 opacity-10">
                  <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_50%,white_1px,transparent_1px)] bg-[size:20px_20px]" />
                </div>
                
                <div className="relative flex items-center">
                  <div className="flex-shrink-0 mr-6">
                    <div className="h-20 w-20 bg-emerald-500/20 rounded-xl flex items-center justify-center group-hover:bg-emerald-500/30 transition-colors">
                      <PlayIcon className="h-10 w-10 text-emerald-400" />
                    </div>
                  </div>
                  
                  <div className="flex-1 min-w-0">
                    <h3 className="text-xl font-semibold text-white mb-1">
                      {continueCourse.course_title}
                    </h3>
                    <p className="text-slate-400 text-sm mb-3 line-clamp-1">
                      {continueCourse.content_title}
                    </p>
                    
                    <div className="flex items-center space-x-4">
                      <div className="flex-1 max-w-xs">
                        <div className="flex justify-between text-xs text-slate-400 mb-1">
                          <span>Lesson progress</span>
                          <span>{continueCourse.progress_percentage}%</span>
                        </div>
                        <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                          <div 
                            className="h-full bg-emerald-500 rounded-full transition-all"
                            style={{ width: `${continueCourse.progress_percentage}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500">
                <BookOpenIcon className="h-12 w-12 mx-auto mb-3 text-gray-400" />
                <p>No courses in progress</p>
                <button 
                  onClick={() => navigate('/teacher/courses')}
                  className="mt-2 text-emerald-600 hover:text-emerald-700"
                >
                  Browse courses
                </button>
              </div>
            )}
          </div>
        </div>
        
        {/* Upcoming Deadlines */}
        <div className="lg:col-span-1">
          <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100 h-full">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">Upcoming Deadlines</h2>
              <CalendarDaysIcon className="h-5 w-5 text-gray-400" />
            </div>
            
            <div className="space-y-3">
              {deadlines?.map((item) => (
                <div 
                  key={item.id}
                  className="flex items-center p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors cursor-pointer"
                  onClick={() =>
                    navigate(item.type === 'course' ? `/teacher/courses/${item.id}` : `/teacher/assignments`)
                  }
                >
                  <div className={`p-2 rounded-lg mr-3 ${
                    item.type === 'course' ? 'bg-blue-100' : 'bg-amber-100'
                  }`}>
                    {item.type === 'course' ? (
                      <BookOpenIcon className="h-4 w-4 text-blue-600" />
                    ) : (
                      <ClockIcon className="h-4 w-4 text-amber-600" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{item.title}</p>
                    <p className={`text-xs ${
                      item.days_left <= 3 ? 'text-red-500' : 'text-gray-500'
                    }`}>
                      {item.days_left === 0 ? 'Due today' : `${item.days_left} days left`}
                    </p>
                  </div>
                </div>
              ))}
              
              {(!deadlines || deadlines.length === 0) && (
                <p className="text-center text-gray-500 py-4">No upcoming deadlines</p>
              )}
            </div>
          </div>
        </div>
      </div>
      
      {/* Recent Courses */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">My Courses</h2>
          <button 
            onClick={() => navigate('/teacher/courses')}
            className="text-sm text-emerald-600 hover:text-emerald-700 flex items-center"
          >
            View All
            <ArrowRightIcon className="h-4 w-4 ml-1" />
          </button>
        </div>
        
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {coursesLoading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <CourseCard key={i} loading id="" title="" description="" progress={0} totalModules={0} completedModules={0} estimatedHours={0} status="NOT_STARTED" />
            ))
          ) : (
            courses?.slice(0, 4).map((course) => (
              <CourseCard
                key={course.id}
                {...toCourseCard(course)}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
};
