// src/pages/admin/SkipRequestsPage.tsx

import React, { useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { adminService } from '../../services/adminService';
import type { SkipRequestItem } from '../../services/adminService';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  MagnifyingGlassIcon,
  XMarkIcon,
  CheckCircleIcon,
  XCircleIcon,
  DocumentArrowDownIcon,
  ClockIcon,
  FunnelIcon,
} from '@heroicons/react/24/outline';

const STATUS_TABS = [
  { key: 'ALL', label: 'All' },
  { key: 'PENDING', label: 'Pending' },
  { key: 'APPROVED', label: 'Approved' },
  { key: 'REJECTED', label: 'Rejected' },
] as const;

export const SkipRequestsPage: React.FC = () => {
  usePageTitle('Skip Requests');
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<string>('PENDING');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  // Review modal
  const [reviewItem, setReviewItem] = useState<SkipRequestItem | null>(null);
  const [reviewAction, setReviewAction] = useState<'approve' | 'reject' | null>(null);
  const [adminNotes, setAdminNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['skip-requests', activeTab, search, page],
    queryFn: () =>
      adminService.listSkipRequests({
        status: activeTab === 'ALL' ? undefined : activeTab,
        search: search || undefined,
        page,
      }),
  });

  const handleReview = async () => {
    if (!reviewItem || !reviewAction) return;
    setSubmitting(true);
    try {
      await adminService.reviewSkipRequest(reviewItem.id, {
        action: reviewAction,
        admin_notes: adminNotes.trim() || undefined,
      });
      setReviewItem(null);
      setReviewAction(null);
      setAdminNotes('');
      queryClient.invalidateQueries({ queryKey: ['skip-requests'] });
    } catch (err: any) {
      alert(err?.response?.data?.error || 'Failed to submit review.');
    } finally {
      setSubmitting(false);
    }
  };

  const openReview = (item: SkipRequestItem, action: 'approve' | 'reject') => {
    setReviewItem(item);
    setReviewAction(action);
    setAdminNotes('');
  };

  const statusBadge = (s: string) => {
    switch (s) {
      case 'PENDING':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-yellow-700 bg-yellow-50 border border-yellow-200 rounded-full">
            <ClockIcon className="h-3 w-3" /> Pending
          </span>
        );
      case 'APPROVED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-full">
            <CheckCircleIcon className="h-3 w-3" /> Approved
          </span>
        );
      case 'REJECTED':
        return (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded-full">
            <XCircleIcon className="h-3 w-3" /> Rejected
          </span>
        );
      default:
        return null;
    }
  };

  const pendingCount = data?.results?.filter((r) => r.status === 'PENDING').length ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Skip Requests</h1>
        <p className="text-sm text-gray-500 mt-1">
          Review teacher requests to skip mandatory courses.
        </p>
      </div>

      {/* Tabs + Search */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex gap-1 bg-gray-100 p-1 rounded-lg">
          {STATUS_TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => { setActiveTab(tab.key); setPage(1); }}
              className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
                activeTab === tab.key
                  ? 'bg-white text-gray-900 shadow-sm'
                  : 'text-gray-600 hover:text-gray-900'
              }`}
            >
              {tab.label}
              {tab.key === 'PENDING' && pendingCount > 0 && activeTab !== 'PENDING' && (
                <span className="ml-1.5 px-1.5 py-0.5 text-xs bg-yellow-100 text-yellow-700 rounded-full">
                  {pendingCount}
                </span>
              )}
            </button>
          ))}
        </div>

        <div className="relative">
          <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search by teacher name..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1); }}
            className="pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-sm w-64 focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" />
        </div>
      ) : !data?.results?.length ? (
        <div className="text-center py-20 bg-white rounded-xl border border-gray-200">
          <FunnelIcon className="h-12 w-12 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-500">No skip requests found.</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Teacher</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Course</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Certificate</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Comments</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                  <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {data.results.map((item) => (
                  <tr key={item.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="text-sm font-medium text-gray-900">{item.teacher_name}</div>
                      <div className="text-xs text-gray-500">{item.teacher_email}</div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700">{item.course_title}</td>
                    <td className="px-6 py-4 whitespace-nowrap">{statusBadge(item.status)}</td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      {item.certificate_url ? (
                        <a
                          href={item.certificate_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-sm text-primary-600 hover:underline"
                        >
                          <DocumentArrowDownIcon className="h-4 w-4" />
                          View
                        </a>
                      ) : (
                        <span className="text-xs text-gray-400">None</span>
                      )}
                    </td>
                    <td className="px-6 py-4 max-w-xs">
                      <p className="text-sm text-gray-600 truncate" title={item.comments}>
                        {item.comments || <span className="text-gray-400">-</span>}
                      </p>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(item.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right">
                      {item.status === 'PENDING' ? (
                        <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => openReview(item, 'approve')}
                            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-lg hover:bg-emerald-100"
                          >
                            <CheckCircleIcon className="h-3.5 w-3.5" />
                            Approve
                          </button>
                          <button
                            onClick={() => openReview(item, 'reject')}
                            className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-red-700 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100"
                          >
                            <XCircleIcon className="h-3.5 w-3.5" />
                            Reject
                          </button>
                        </div>
                      ) : (
                        <span className="text-xs text-gray-400">
                          {item.reviewed_by_name && `by ${item.reviewed_by_name}`}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {(data.next || data.previous) && (
            <div className="flex items-center justify-between px-6 py-3 border-t border-gray-200 bg-gray-50">
              <span className="text-sm text-gray-500">{data.count} total request{data.count !== 1 ? 's' : ''}</span>
              <div className="flex gap-2">
                <button
                  disabled={!data.previous}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  className="px-3 py-1 text-sm border border-gray-300 rounded-md hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                <button
                  disabled={!data.next}
                  onClick={() => setPage((p) => p + 1)}
                  className="px-3 py-1 text-sm border border-gray-300 rounded-md hover:bg-gray-100 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Review Modal */}
      {reviewItem && reviewAction && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setReviewItem(null)}>
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full mx-4 p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-gray-900">
                {reviewAction === 'approve' ? 'Approve' : 'Reject'} Skip Request
              </h3>
              <button onClick={() => setReviewItem(null)} className="p-1 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100">
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            <div className="space-y-3 mb-4 bg-gray-50 rounded-lg p-4 text-sm">
              <div><span className="font-medium text-gray-700">Teacher:</span> {reviewItem.teacher_name}</div>
              <div><span className="font-medium text-gray-700">Course:</span> {reviewItem.course_title}</div>
              {reviewItem.certificate_url && (
                <div>
                  <span className="font-medium text-gray-700">Certificate:</span>{' '}
                  <a href={reviewItem.certificate_url} target="_blank" rel="noopener noreferrer" className="text-primary-600 hover:underline">
                    View file
                  </a>
                </div>
              )}
              {reviewItem.comments && (
                <div>
                  <span className="font-medium text-gray-700">Comments:</span>
                  <p className="mt-1 text-gray-600">{reviewItem.comments}</p>
                </div>
              )}
            </div>

            {reviewAction === 'approve' && (
              <div className="mb-4 p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-sm text-emerald-700">
                Approving will automatically mark all course content as completed for this teacher.
              </div>
            )}

            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-1">Admin Notes (optional)</label>
              <textarea
                value={adminNotes}
                onChange={(e) => setAdminNotes(e.target.value)}
                rows={3}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
                placeholder="Add any notes for the teacher..."
              />
            </div>

            <div className="flex justify-end gap-3">
              <button
                onClick={() => setReviewItem(null)}
                className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                disabled={submitting}
                onClick={handleReview}
                className={`px-4 py-2 text-sm font-medium text-white rounded-lg disabled:opacity-50 ${
                  reviewAction === 'approve'
                    ? 'bg-emerald-600 hover:bg-emerald-700'
                    : 'bg-red-600 hover:bg-red-700'
                }`}
              >
                {submitting ? 'Submitting...' : reviewAction === 'approve' ? 'Approve' : 'Reject'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
