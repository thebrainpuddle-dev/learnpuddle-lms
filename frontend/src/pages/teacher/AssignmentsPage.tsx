// src/pages/teacher/AssignmentsPage.tsx
//
// Assessments page — polished white + orange theme.

import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  ClipboardList,
  Clock,
  CheckCircle2,
  AlertCircle,
  FileText,
  Play,
  Eye,
  Send,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';
import { useToast } from '../../components/common';
import { SubmissionModal } from '../../components/teacher/SubmissionModal';
import {
  teacherService,
  TeacherAssignmentListItem,
  TeacherAssignmentSubmission,
} from '../../services/teacherService';
import { usePageTitle } from '../../hooks/usePageTitle';

type TabFilter = 'ALL' | 'PENDING' | 'SUBMITTED' | 'GRADED';

const TABS: { key: TabFilter; label: string }[] = [
  { key: 'ALL', label: 'All' },
  { key: 'PENDING', label: 'Pending' },
  { key: 'SUBMITTED', label: 'Submitted' },
  { key: 'GRADED', label: 'Graded' },
];

export const AssignmentsPage: React.FC = () => {
  usePageTitle('Assessments');
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabFilter>('ALL');
  const [submissionModalOpen, setSubmissionModalOpen] = useState(false);
  const [selectedAssignment, setSelectedAssignment] =
    useState<TeacherAssignmentListItem | null>(null);
  const [currentSubmission, setCurrentSubmission] =
    useState<TeacherAssignmentSubmission | null>(null);
  const [loadingSubmission, setLoadingSubmission] = useState(false);
  const [submitModalOpen, setSubmitModalOpen] = useState(false);
  const [submitTarget, setSubmitTarget] = useState<TeacherAssignmentListItem | null>(null);
  const [submissionText, setSubmissionText] = useState('');

  const { data: allAssignments = [] } = useQuery({
    queryKey: ['teacherAssignmentsAll'],
    queryFn: () => teacherService.listAssignments(),
  });

  const { data: assignments = [], isLoading } = useQuery({
    queryKey: ['teacherAssignments', activeTab],
    queryFn: () =>
      activeTab === 'ALL'
        ? teacherService.listAssignments()
        : teacherService.listAssignments(
            activeTab as 'PENDING' | 'SUBMITTED' | 'GRADED',
          ),
  });

  const submitMutation = useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) =>
      teacherService.submitAssignment(id, { submission_text: text }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['teacherAssignments'] });
      queryClient.invalidateQueries({ queryKey: ['teacherAssignmentsAll'] });
      toast.success('Submitted', 'Your assessment has been submitted.');
      setSubmitModalOpen(false);
      setSubmitTarget(null);
      setSubmissionText('');
    },
    onError: () => {
      toast.error('Failed', 'Could not submit. Please try again.');
    },
  });

  const handleOpenSubmit = (a: TeacherAssignmentListItem) => {
    setSubmitTarget(a);
    setSubmissionText('');
    setSubmitModalOpen(true);
  };

  const handleViewSubmission = async (a: TeacherAssignmentListItem) => {
    setSelectedAssignment(a);
    setSubmissionModalOpen(true);
    setLoadingSubmission(true);
    setCurrentSubmission(null);
    try {
      const sub = await teacherService.getSubmission(a.id);
      setCurrentSubmission(sub);
    } catch {
      toast.error('Error', 'Could not load submission.');
    } finally {
      setLoadingSubmission(false);
    }
  };

  const counts = {
    ALL: allAssignments.length,
    PENDING: allAssignments.filter((a) => a.submission_status === 'PENDING')
      .length,
    SUBMITTED: allAssignments.filter((a) => a.submission_status === 'SUBMITTED')
      .length,
    GRADED: allAssignments.filter((a) => a.submission_status === 'GRADED')
      .length,
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-[22px] font-bold text-tp-text tracking-tight">
          Assessments
        </h1>
        <p className="mt-0.5 text-[13px] text-gray-400">
          View and submit your course assessments
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-white rounded-2xl border border-gray-100 p-4 text-center shadow-sm">
          <p className="text-[22px] font-bold text-tp-text leading-tight tabular-nums">
            {counts.PENDING}
          </p>
          <p className="text-[10px] text-amber-500 mt-1 font-semibold uppercase tracking-wider">
            Pending
          </p>
        </div>
        <div className="bg-white rounded-2xl border border-gray-100 p-4 text-center shadow-sm">
          <p className="text-[22px] font-bold text-tp-text leading-tight tabular-nums">
            {allAssignments.length > 0
              ? Math.round(
                  allAssignments
                    .filter((a) => a.score !== null)
                    .reduce((acc, a) => acc + (a.score ?? 0), 0) /
                    Math.max(
                      1,
                      allAssignments.filter((a) => a.score !== null).length,
                    ),
                ) + '%'
              : '—'}
          </p>
          <p className="text-[10px] text-tp-accent mt-1 font-semibold uppercase tracking-wider">
            Avg Score
          </p>
        </div>
        <div className="bg-white rounded-2xl border border-gray-100 p-4 text-center shadow-sm">
          <p className="text-[22px] font-bold text-tp-text leading-tight tabular-nums">
            {counts.GRADED + counts.SUBMITTED}
          </p>
          <p className="text-[10px] text-emerald-500 mt-1 font-semibold uppercase tracking-wider">
            Completed
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-0.5 border-b border-gray-200 pb-px overflow-x-auto">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={cn(
              'px-4 py-2.5 text-[13px] font-medium border-b-2 transition-colors whitespace-nowrap',
              activeTab === tab.key
                ? 'border-tp-accent text-tp-accent'
                : 'border-transparent text-gray-400 hover:text-tp-text',
            )}
          >
            {tab.label}
            <span
              className={cn(
                'ml-1.5 px-1.5 py-[2px] rounded-md text-[10px] font-semibold tabular-nums leading-none',
                activeTab === tab.key
                  ? 'bg-orange-50 text-tp-accent'
                  : 'bg-gray-100 text-gray-400',
              )}
            >
              {counts[tab.key]}
            </span>
          </button>
        ))}
      </div>

      {/* List */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 tp-skeleton rounded-2xl" />
          ))}
        </div>
      ) : assignments.length === 0 ? (
        <div className="text-center py-20">
          <ClipboardList className="h-10 w-10 mx-auto text-gray-200 mb-3" />
          <h3 className="text-[15px] font-semibold text-tp-text mb-1">
            No assessments found
          </h3>
          <p className="text-[13px] text-gray-400">
            {activeTab === 'ALL'
              ? "You don't have any assessments yet"
              : `No ${activeTab.toLowerCase()} assessments`}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {assignments.map((a) => {
            const isPending = a.submission_status === 'PENDING';
            const isGraded = a.submission_status === 'GRADED';
            const dueDate = a.due_date ? new Date(a.due_date) : null;
            const now = new Date();
            const isUrgent =
              dueDate &&
              dueDate.getTime() - now.getTime() < 24 * 60 * 60 * 1000 &&
              isPending;
            const isSoon =
              dueDate &&
              dueDate.getTime() - now.getTime() < 3 * 24 * 60 * 60 * 1000 &&
              isPending;

            return (
              <div
                key={a.id}
                className={cn(
                  'bg-white rounded-2xl border p-4 transition-all hover:shadow-md shadow-sm',
                  isUrgent ? 'border-red-200' : 'border-gray-100',
                )}
              >
                <div className="flex items-start justify-between gap-3 mb-2.5">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      {a.is_quiz ? (
                        <div className="h-6 w-6 rounded-md bg-orange-50 flex items-center justify-center flex-shrink-0">
                          <FileText className="h-3.5 w-3.5 text-tp-accent" />
                        </div>
                      ) : (
                        <div className="h-6 w-6 rounded-md bg-blue-50 flex items-center justify-center flex-shrink-0">
                          <ClipboardList className="h-3.5 w-3.5 text-blue-500" />
                        </div>
                      )}
                      <h3 className="text-[13px] font-semibold text-tp-text truncate leading-tight">
                        {a.title}
                      </h3>
                    </div>
                    <p className="text-[11px] text-gray-400 ml-8">{a.course_title}</p>
                  </div>
                  <span
                    className={cn(
                      'px-2 py-[3px] rounded-md text-[10px] font-semibold uppercase tracking-wide flex-shrink-0 leading-none',
                      isPending
                        ? 'bg-amber-50 text-amber-600'
                        : isGraded
                          ? 'bg-emerald-50 text-emerald-600'
                          : 'bg-blue-50 text-blue-600',
                    )}
                  >
                    {a.submission_status}
                  </span>
                </div>

                {isGraded && a.score !== null && (
                  <div className="mb-2.5 ml-8 flex items-center gap-2">
                    <div className="h-7 w-7 rounded-full bg-emerald-50 flex items-center justify-center">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                    </div>
                    <div>
                      <p className="text-[13px] font-semibold text-tp-text tabular-nums">
                        {a.score}/{a.max_score}
                      </p>
                      <p className="text-[9px] text-gray-400 uppercase tracking-wider font-semibold">
                        Score
                      </p>
                    </div>
                  </div>
                )}

                <div className="flex items-center gap-3 text-[11px] text-gray-400 mb-3 ml-8">
                  <span className="flex items-center gap-1 font-medium">
                    <FileText className="h-3 w-3" />
                    {a.is_quiz ? 'Quiz' : 'Assignment'}
                  </span>
                  {dueDate && (
                    <span
                      className={cn(
                        'flex items-center gap-1 font-medium',
                        isUrgent
                          ? 'text-red-500'
                          : isSoon
                            ? 'text-amber-500'
                            : '',
                      )}
                    >
                      {isUrgent && <AlertCircle className="h-3 w-3" />}
                      <Clock className="h-3 w-3" />
                      {dueDate.toLocaleDateString('en-US', {
                        month: 'short',
                        day: 'numeric',
                      })}
                    </span>
                  )}
                </div>

                <div className="flex items-center gap-2 ml-8">
                  {isPending && a.is_quiz && (
                    <button
                      onClick={() => navigate(`/teacher/quizzes/${a.id}`)}
                      className="inline-flex items-center gap-1.5 px-3 py-[6px] rounded-lg text-[11px] font-semibold bg-tp-accent text-white hover:bg-tp-accent-dark transition-colors shadow-sm"
                    >
                      <Play className="h-3 w-3" />
                      Start Quiz
                    </button>
                  )}
                  {isPending && !a.is_quiz && (
                    <button
                      onClick={() => handleOpenSubmit(a)}
                      className="inline-flex items-center gap-1.5 px-3 py-[6px] rounded-lg text-[11px] font-semibold bg-tp-accent text-white hover:bg-tp-accent-dark transition-colors shadow-sm"
                    >
                      <Send className="h-3 w-3" />
                      Submit
                    </button>
                  )}
                  {!isPending && (
                    <button
                      onClick={() => {
                        if (a.is_quiz) {
                          navigate(`/teacher/quizzes/${a.id}`);
                        } else {
                          handleViewSubmission(a);
                        }
                      }}
                      className="inline-flex items-center gap-1.5 px-3 py-[6px] rounded-lg text-[11px] font-semibold bg-gray-50 border border-gray-200 text-gray-600 hover:text-tp-text hover:bg-gray-100 transition-colors"
                    >
                      <Eye className="h-3 w-3" />
                      View
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <SubmissionModal
        isOpen={submissionModalOpen}
        onClose={() => {
          setSubmissionModalOpen(false);
          setSelectedAssignment(null);
          setCurrentSubmission(null);
        }}
        submission={currentSubmission}
        assignmentTitle={selectedAssignment?.title}
        maxScore={
          selectedAssignment?.max_score
            ? Number(selectedAssignment.max_score)
            : undefined
        }
        isLoading={loadingSubmission}
      />

      {/* Submit Assignment Modal */}
      {submitModalOpen && submitTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-2xl shadow-xl border border-gray-100 w-full max-w-lg mx-4">
            <div className="px-5 py-4 border-b border-gray-100">
              <h3 className="text-[15px] font-semibold text-slate-900">
                Submit: {submitTarget.title}
              </h3>
              <p className="text-[12px] text-gray-400 mt-0.5">
                {submitTarget.course_title}
              </p>
            </div>
            <div className="px-5 py-4">
              <label className="block text-[13px] font-medium text-slate-700 mb-1.5">
                Your response
              </label>
              <textarea
                rows={6}
                value={submissionText}
                onChange={(e) => setSubmissionText(e.target.value)}
                placeholder="Type your answer or reflection here..."
                className="w-full px-3 py-2.5 border border-gray-200 rounded-xl text-[13px] focus:ring-2 focus:ring-orange-500/20 focus:border-orange-400 placeholder:text-gray-400 resize-none"
              />
            </div>
            <div className="flex items-center justify-end gap-2 px-5 py-3.5 border-t border-gray-100">
              <button
                onClick={() => {
                  setSubmitModalOpen(false);
                  setSubmitTarget(null);
                  setSubmissionText('');
                }}
                className="px-4 py-2 rounded-lg text-[13px] font-medium text-gray-600 hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() =>
                  submitMutation.mutate({ id: submitTarget.id, text: submissionText })
                }
                disabled={submitMutation.isPending}
                className={cn(
                  'inline-flex items-center gap-1.5 px-4 py-2 rounded-lg text-[13px] font-semibold text-white bg-tp-accent hover:bg-orange-600 transition-colors shadow-sm',
                  submitMutation.isPending && 'opacity-60 cursor-not-allowed',
                )}
              >
                {submitMutation.isPending ? (
                  <>
                    <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Submitting...
                  </>
                ) : (
                  <>
                    <Send className="h-3.5 w-3.5" />
                    Submit
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
