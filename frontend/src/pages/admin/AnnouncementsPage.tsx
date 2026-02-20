// src/pages/admin/AnnouncementsPage.tsx

import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Button } from '../../components/common/Button';
import { Input } from '../../components/common/Input';
import { useToast } from '../../components/common';
import { adminAnnouncementsService } from '../../services/adminAnnouncementsService';
import { adminGroupsService } from '../../services/adminGroupsService';
import {
  MegaphoneIcon,
  TrashIcon,
  UserGroupIcon,
  UsersIcon,
  PaperAirplaneIcon,
} from '@heroicons/react/24/outline';
import { usePageTitle } from '../../hooks/usePageTitle';

export const AnnouncementsPage: React.FC = () => {
  usePageTitle('Announcements');
  const toast = useToast();
  const queryClient = useQueryClient();

  // Form state
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [target, setTarget] = useState<'all' | 'groups'>('all');
  const [selectedGroupIds, setSelectedGroupIds] = useState<string[]>([]);

  // Fetch announcements
  const { data: announcements, isLoading: loadingAnnouncements } = useQuery({
    queryKey: ['adminAnnouncements'],
    queryFn: adminAnnouncementsService.listAnnouncements,
  });

  // Fetch groups for targeting
  const { data: groups } = useQuery({
    queryKey: ['adminGroups'],
    queryFn: adminGroupsService.listGroups,
  });

  // Create announcement mutation
  const createMutation = useMutation({
    mutationFn: () =>
      adminAnnouncementsService.createAnnouncement({
        title,
        message,
        target,
        group_ids: target === 'groups' ? selectedGroupIds : undefined,
      }),
    onSuccess: (data) => {
      toast.success('Announcement sent!', `Sent to ${data.recipient_count} teachers.`);
      queryClient.invalidateQueries({ queryKey: ['adminAnnouncements'] });
      // Reset form
      setTitle('');
      setMessage('');
      setTarget('all');
      setSelectedGroupIds([]);
    },
    onError: (error: any) => {
      const errorMessage = error.response?.data?.error || 'Failed to send announcement';
      toast.error('Error', errorMessage);
    },
  });

  // Delete announcement mutation
  const deleteMutation = useMutation({
    mutationFn: (announcementId: string) =>
      adminAnnouncementsService.deleteAnnouncement(announcementId),
    onSuccess: () => {
      toast.success('Deleted', 'Announcement has been removed.');
      queryClient.invalidateQueries({ queryKey: ['adminAnnouncements'] });
    },
    onError: () => {
      toast.error('Error', 'Failed to delete announcement.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !message.trim()) {
      toast.error('Validation Error', 'Title and message are required.');
      return;
    }
    if (target === 'groups' && selectedGroupIds.length === 0) {
      toast.error('Validation Error', 'Please select at least one group.');
      return;
    }
    createMutation.mutate();
  };

  const toggleGroup = (groupId: string) => {
    setSelectedGroupIds((prev) =>
      prev.includes(groupId)
        ? prev.filter((id) => id !== groupId)
        : [...prev, groupId]
    );
  };

  const formatDate = (dateString: string) => {
    return new Date(dateString).toLocaleString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Announcements</h1>
        <p className="mt-1 text-gray-500">
          Send announcements to all teachers or specific groups
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Create Announcement Form */}
        <div data-tour="admin-announcements-compose" className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <div className="flex items-center gap-2 mb-6">
            <MegaphoneIcon className="h-6 w-6 text-emerald-600" />
            <h2 className="text-lg font-semibold text-gray-900">New Announcement</h2>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              label="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Enter announcement title"
              required
              maxLength={255}
            />

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Message
              </label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Enter your announcement message..."
                required
                rows={5}
                className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 resize-none"
              />
            </div>

            {/* Target Selection */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Send To
              </label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="target"
                    value="all"
                    checked={target === 'all'}
                    onChange={() => setTarget('all')}
                    className="text-emerald-600 focus:ring-emerald-500"
                  />
                  <UsersIcon className="h-5 w-5 text-gray-400" />
                  <span className="text-sm text-gray-700">All Teachers</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="target"
                    value="groups"
                    checked={target === 'groups'}
                    onChange={() => setTarget('groups')}
                    className="text-emerald-600 focus:ring-emerald-500"
                  />
                  <UserGroupIcon className="h-5 w-5 text-gray-400" />
                  <span className="text-sm text-gray-700">Specific Groups</span>
                </label>
              </div>
            </div>

            {/* Group Selection */}
            {target === 'groups' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Select Groups
                </label>
                <div className="border border-gray-200 rounded-lg p-3 max-h-48 overflow-y-auto space-y-2">
                  {groups && groups.length > 0 ? (
                    groups.map((group) => (
                      <label
                        key={group.id}
                        className="flex items-center gap-2 cursor-pointer hover:bg-gray-50 p-2 rounded"
                      >
                        <input
                          type="checkbox"
                          checked={selectedGroupIds.includes(group.id)}
                          onChange={() => toggleGroup(group.id)}
                          className="text-emerald-600 focus:ring-emerald-500 rounded"
                        />
                        <span className="text-sm text-gray-700">{group.name}</span>
                        {group.description && (
                          <span className="text-xs text-gray-400">
                            - {group.description}
                          </span>
                        )}
                      </label>
                    ))
                  ) : (
                    <p className="text-sm text-gray-500">No groups available</p>
                  )}
                </div>
              </div>
            )}

            <Button
              type="submit"
              variant="primary"
              loading={createMutation.isPending}
              className="w-full"
            >
              <PaperAirplaneIcon className="h-5 w-5 mr-2" />
              Send Announcement
            </Button>
          </form>
        </div>

        {/* Announcement History */}
        <div data-tour="admin-announcements-history" className="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Recent Announcements</h2>

          {loadingAnnouncements ? (
            <div className="space-y-4">
              {[1, 2, 3].map((i) => (
                <div key={i} className="animate-pulse border-b border-gray-100 pb-4">
                  <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
                  <div className="h-3 bg-gray-200 rounded w-full mb-2" />
                  <div className="h-3 bg-gray-200 rounded w-1/2" />
                </div>
              ))}
            </div>
          ) : announcements && announcements.length > 0 ? (
            <div className="space-y-4 max-h-[500px] overflow-y-auto">
              {announcements.map((announcement) => (
                <div
                  key={announcement.id}
                  className="border border-gray-100 rounded-lg p-4 hover:border-gray-200 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-gray-900 truncate">
                        {announcement.title}
                      </h3>
                      <p className="text-sm text-gray-500 mt-1 line-clamp-2">
                        {announcement.message}
                      </p>
                      <div className="flex items-center gap-4 mt-2 text-xs text-gray-400">
                        <span>{formatDate(announcement.created_at)}</span>
                        <span className="flex items-center gap-1">
                          <UsersIcon className="h-3 w-3" />
                          {announcement.recipient_count} recipients
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() => deleteMutation.mutate(announcement.id)}
                      disabled={deleteMutation.isPending}
                      className="p-2 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors"
                      title="Delete announcement"
                    >
                      <TrashIcon className="h-5 w-5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12">
              <MegaphoneIcon className="h-12 w-12 mx-auto text-gray-300 mb-2" />
              <p className="text-gray-500">No announcements yet</p>
              <p className="text-sm text-gray-400">
                Create your first announcement to notify teachers
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
