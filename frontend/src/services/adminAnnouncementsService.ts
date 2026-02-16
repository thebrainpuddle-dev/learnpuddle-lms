// src/services/adminAnnouncementsService.ts

import api from '../config/api';

export interface Announcement {
  id: string;
  title: string;
  message: string;
  recipient_count: number;
  created_at: string;
}

export interface CreateAnnouncementPayload {
  title: string;
  message: string;
  target: 'all' | 'groups';
  group_ids?: string[];
}

export interface CreateAnnouncementResponse {
  message: string;
  title: string;
  recipient_count: number;
}

export const adminAnnouncementsService = {
  /**
   * List all announcements for the tenant.
   */
  async listAnnouncements(): Promise<Announcement[]> {
    const res = await api.get('/notifications/announcements/');
    return res.data.announcements ?? [];
  },

  /**
   * Create a new announcement.
   */
  async createAnnouncement(payload: CreateAnnouncementPayload): Promise<CreateAnnouncementResponse> {
    const res = await api.post('/notifications/announcements/', payload);
    return res.data;
  },

  /**
   * Delete an announcement.
   */
  async deleteAnnouncement(announcementId: string): Promise<{ message: string }> {
    const res = await api.delete(`/notifications/announcements/${announcementId}/`);
    return res.data;
  },
};
