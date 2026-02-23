// src/pages/teacher/RemindersPage.tsx

import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '../../stores/authStore';
import { useTenantStore } from '../../stores/tenantStore';
import { notificationService, Notification } from '../../services/notificationService';
import { usePageTitle } from '../../hooks/usePageTitle';
import {
  BellAlertIcon,
  CheckIcon,
  ArrowPathIcon,
} from '@heroicons/react/24/outline';
import { formatDistanceToNow } from 'date-fns';

type Filter = 'ALL' | 'UNREAD' | 'READ';

const INVALIDATE_KEYS = [
  ['teacherRemindersPage'],
  ['unreadReminderCount'],
  ['notificationUnreadCount'],
  ['notifications'],
  ['dashboardNotifications'],
];

export const RemindersPage: React.FC = () => {
  usePageTitle('Reminders');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();
  const { theme } = useTenantStore();
  const [filter, setFilter] = useState<Filter>('ALL');
  const [refreshing, setRefreshing] = useState(false);

  const { data: reminders = [], isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['teacherRemindersPage'],
    queryFn: () => notificationService.getNotifications({ type: 'REMINDER', limit: 100 }),
  });

  const invalidateAll = () => {
    INVALIDATE_KEYS.forEach((key) => queryClient.invalidateQueries({ queryKey: key }));
  };

  const markReadMutation = useMutation({
    mutationFn: notificationService.markAsRead,
    onSuccess: invalidateAll,
  });

  const markAllReadMutation = useMutation({
    mutationFn: notificationService.markAllAsRead,
    onSuccess: invalidateAll,
  });

  const handleRefresh = async () => {
    setRefreshing(true);
    await refetch();
    // Also refresh the sidebar badge count
    queryClient.invalidateQueries({ queryKey: ['unreadReminderCount'] });
    queryClient.invalidateQueries({ queryKey: ['notificationUnreadCount'] });
    setRefreshing(false);
  };

  const handleClick = (r: Notification) => {
    if (!r.is_read) markReadMutation.mutate(r.id);
    if (r.course) navigate(`/teacher/courses/${r.course}`);
    else if (r.assignment) navigate('/teacher/assignments');
    else navigate('/teacher/courses');
  };

  const filtered = reminders.filter((r) => {
    if (filter === 'UNREAD') return !r.is_read;
    if (filter === 'READ') return r.is_read;
    return true;
  });

  const unreadCount = reminders.filter((r) => !r.is_read).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Reminders</h1>
          <p className="mt-1 text-sm text-gray-500">
            For {user?.first_name} {user?.last_name}{theme.name ? ` at ${theme.name}` : ''}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {dataUpdatedAt > 0 && (
            <span className="text-xs text-gray-400 hidden sm:inline">
              Updated {formatDistanceToNow(new Date(dataUpdatedAt), { addSuffix: true })}
            </span>
          )}
          {unreadCount > 0 && (
            <button
              type="button"
              onClick={() => markAllReadMutation.mutate()}
              disabled={markAllReadMutation.isPending}
              className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700 transition-colors hover:bg-emerald-100 disabled:opacity-50 sm:w-auto"
            >
              <CheckIcon className="h-4 w-4" />
              Mark all read
            </button>
          )}
          <button
            type="button"
            onClick={handleRefresh}
            disabled={refreshing || isLoading}
            className="inline-flex w-full items-center justify-center gap-1.5 rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 transition-colors hover:bg-gray-50 disabled:opacity-50 sm:w-auto"
          >
            <ArrowPathIcon className={`h-4 w-4 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Filter tabs */}
      <div
        data-tour="teacher-reminders-filters"
        className="flex w-full items-center gap-1 overflow-x-auto rounded-lg bg-gray-100 p-1 sm:w-fit"
      >
        {([
          { key: 'ALL' as Filter, label: 'All', count: reminders.length },
          { key: 'UNREAD' as Filter, label: 'Unread', count: unreadCount },
          { key: 'READ' as Filter, label: 'Read', count: reminders.length - unreadCount },
        ]).map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => setFilter(tab.key)}
            className={`whitespace-nowrap rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === tab.key
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
            {tab.count > 0 && (
              <span className={`ml-1.5 text-xs ${filter === tab.key ? 'text-gray-500' : 'text-gray-400'}`}>
                {tab.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Reminders list */}
      <div data-tour="teacher-reminders-list" className="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
        {isLoading ? (
          <div className="p-12 text-center text-gray-500 text-sm">Loading reminders...</div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center">
            <BellAlertIcon className="h-12 w-12 mx-auto text-gray-300 mb-3" />
            <p className="text-gray-500 font-medium">
              {filter === 'UNREAD' ? 'No unread reminders' : filter === 'READ' ? 'No read reminders' : 'No reminders yet'}
            </p>
            <p className="text-gray-400 text-sm mt-1">
              {filter === 'ALL' ? 'When your school admin sends reminders, they will appear here.' : 'Try a different filter.'}
            </p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {filtered.map((r) => (
              <div
                key={r.id}
                className={`flex flex-col gap-3 px-4 py-4 transition-colors hover:bg-gray-50 sm:flex-row sm:items-start sm:gap-4 sm:px-6 ${
                  !r.is_read ? 'bg-red-50/30' : ''
                }`}
              >
                <div className="flex-shrink-0 mt-0.5">
                  <div className={`p-2 rounded-lg ${!r.is_read ? 'bg-red-100' : 'bg-gray-100'}`}>
                    <BellAlertIcon className={`h-5 w-5 ${!r.is_read ? 'text-red-500' : 'text-gray-400'}`} />
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleClick(r)}
                  className="flex-1 min-w-0 text-left"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className={`text-sm ${!r.is_read ? 'font-semibold text-gray-900' : 'text-gray-700'}`}>
                      {r.title}
                    </p>
                    {!r.is_read && (
                      <span className="flex-shrink-0 w-2 h-2 rounded-full bg-red-500 mt-1.5" />
                    )}
                  </div>
                  <p className="text-sm text-gray-600 mt-1">{r.message}</p>
                  <p className="text-xs text-gray-400 mt-2">
                    {formatDistanceToNow(new Date(r.created_at), { addSuffix: true })}
                  </p>
                </button>
                <div className="flex-shrink-0 flex items-center gap-2 mt-1">
                  {!r.is_read && (
                    <button
                      type="button"
                      onClick={() => markReadMutation.mutate(r.id)}
                      disabled={markReadMutation.isPending}
                      className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-gray-500 hover:text-emerald-600 bg-gray-50 hover:bg-emerald-50 rounded transition-colors"
                      title="Mark as read"
                    >
                      <CheckIcon className="h-3.5 w-3.5" />
                      Read
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
