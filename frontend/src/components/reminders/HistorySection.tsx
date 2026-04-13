import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  FunnelIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  XCircleIcon,
  CpuChipIcon,
  PaperAirplaneIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
} from '@heroicons/react/24/outline';
import { adminRemindersService, type ReminderCampaign } from '../../services/adminRemindersService';

// ─── Types ──────────────────────────────────────────────────────────────────

type FilterType = 'all' | 'MANUAL' | 'AUTOMATED';

// ─── Component ──────────────────────────────────────────────────────────────

const PAGE_SIZE = 10;

interface HistorySectionProps {
  refreshKey?: number;
}

export const HistorySection: React.FC<HistorySectionProps> = ({ refreshKey }) => {
  const [filterType, setFilterType] = useState<FilterType>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [currentPage, setCurrentPage] = useState(1);

  const historyQuery = useQuery({
    queryKey: ['remindersHistory', refreshKey],
    queryFn: adminRemindersService.history,
  });

  const campaigns = historyQuery.data?.results ?? [];

  // Filter and search
  const filtered = useMemo(() => {
    let items = campaigns;

    if (filterType !== 'all') {
      items = items.filter((c) => c.source === filterType);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      items = items.filter(
        (c) =>
          c.subject.toLowerCase().includes(q) ||
          c.reminder_type.toLowerCase().includes(q)
      );
    }

    return items;
  }, [campaigns, filterType, searchQuery]);

  // Pagination
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const goToPage = (page: number) => {
    setCurrentPage(Math.min(Math.max(1, page), totalPages));
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">History</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Log of all sent reminders, both automated and manual.
          </p>
        </div>
        <button
          onClick={() => historyQuery.refetch()}
          disabled={historyQuery.isFetching}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-600 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50"
        >
          <ArrowPathIcon
            className={`h-4 w-4 ${historyQuery.isFetching ? 'animate-spin' : ''}`}
          />
          Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex items-center gap-2">
          <FunnelIcon className="h-4 w-4 text-gray-400" />
          <div className="inline-flex rounded-lg border border-gray-200 bg-white p-0.5">
            {(['all', 'MANUAL', 'AUTOMATED'] as FilterType[]).map((type) => (
              <button
                key={type}
                onClick={() => {
                  setFilterType(type);
                  setCurrentPage(1);
                }}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                  filterType === type
                    ? 'bg-primary-50 text-primary-700'
                    : 'text-gray-600 hover:text-gray-900'
                }`}
              >
                {type === 'all' ? 'All' : type === 'MANUAL' ? 'Manual' : 'Automated'}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 max-w-xs">
          <input
            type="text"
            placeholder="Search by subject..."
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setCurrentPage(1);
            }}
            className="w-full px-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>
      </div>

      {/* Table */}
      <div className="border border-gray-200 rounded-xl bg-white overflow-hidden">
        {historyQuery.isLoading ? (
          <div className="px-4 py-12 text-center text-gray-500">
            <div className="animate-spin h-6 w-6 border-2 border-primary-600 border-t-transparent rounded-full mx-auto mb-2" />
            Loading history...
          </div>
        ) : filtered.length === 0 ? (
          <div className="px-4 py-12 text-center text-gray-500">
            <PaperAirplaneIcon className="h-8 w-8 mx-auto mb-2 text-gray-300" />
            <p className="font-medium">No reminders found</p>
            <p className="text-xs mt-1">
              {campaigns.length > 0
                ? 'Try adjusting your filters.'
                : 'Sent reminders will appear here.'}
            </p>
          </div>
        ) : (
          <>
            {/* Header */}
            <div className="hidden sm:grid grid-cols-12 gap-2 px-4 py-2.5 bg-gray-50 text-xs font-semibold text-gray-500 uppercase tracking-wider border-b border-gray-200">
              <div className="col-span-3">Date</div>
              <div className="col-span-1">Type</div>
              <div className="col-span-4">Subject</div>
              <div className="col-span-2">Delivery</div>
              <div className="col-span-2">Status</div>
            </div>

            {/* Rows */}
            {paginated.map((campaign) => (
              <HistoryRow key={campaign.id} campaign={campaign} />
            ))}
          </>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-1">
          <p className="text-xs text-gray-500">
            Showing {(currentPage - 1) * PAGE_SIZE + 1}–
            {Math.min(currentPage * PAGE_SIZE, filtered.length)} of {filtered.length}
          </p>
          <div className="flex items-center gap-1">
            <button
              onClick={() => goToPage(currentPage - 1)}
              disabled={currentPage === 1}
              className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronLeftIcon className="h-4 w-4" />
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .filter((p) => p === 1 || p === totalPages || Math.abs(p - currentPage) <= 1)
              .map((page, idx, arr) => (
                <React.Fragment key={page}>
                  {idx > 0 && arr[idx - 1] !== page - 1 && (
                    <span className="px-1 text-xs text-gray-400">...</span>
                  )}
                  <button
                    onClick={() => goToPage(page)}
                    className={`min-w-[28px] h-7 text-xs rounded-md ${
                      currentPage === page
                        ? 'bg-primary-50 text-primary-700 font-medium'
                        : 'text-gray-600 hover:bg-gray-100'
                    }`}
                  >
                    {page}
                  </button>
                </React.Fragment>
              ))}
            <button
              onClick={() => goToPage(currentPage + 1)}
              disabled={currentPage === totalPages}
              className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ChevronRightIcon className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

// ─── Row subcomponent ───────────────────────────────────────────────────────

function HistoryRow({ campaign }: { campaign: ReminderCampaign }) {
  const isAuto = campaign.source === 'AUTOMATED';
  const hasFailed = campaign.failed_count > 0;
  const allFailed = campaign.sent_count === 0 && campaign.failed_count > 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-12 gap-1 sm:gap-2 px-4 py-3 border-b border-gray-100 last:border-b-0 hover:bg-gray-50/50 transition-colors items-center">
      {/* Date */}
      <div className="col-span-3 text-xs text-gray-500">
        {new Date(campaign.created_at).toLocaleDateString(undefined, {
          month: 'short',
          day: 'numeric',
          year: 'numeric',
        })}{' '}
        <span className="text-gray-400">
          {new Date(campaign.created_at).toLocaleTimeString(undefined, {
            hour: '2-digit',
            minute: '2-digit',
          })}
        </span>
      </div>

      {/* Type badge */}
      <div className="col-span-1">
        {isAuto ? (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium bg-blue-50 text-blue-700 rounded">
            <CpuChipIcon className="h-3 w-3" />
            Auto
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium bg-gray-100 text-gray-700 rounded">
            <PaperAirplaneIcon className="h-3 w-3" />
            Manual
          </span>
        )}
      </div>

      {/* Subject */}
      <div className="col-span-4">
        <div className="text-sm font-medium text-gray-900 truncate">{campaign.subject}</div>
        <div className="text-[10px] text-gray-400 uppercase">{campaign.reminder_type}</div>
      </div>

      {/* Delivery counts */}
      <div className="col-span-2 text-xs text-gray-600">
        <span className="text-green-600 font-medium">{campaign.sent_count}</span> sent
        {hasFailed && (
          <>
            {' / '}
            <span className="text-red-600 font-medium">{campaign.failed_count}</span> failed
          </>
        )}
      </div>

      {/* Status */}
      <div className="col-span-2">
        {allFailed ? (
          <span className="inline-flex items-center gap-1 text-xs text-red-600">
            <XCircleIcon className="h-4 w-4" />
            Failed
          </span>
        ) : hasFailed ? (
          <span className="inline-flex items-center gap-1 text-xs text-amber-600">
            <CheckCircleIcon className="h-4 w-4" />
            Partial
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-xs text-green-600">
            <CheckCircleIcon className="h-4 w-4" />
            Sent
          </span>
        )}
      </div>
    </div>
  );
}
