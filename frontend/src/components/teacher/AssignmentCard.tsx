// src/components/teacher/AssignmentCard.tsx

import React from 'react';
import { 
  ClipboardDocumentCheckIcon,
  ClockIcon,
  CheckCircleIcon,
  ExclamationCircleIcon,
} from '@heroicons/react/24/outline';

interface AssignmentCardProps {
  id: string;
  title: string;
  courseName: string;
  description: string;
  dueDate?: string;
  maxScore: number;
  status: 'PENDING' | 'SUBMITTED' | 'GRADED';
  score?: number;
  feedback?: string;
  isQuiz?: boolean;
  onSubmit?: () => void;
  onStartQuiz?: () => void;
  onView?: () => void;
  loading?: boolean;
}

export const AssignmentCard: React.FC<AssignmentCardProps> = ({
  id,
  title,
  courseName,
  description,
  dueDate,
  maxScore,
  status,
  score,
  feedback,
  isQuiz = false,
  onSubmit,
  onStartQuiz,
  onView,
  loading,
}) => {
  if (loading) {
    return (
      <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-100">
        <div className="animate-pulse">
          <div className="flex items-start justify-between mb-4">
            <div className="flex-1">
              <div className="h-5 bg-gray-200 rounded w-3/4 mb-2"></div>
              <div className="h-4 bg-gray-200 rounded w-1/2"></div>
            </div>
            <div className="h-6 w-20 bg-gray-200 rounded-full"></div>
          </div>
          <div className="h-4 bg-gray-200 rounded w-full mb-4"></div>
          <div className="flex justify-between">
            <div className="h-4 bg-gray-200 rounded w-24"></div>
            <div className="h-8 bg-gray-200 rounded w-24"></div>
          </div>
        </div>
      </div>
    );
  }
  
  const statusConfig = {
    PENDING: {
      bg: 'bg-amber-50',
      border: 'border-amber-200',
      badge: 'bg-amber-100 text-amber-700',
      icon: ClockIcon,
      label: 'Pending',
    },
    SUBMITTED: {
      bg: 'bg-blue-50',
      border: 'border-blue-200',
      badge: 'bg-blue-100 text-blue-700',
      icon: ClipboardDocumentCheckIcon,
      label: 'Submitted',
    },
    GRADED: {
      bg: 'bg-emerald-50',
      border: 'border-emerald-200',
      badge: 'bg-emerald-100 text-emerald-700',
      icon: CheckCircleIcon,
      label: 'Graded',
    },
  };
  
  const config = statusConfig[status];
  const StatusIcon = config.icon;
  
  const isOverdue = dueDate && new Date(dueDate) < new Date() && status === 'PENDING';
  const daysUntilDue = dueDate
    ? Math.ceil((new Date(dueDate).getTime() - Date.now()) / (1000 * 60 * 60 * 24))
    : null;
  
  return (
    <div className={`rounded-xl border p-4 transition-all hover:shadow-md sm:p-6 ${config.bg} ${config.border}`}>
      {/* Header */}
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-gray-900 mb-1">{title}</h3>
          <p className="truncate text-sm text-gray-500">{courseName}</p>
        </div>
        <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${config.badge}`}>
          <StatusIcon className="h-3.5 w-3.5 mr-1" />
          {config.label}
        </span>
      </div>
      
      {/* Description */}
      <p className="text-sm text-gray-600 mb-4 line-clamp-2">{description}</p>
      
      {/* Due date */}
      {dueDate && (
        <div className={`flex items-center text-sm mb-4 ${isOverdue ? 'text-red-600' : 'text-gray-500'}`}>
          {isOverdue ? (
            <>
              <ExclamationCircleIcon className="h-4 w-4 mr-1" />
              Overdue
            </>
          ) : (
            <>
              <ClockIcon className="h-4 w-4 mr-1" />
              {daysUntilDue !== null && daysUntilDue >= 0 ? (
                daysUntilDue === 0 ? 'Due today' : `Due in ${daysUntilDue} days`
              ) : (
                `Due: ${new Date(dueDate).toLocaleDateString()}`
              )}
            </>
          )}
        </div>
      )}
      
      {/* Score (for graded) */}
      {status === 'GRADED' && score !== undefined && (
        <div className="mb-4 p-3 bg-white rounded-lg">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm text-gray-600">Score</span>
            <span className={`font-semibold ${score >= maxScore * 0.7 ? 'text-emerald-600' : 'text-amber-600'}`}>
              {score}/{maxScore}
            </span>
          </div>
          {feedback && (
            <p className="text-sm text-gray-500 mt-2 italic">"{feedback}"</p>
          )}
        </div>
      )}
      
      {/* Actions */}
      <div className="flex flex-col gap-3 border-t border-gray-200/50 pt-3 sm:flex-row sm:items-center sm:justify-between">
        <span className="text-sm text-gray-500">
          Max Score: {maxScore}
        </span>
        
        {status === 'PENDING' && !isQuiz && (
          <button
            onClick={onSubmit}
            className="w-full rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 sm:w-auto"
          >
            Submit
          </button>
        )}

        {status === 'PENDING' && isQuiz && (
          <button
            onClick={onStartQuiz}
            className="w-full rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-700 sm:w-auto"
          >
            Start Quiz
          </button>
        )}
        
        {(status === 'SUBMITTED' || status === 'GRADED') && (
          <button
            onClick={onView}
            className="w-full rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 sm:w-auto"
          >
            View Submission
          </button>
        )}
      </div>
    </div>
  );
};
