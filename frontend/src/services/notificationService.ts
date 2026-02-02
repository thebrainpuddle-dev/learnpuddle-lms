import api from '../config/api';

export interface Notification {
  id: string;
  notification_type: 'REMINDER' | 'COURSE_ASSIGNED' | 'ASSIGNMENT_DUE' | 'ANNOUNCEMENT' | 'SYSTEM';
  title: string;
  message: string;
  course?: string;
  course_title?: string;
  assignment?: string;
  assignment_title?: string;
  is_read: boolean;
  read_at?: string;
  created_at: string;
}

export const notificationService = {
  /**
   * Get notifications for current teacher
   */
  getNotifications: async (params?: { unread_only?: boolean; limit?: number }): Promise<Notification[]> => {
    const queryParams = new URLSearchParams();
    if (params?.unread_only) queryParams.append('unread_only', 'true');
    if (params?.limit) queryParams.append('limit', params.limit.toString());
    
    const response = await api.get(`/notifications/?${queryParams.toString()}`);
    return response.data;
  },

  /**
   * Get unread notification count
   */
  getUnreadCount: async (): Promise<number> => {
    const response = await api.get('/notifications/unread-count/');
    return response.data.count;
  },

  /**
   * Mark a notification as read
   */
  markAsRead: async (notificationId: string): Promise<Notification> => {
    const response = await api.post(`/notifications/${notificationId}/read/`);
    return response.data;
  },

  /**
   * Mark all notifications as read
   */
  markAllAsRead: async (): Promise<{ marked_read: number }> => {
    const response = await api.post('/notifications/mark-all-read/');
    return response.data;
  },
};
