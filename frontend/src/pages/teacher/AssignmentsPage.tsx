// src/pages/teacher/AssignmentsPage.tsx

import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { AssignmentCard } from '../../components/teacher';
import { useToast } from '../../components/common';
import { ClipboardDocumentListIcon } from '@heroicons/react/24/outline';
import { teacherService } from '../../services/teacherService';

type TabFilter = 'ALL' | 'PENDING' | 'SUBMITTED';

export const AssignmentsPage: React.FC = () => {
  const toast = useToast();
  const [activeTab, setActiveTab] = useState<TabFilter>('ALL');
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  
  // Fetch all assignments once for accurate counts
  const { data: allAssignments } = useQuery({
    queryKey: ['teacherAssignmentsAll'],
    queryFn: () => teacherService.listAssignments(),
  });

  // Fetch assignments
  const { data: assignments, isLoading } = useQuery({
    queryKey: ['teacherAssignments', activeTab],
    queryFn: () =>
      activeTab === 'ALL'
        ? teacherService.listAssignments()
        : teacherService.listAssignments(activeTab),
  });

  const submitMutation = useMutation({
    mutationFn: (assignmentId: string) => teacherService.submitAssignment(assignmentId, { submission_text: '' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['teacherAssignments'] });
      await queryClient.invalidateQueries({ queryKey: ['teacherAssignments', activeTab] });
      toast.success('Assignment submitted', 'Your assignment has been submitted successfully.');
    },
    onError: () => {
      toast.error('Submission failed', 'Could not submit assignment. Please try again.');
    },
  });
  
  // Count by status
  const statusCounts = {
    ALL: allAssignments?.length || 0,
    PENDING: allAssignments?.filter(a => a.submission_status === 'PENDING').length || 0,
    SUBMITTED: allAssignments?.filter(a => a.submission_status === 'SUBMITTED').length || 0,
  };
  
  const tabs: { key: TabFilter; label: string }[] = [
    { key: 'ALL', label: 'All' },
    { key: 'PENDING', label: 'Pending' },
    { key: 'SUBMITTED', label: 'Submitted' },
  ];
  
  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Assignments</h1>
        <p className="mt-1 text-gray-500">
          View and submit your course assignments
        </p>
      </div>
      
      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-white rounded-xl p-4 border border-gray-100">
          <p className="text-sm text-gray-500">Total</p>
          <p className="text-2xl font-bold text-gray-900">{statusCounts.ALL}</p>
        </div>
        <div className="bg-amber-50 rounded-xl p-4 border border-amber-100">
          <p className="text-sm text-amber-600">Pending</p>
          <p className="text-2xl font-bold text-amber-700">{statusCounts.PENDING}</p>
        </div>
        <div className="bg-blue-50 rounded-xl p-4 border border-blue-100">
          <p className="text-sm text-blue-600">Submitted</p>
          <p className="text-2xl font-bold text-blue-700">{statusCounts.SUBMITTED}</p>
        </div>
      </div>
      
      {/* Tabs */}
      <div className="border-b border-gray-200">
        <nav className="-mb-px flex space-x-8">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                activeTab === tab.key
                  ? 'border-emerald-500 text-emerald-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.label}
              <span className={`ml-2 py-0.5 px-2 rounded-full text-xs ${
                activeTab === tab.key
                  ? 'bg-emerald-100 text-emerald-600'
                  : 'bg-gray-100 text-gray-600'
              }`}>
                {statusCounts[tab.key]}
              </span>
            </button>
          ))}
        </nav>
      </div>
      
      {/* Assignment List */}
      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <AssignmentCard
              key={i}
              loading
              id=""
              title=""
              courseName=""
              description=""
              maxScore={0}
              status="PENDING"
            />
          ))}
        </div>
      ) : assignments && assignments.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {assignments?.map((assignment) => (
            <AssignmentCard
              key={assignment.id}
              id={assignment.id}
              title={assignment.title}
              courseName={assignment.course_title}
              description={assignment.description}
              dueDate={assignment.due_date || undefined}
              maxScore={Number(assignment.max_score || 0)}
              status={assignment.submission_status}
              score={assignment.score ?? undefined}
              feedback={assignment.feedback || undefined}
              isQuiz={Boolean((assignment as any).is_quiz)}
              onSubmit={() => {
                if ((assignment as any).is_quiz) return;
                submitMutation.mutate(assignment.id);
              }}
              onStartQuiz={() => {
                navigate(`/teacher/quizzes/${assignment.id}`);
              }}
              onView={() => {
                if ((assignment as any).is_quiz) {
                  navigate(`/teacher/quizzes/${assignment.id}`);
                  return;
                }
                // For now: fetch submission and log (UI modal can be added later)
                teacherService.getSubmission(assignment.id).then((s) => console.log('Submission', s));
              }}
            />
          ))}
        </div>
      ) : (
        <div className="text-center py-12">
          <ClipboardDocumentListIcon className="h-12 w-12 mx-auto text-gray-400 mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-1">No assignments found</h3>
          <p className="text-gray-500">
            {activeTab === 'ALL' 
              ? 'You don\'t have any assignments yet' 
              : `No ${activeTab.toLowerCase()} assignments`}
          </p>
        </div>
      )}
    </div>
  );
};
