// src/components/teacher/SubmissionModal.tsx

import React, { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import {
  XMarkIcon,
  DocumentTextIcon,
  DocumentArrowDownIcon,
  CheckCircleIcon,
  ClockIcon,
  ChatBubbleLeftEllipsisIcon,
} from '@heroicons/react/24/outline';
import { TeacherAssignmentSubmission } from '../../services/teacherService';

interface SubmissionModalProps {
  isOpen: boolean;
  onClose: () => void;
  submission: TeacherAssignmentSubmission | null;
  assignmentTitle?: string;
  maxScore?: number;
  isLoading?: boolean;
}

export const SubmissionModal: React.FC<SubmissionModalProps> = ({
  isOpen,
  onClose,
  submission,
  assignmentTitle,
  maxScore,
  isLoading = false,
}) => {
  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'GRADED':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
            <CheckCircleIcon className="w-4 h-4 mr-1" />
            Graded
          </span>
        );
      case 'SUBMITTED':
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
            <ClockIcon className="w-4 h-4 mr-1" />
            Submitted
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
            Pending
          </span>
        );
    }
  };

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/30" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-end justify-center p-2 text-center sm:items-center sm:p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 translate-y-3 sm:translate-y-0 sm:scale-95"
              enterTo="opacity-100 translate-y-0 sm:scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 translate-y-0 sm:scale-100"
              leaveTo="opacity-0 translate-y-3 sm:translate-y-0 sm:scale-95"
            >
              <Dialog.Panel className="w-full max-w-2xl transform overflow-hidden rounded-t-2xl bg-white p-4 text-left align-middle shadow-xl transition-all sm:rounded-2xl sm:p-6">
                {/* Header */}
                <div className="mb-6 flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <Dialog.Title as="h3" className="text-lg font-semibold text-gray-900">
                      Submission Details
                    </Dialog.Title>
                    {assignmentTitle && (
                      <p className="mt-1 truncate text-sm text-gray-500">{assignmentTitle}</p>
                    )}
                  </div>
                  <button
                    onClick={onClose}
                    className="rounded-full p-1 hover:bg-gray-100 transition-colors"
                  >
                    <XMarkIcon className="h-6 w-6 text-gray-400" />
                  </button>
                </div>

                {isLoading ? (
                  <div className="flex items-center justify-center py-12">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-600"></div>
                  </div>
                ) : submission ? (
                  <div className="space-y-6">
                    {/* Status and Score */}
                    <div className="rounded-lg bg-gray-50 p-4">
                      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
                        {getStatusBadge(submission.status)}
                        <span className="text-sm text-gray-500">
                          Submitted {formatDate(submission.submitted_at)}
                        </span>
                      </div>
                        {submission.status === 'GRADED' && submission.score !== null && (
                          <div className="text-left sm:text-right">
                            <span className="text-2xl font-bold text-emerald-600">
                              {submission.score}
                            </span>
                            {maxScore && (
                              <span className="text-gray-500 text-lg">/{maxScore}</span>
                            )}
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Submission Text */}
                    {submission.submission_text && (
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <DocumentTextIcon className="h-5 w-5 text-gray-400" />
                          <h4 className="font-medium text-gray-900">Your Response</h4>
                        </div>
                        <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
                          <p className="text-gray-700 whitespace-pre-wrap">
                            {submission.submission_text}
                          </p>
                        </div>
                      </div>
                    )}

                    {/* Attached File */}
                    {submission.file_url && (
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <DocumentArrowDownIcon className="h-5 w-5 text-gray-400" />
                          <h4 className="font-medium text-gray-900">Attached File</h4>
                        </div>
                        <a
                          href={submission.file_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-2 px-4 py-2 bg-emerald-50 text-emerald-700 rounded-lg hover:bg-emerald-100 transition-colors"
                        >
                          <DocumentArrowDownIcon className="h-5 w-5" />
                          Download Attachment
                        </a>
                      </div>
                    )}

                    {/* Feedback */}
                    {submission.feedback && (
                      <div>
                        <div className="flex items-center gap-2 mb-2">
                          <ChatBubbleLeftEllipsisIcon className="h-5 w-5 text-gray-400" />
                          <h4 className="font-medium text-gray-900">Instructor Feedback</h4>
                        </div>
                        <div className="p-4 bg-blue-50 rounded-lg border border-blue-200">
                          <p className="text-gray-700 whitespace-pre-wrap">
                            {submission.feedback}
                          </p>
                        </div>
                      </div>
                    )}

                    {/* No content message */}
                    {!submission.submission_text && !submission.file_url && (
                      <div className="text-center py-8 text-gray-500">
                        <DocumentTextIcon className="h-12 w-12 mx-auto mb-2 text-gray-300" />
                        <p>No submission content available</p>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-12 text-gray-500">
                    <DocumentTextIcon className="h-12 w-12 mx-auto mb-2 text-gray-300" />
                    <p>No submission found</p>
                  </div>
                )}

                {/* Close Button */}
                <div className="mt-6 flex justify-end">
                  <button
                    type="button"
                    onClick={onClose}
                    className="w-full rounded-lg bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-200 sm:w-auto"
                  >
                    Close
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
};
