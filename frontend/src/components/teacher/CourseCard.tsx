// src/components/teacher/CourseCard.tsx

import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ClockIcon, BookOpenIcon, CheckCircleIcon } from '@heroicons/react/24/outline';
import { PlayIcon } from '@heroicons/react/24/solid';

interface CourseCardProps {
  id: string;
  title: string;
  description: string;
  thumbnail?: string;
  progress: number;
  totalModules: number;
  completedModules: number;
  estimatedHours: number;
  deadline?: string;
  status: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';
  loading?: boolean;
}

export const CourseCard: React.FC<CourseCardProps> = ({
  id,
  title,
  description,
  thumbnail,
  progress,
  totalModules,
  completedModules,
  estimatedHours,
  deadline,
  status,
  loading,
}) => {
  const navigate = useNavigate();
  
  if (loading) {
    return (
      <div className="bg-white rounded-xl overflow-hidden shadow-sm border border-gray-100">
        <div className="animate-pulse">
          <div className="h-40 bg-gray-200"></div>
          <div className="p-4">
            <div className="h-5 bg-gray-200 rounded w-3/4 mb-2"></div>
            <div className="h-4 bg-gray-200 rounded w-full mb-4"></div>
            <div className="h-2 bg-gray-200 rounded w-full mb-4"></div>
            <div className="flex justify-between">
              <div className="h-4 bg-gray-200 rounded w-20"></div>
              <div className="h-4 bg-gray-200 rounded w-20"></div>
            </div>
          </div>
        </div>
      </div>
    );
  }
  
  const statusColors = {
    NOT_STARTED: 'bg-gray-100 text-gray-600',
    IN_PROGRESS: 'bg-blue-100 text-blue-700',
    COMPLETED: 'bg-emerald-100 text-emerald-700',
  };
  
  const statusLabels = {
    NOT_STARTED: 'Not Started',
    IN_PROGRESS: 'In Progress',
    COMPLETED: 'Completed',
  };
  
  const daysUntilDeadline = deadline
    ? Math.ceil((new Date(deadline).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
    : null;
  
  return (
    <div 
      className="group bg-white rounded-xl overflow-hidden shadow-sm border border-gray-100 hover:shadow-lg hover:border-emerald-200 transition-all duration-300 cursor-pointer"
      onClick={() => navigate(`/teacher/courses/${id}`)}
    >
      {/* Thumbnail */}
      <div className="relative h-40 bg-gradient-to-br from-slate-700 to-slate-900 overflow-hidden">
        {thumbnail ? (
          <img src={thumbnail} alt={title} className="w-full h-full object-cover" />
        ) : (
          <div className="absolute inset-0 flex items-center justify-center">
            <BookOpenIcon className="h-16 w-16 text-slate-600" />
          </div>
        )}
        
        {/* Status badge */}
        <div className={`absolute top-3 left-3 px-2 py-1 rounded-full text-xs font-medium ${statusColors[status]}`}>
          {statusLabels[status]}
        </div>
        
        {/* Play button overlay */}
        <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
          <div className="bg-white/90 rounded-full p-3 transform scale-90 group-hover:scale-100 transition-transform">
            <PlayIcon className="h-8 w-8 text-emerald-600" />
          </div>
        </div>
        
        {/* Deadline warning */}
        {daysUntilDeadline !== null && daysUntilDeadline <= 7 && daysUntilDeadline > 0 && (
          <div className="absolute top-3 right-3 px-2 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-700">
            {daysUntilDeadline} days left
          </div>
        )}
        
        {status === 'COMPLETED' && (
          <div className="absolute top-3 right-3">
            <CheckCircleIcon className="h-8 w-8 text-emerald-400 bg-white rounded-full" />
          </div>
        )}
      </div>
      
      {/* Content */}
      <div className="p-4">
        <h3 className="font-semibold text-gray-900 mb-1 line-clamp-1 group-hover:text-emerald-600 transition-colors">
          {title}
        </h3>
        <p className="text-sm text-gray-500 line-clamp-2 mb-3">{description}</p>
        
        {/* Progress bar */}
        <div className="mb-3">
          <div className="flex justify-between text-xs text-gray-500 mb-1">
            <span>{completedModules}/{totalModules} lessons</span>
            <span>{progress}%</span>
          </div>
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div 
              className={`h-full rounded-full transition-all duration-500 ${
                status === 'COMPLETED' ? 'bg-emerald-500' : 'bg-blue-500'
              }`}
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
        
        {/* Meta info */}
        <div className="flex items-center justify-between text-xs text-gray-500">
          <div className="flex items-center">
            <ClockIcon className="h-4 w-4 mr-1" />
            {estimatedHours}h
          </div>
          <div className="flex items-center">
            <BookOpenIcon className="h-4 w-4 mr-1" />
            {totalModules} lessons
          </div>
        </div>
      </div>
    </div>
  );
};
