// src/pages/student/AssignmentsPage.tsx
//
// Student assignments page — indigo accent, tab filtering, submission modal.

import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  ClipboardList,
  Clock,
  CheckCircle2,
  XCircle,
  AlertCircle,
  FileText,
  Play,
  Eye,
  Send,
  ChevronDown,
  ChevronUp,
  X,
  Link as LinkIcon,
  Inbox,
  Loader2,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';
import { useToast } from '../../components/common';
import {
  studentService,
  StudentAssignmentListItem,
} from '../../services/studentService';
import { usePageTitle } from '../../hooks/usePageTitle';

// ─── Types ───────────────────────────────────────────────────────────────────

type TabFilter = 'ALL' | 'PENDING' | 'SUBMITTED' | 'GRADED';

const TABS: { key: TabFilter; label: string }[] = [
  { key: 'ALL', label: 'All' },
  { key: 'PENDING', label: 'Pending' },
  { key: 'SUBMITTED', label: 'Submitted' },
  { key: 'GRADED', label: 'Graded' },
];

const EMPTY_MESSAGES: Record<TabFilter, { title: string; subtitle: string }> = {
  ALL: {
    title: 'No assignments yet',
    subtitle: 'Assignments from your courses will appear here.',
  },
  PENDING: {
    title: 'All caught up!',
    subtitle: 'No pending assignments — you\'re all caught up!',
  },
  SUBMITTED: {
    title: 'Nothing submitted',
    subtitle: 'Assignments you submit will appear here while awaiting review.',
  },
  GRADED: {
    title: 'No graded assignments',
    subtitle: 'Your graded assignments and feedback will show up here.',
  },
};

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getDaysLeft(dueDate: string): number {
  const now = new Date();
  const due = new Date(dueDate);
  return Math.ceil((due.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
}

function formatDueLabel(dueDate: string): string {
  const days = getDaysLeft(dueDate);
  if (days < 0) return `${Math.abs(days)}d overdue`;
  if (days === 0) return 'Due today';
  if (days === 1) return 'Due tomorrow';
  return `${days}d left`;
}

// ─── Submission Modal ────────────────────────────────────────────────────────

function SubmissionModal({
  isOpen,
  onClose,
  assignment,
  onSubmit,
  isSubmitting,
}: {
  isOpen: boolean;
  onClose: () => void;
  assignment: StudentAssignmentListItem | null;
  onSubmit: (data: { submission_text?: string; file_url?: string }) => void;
  isSubmitting: boolean;
}) {
  const [submissionText, setSubmissionText] = useState('');
  const [fileUrl, setFileUrl] = useState('');

  if (!isOpen || !assignment) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onSubmit({
      submission_text: submissionText || undefined,
      file_url: fileUrl || undefined,
    });
  };

  const handleClose = () => {
    setSubmissionText('');
    setFileUrl('');
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="min-w-0">
            <h2 className="text-[15px] font-semibold text-tp-text truncate">
              Submit Assignment
            </h2>
            <p className="text-[12px] text-gray-400 truncate mt-0.5">
              {assignment.title}
            </p>
          </div>
          <button
            onClick={handleClose}
            className="h-8 w-8 rounded-lg flex items-center justify-center text-gray-400 hover:text-tp-text hover:bg-gray-100 transition-colors flex-shrink-0"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Instructions preview */}
          {assignment.instructions && (
            <div className="bg-indigo-50/50 rounded-xl p-3.5 border border-indigo-100/50">
              <p className="text-[11px] font-semibold text-indigo-600 uppercase tracking-wider mb-1">
                Instructions
              </p>
              <p className="text-[12px] text-gray-600 leading-relaxed">
                {assignment.instructions}
              </p>
            </div>
          )}

          {/* Submission text */}
          <div>
            <label className="block text-[12px] font-medium text-tp-text mb-1.5">
              Your Answer
            </label>
            <textarea
              value={submissionText}
              onChange={(e) => setSubmissionText(e.target.value)}
              rows={5}
              placeholder="Type your submission here..."
              className="w-full rounded-xl border border-gray-200 px-4 py-3 text-[13px] text-tp-text placeholder:text-gray-400 focus:border-indigo-400/40 focus:ring-2 focus:ring-indigo-400/10 transition-all resize-none"
            />
          </div>

          {/* File URL */}
          <div>
            <label className="block text-[12px] font-medium text-tp-text mb-1.5">
              File URL
              <span className="text-gray-400 font-normal ml-1">(optional)</span>
            </label>
            <div className="relative">
              <LinkIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
              <input
                type="url"
                value={fileUrl}
                onChange={(e) => setFileUrl(e.target.value)}
                placeholder="https://..."
                className="w-full rounded-xl border border-gray-200 pl-9 pr-4 py-2.5 text-[13px] text-tp-text placeholder:text-gray-400 focus:border-indigo-400/40 focus:ring-2 focus:ring-indigo-400/10 transition-all"
              />
            </div>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={handleClose}
              disabled={isSubmitting}
              className="px-4 py-2 rounded-lg text-[12px] font-medium text-gray-600 hover:text-tp-text hover:bg-gray-100 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting || (!submissionText.trim() && !fileUrl.trim())}
              className="inline-flex items-center gap-1.5 px-5 py-2 rounded-lg text-[12px] font-semibold bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
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
        </form>
      </div>
    </div>
  );
}

// ─── Assignment Card ─────────────────────────────────────────────────────────

function AssignmentCard({
  assignment,
  onSubmit,
  onNavigateQuiz,
}: {
  assignment: StudentAssignmentListItem;
  onSubmit: (a: StudentAssignmentListItem) => void;
  onNavigateQuiz: (id: string) => void;
}) {
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  const isPending = assignment.submission_status === 'PENDING';
  const isSubmitted = assignment.submission_status === 'SUBMITTED';
  const isGraded = assignment.submission_status === 'GRADED';
  const dueDate = assignment.due_date;
  const daysLeft = dueDate ? getDaysLeft(dueDate) : null;
  const isOverdue = daysLeft !== null && daysLeft < 0 && isPending;
  const isSoon = daysLeft !== null && daysLeft >= 0 && daysLeft < 3 && isPending;
  const passed =
    isGraded &&
    assignment.score !== null &&
    assignment.score >= Number(assignment.passing_score);

  return (
    <div
      className={cn(
        'bg-white rounded-2xl border p-4 transition-all hover:shadow-md shadow-sm',
        isOverdue ? 'border-red-200' : 'border-gray-100',
      )}
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-2.5">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            {assignment.is_quiz ? (
              <div className="h-6 w-6 rounded-md bg-indigo-50 flex items-center justify-center flex-shrink-0">
                <FileText className="h-3.5 w-3.5 text-indigo-600" />
              </div>
            ) : (
              <div className="h-6 w-6 rounded-md bg-indigo-50 flex items-center justify-center flex-shrink-0">
                <ClipboardList className="h-3.5 w-3.5 text-indigo-600" />
              </div>
            )}
            <h3 className="text-[13px] font-semibold text-tp-text truncate leading-tight">
              {assignment.title}
            </h3>
            {assignment.is_quiz && (
              <span className="px-1.5 py-[2px] rounded text-[9px] font-bold uppercase tracking-wider bg-violet-50 text-violet-600 flex-shrink-0">
                Quiz
              </span>
            )}
          </div>
          <p className="text-[11px] text-gray-400 ml-8">{assignment.course_title}</p>
        </div>

        {/* Status badge */}
        <span
          className={cn(
            'px-2 py-[3px] rounded-md text-[10px] font-semibold uppercase tracking-wide flex-shrink-0 leading-none',
            isPending
              ? 'bg-gray-100 text-gray-500'
              : isSubmitted
                ? 'bg-blue-50 text-blue-600'
                : passed
                  ? 'bg-emerald-50 text-emerald-600'
                  : 'bg-red-50 text-red-600',
          )}
        >
          {assignment.submission_status}
        </span>
      </div>

      {/* Description */}
      {assignment.description && (
        <p className="text-[12px] text-gray-500 ml-8 mb-2.5 line-clamp-2 leading-relaxed">
          {assignment.description}
        </p>
      )}

      {/* Graded score display */}
      {isGraded && assignment.score !== null && (
        <div className="mb-2.5 ml-8 flex items-center gap-2">
          <div
            className={cn(
              'h-7 w-7 rounded-full flex items-center justify-center',
              passed ? 'bg-emerald-50' : 'bg-red-50',
            )}
          >
            {passed ? (
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
            ) : (
              <XCircle className="h-3.5 w-3.5 text-red-500" />
            )}
          </div>
          <div>
            <p className="text-[13px] font-semibold text-tp-text tabular-nums">
              {assignment.score}/{assignment.max_score}
            </p>
            <p className="text-[9px] text-gray-400 uppercase tracking-wider font-semibold">
              Score (pass: {assignment.passing_score})
            </p>
          </div>
        </div>
      )}

      {/* Meta row: type + due date */}
      <div className="flex items-center gap-3 text-[11px] text-gray-400 mb-3 ml-8">
        <span className="flex items-center gap-1 font-medium">
          <FileText className="h-3 w-3" />
          {assignment.is_quiz ? 'Quiz' : 'Assignment'}
        </span>
        {assignment.is_mandatory && (
          <span className="flex items-center gap-1 font-medium text-amber-500">
            <AlertCircle className="h-3 w-3" />
            Required
          </span>
        )}
        {dueDate && (
          <span
            className={cn(
              'flex items-center gap-1 font-medium',
              isOverdue
                ? 'text-red-500'
                : isSoon
                  ? 'text-amber-500'
                  : '',
            )}
          >
            {isOverdue && <AlertCircle className="h-3 w-3" />}
            <Clock className="h-3 w-3" />
            {new Date(dueDate).toLocaleDateString('en-US', {
              month: 'short',
              day: 'numeric',
            })}
            <span className="text-[10px]">({formatDueLabel(dueDate)})</span>
          </span>
        )}
      </div>

      {/* Feedback (expandable) */}
      {isGraded && assignment.feedback && (
        <div className="ml-8 mb-3">
          <button
            onClick={() => setFeedbackOpen(!feedbackOpen)}
            className="flex items-center gap-1 text-[11px] font-medium text-indigo-600 hover:text-indigo-700 transition-colors"
          >
            {feedbackOpen ? (
              <ChevronUp className="h-3 w-3" />
            ) : (
              <ChevronDown className="h-3 w-3" />
            )}
            {feedbackOpen ? 'Hide feedback' : 'View feedback'}
          </button>
          {feedbackOpen && (
            <div className="mt-2 bg-gray-50 rounded-xl p-3 border border-gray-100">
              <p className="text-[12px] text-gray-600 leading-relaxed whitespace-pre-wrap">
                {assignment.feedback}
              </p>
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      <div className="flex items-center gap-2 ml-8">
        {isPending && assignment.is_quiz && (
          <button
            onClick={() => onNavigateQuiz(assignment.id)}
            className="inline-flex items-center gap-1.5 px-3 py-[6px] rounded-lg text-[11px] font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition-colors shadow-sm"
          >
            <Play className="h-3 w-3" />
            Start Quiz
          </button>
        )}
        {isPending && !assignment.is_quiz && (
          <button
            onClick={() => onSubmit(assignment)}
            className="inline-flex items-center gap-1.5 px-3 py-[6px] rounded-lg text-[11px] font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition-colors shadow-sm"
          >
            <Send className="h-3 w-3" />
            Submit
          </button>
        )}
        {isSubmitted && assignment.is_quiz && (
          <button
            onClick={() => onNavigateQuiz(assignment.id)}
            className="inline-flex items-center gap-1.5 px-3 py-[6px] rounded-lg text-[11px] font-semibold bg-gray-50 border border-gray-200 text-gray-600 hover:text-tp-text hover:bg-gray-100 transition-colors"
          >
            <Eye className="h-3 w-3" />
            View Quiz
          </button>
        )}
        {isGraded && assignment.is_quiz && (
          <button
            onClick={() => onNavigateQuiz(assignment.id)}
            className="inline-flex items-center gap-1.5 px-3 py-[6px] rounded-lg text-[11px] font-semibold bg-gray-50 border border-gray-200 text-gray-600 hover:text-tp-text hover:bg-gray-100 transition-colors"
          >
            <Eye className="h-3 w-3" />
            Review Quiz
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────────────────────────

export const AssignmentsPage: React.FC = () => {
  usePageTitle('Assignments');
  const toast = useToast();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<TabFilter>('ALL');
  const [submissionModal, setSubmissionModal] = useState<{
    open: boolean;
    assignment: StudentAssignmentListItem | null;
  }>({ open: false, assignment: null });

  // Fetch all assignments (for counts)
  const { data: allAssignments = [] } = useQuery({
    queryKey: ['studentAssignmentsAll'],
    queryFn: () => studentService.getStudentAssignments(),
  });

  // Fetch filtered assignments
  const { data: assignments = [], isLoading } = useQuery({
    queryKey: ['studentAssignments', activeTab],
    queryFn: () =>
      activeTab === 'ALL'
        ? studentService.getStudentAssignments()
        : studentService.getStudentAssignments(
            activeTab as 'PENDING' | 'SUBMITTED' | 'GRADED',
          ),
  });

  // Submit mutation
  const submitMutation = useMutation({
    mutationFn: ({
      assignmentId,
      data,
    }: {
      assignmentId: string;
      data: { submission_text?: string; file_url?: string };
    }) => studentService.submitAssignment(assignmentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['studentAssignments'] });
      queryClient.invalidateQueries({ queryKey: ['studentAssignmentsAll'] });
      setSubmissionModal({ open: false, assignment: null });
      toast.success('Submitted!', 'Your assignment has been submitted successfully.');
    },
    onError: () => {
      toast.error('Submission failed', 'Could not submit your assignment. Please try again.');
    },
  });

  // Tab counts
  const counts: Record<TabFilter, number> = {
    ALL: allAssignments.length,
    PENDING: allAssignments.filter((a) => a.submission_status === 'PENDING').length,
    SUBMITTED: allAssignments.filter((a) => a.submission_status === 'SUBMITTED').length,
    GRADED: allAssignments.filter((a) => a.submission_status === 'GRADED').length,
  };

  return (
    <div className="space-y-5">
      {/* Header */}
      <div>
        <h1 className="text-[22px] font-bold text-tp-text tracking-tight">
          Assignments
        </h1>
        <p className="mt-0.5 text-[13px] text-gray-400">
          {allAssignments.length === 0
            ? 'Your course assignments'
            : `${allAssignments.length} assignment${allAssignments.length !== 1 ? 's' : ''} across your courses`}
        </p>
      </div>

      {/* Stats row */}
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
              ? (() => {
                  const graded = allAssignments.filter((a) => a.score !== null);
                  return graded.length > 0
                    ? Math.round(
                        graded.reduce((acc, a) => acc + (a.score ?? 0), 0) /
                          graded.length,
                      ) + '%'
                    : '\u2014';
                })()
              : '\u2014'}
          </p>
          <p className="text-[10px] text-indigo-600 mt-1 font-semibold uppercase tracking-wider">
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
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-gray-400 hover:text-tp-text',
            )}
          >
            {tab.label}
            <span
              className={cn(
                'ml-1.5 px-1.5 py-[2px] rounded-md text-[10px] font-semibold tabular-nums leading-none',
                activeTab === tab.key
                  ? 'bg-indigo-50 text-indigo-600'
                  : 'bg-gray-100 text-gray-400',
              )}
            >
              {counts[tab.key]}
            </span>
          </button>
        ))}
      </div>

      {/* Assignment list */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 tp-skeleton rounded-2xl" />
          ))}
        </div>
      ) : assignments.length === 0 ? (
        <div className="text-center py-20">
          <Inbox className="h-10 w-10 mx-auto text-gray-200 mb-3" />
          <h3 className="text-[15px] font-semibold text-tp-text mb-1">
            {EMPTY_MESSAGES[activeTab].title}
          </h3>
          <p className="text-[13px] text-gray-400">
            {EMPTY_MESSAGES[activeTab].subtitle}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {assignments.map((a) => (
            <AssignmentCard
              key={a.id}
              assignment={a}
              onSubmit={(assignment) =>
                setSubmissionModal({ open: true, assignment })
              }
              onNavigateQuiz={(id) => navigate(`/student/quizzes/${id}`)}
            />
          ))}
        </div>
      )}

      {/* Submission Modal */}
      <SubmissionModal
        isOpen={submissionModal.open}
        onClose={() => setSubmissionModal({ open: false, assignment: null })}
        assignment={submissionModal.assignment}
        onSubmit={(data) => {
          if (submissionModal.assignment) {
            submitMutation.mutate({
              assignmentId: submissionModal.assignment.id,
              data,
            });
          }
        }}
        isSubmitting={submitMutation.isPending}
      />
    </div>
  );
};
