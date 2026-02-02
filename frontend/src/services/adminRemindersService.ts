import api from '../config/api';

export interface ReminderPreviewResponse {
  recipient_count: number;
  recipients_preview: { id: string; name: string; email: string }[];
  resolved_subject: string;
  resolved_message: string;
}

export interface ReminderCampaign {
  id: string;
  reminder_type: string;
  course: string | null;
  assignment: string | null;
  subject: string;
  message: string;
  deadline_override: string | null;
  created_at: string;
  sent_count: number;
  failed_count: number;
}

export const adminRemindersService = {
  async preview(payload: any): Promise<ReminderPreviewResponse> {
    const res = await api.post('/reminders/preview/', payload);
    return res.data;
  },

  async send(payload: any): Promise<any> {
    const res = await api.post('/reminders/send/', payload);
    return res.data;
  },

  async history(): Promise<{ results: ReminderCampaign[] }> {
    const res = await api.get('/reminders/history/');
    return res.data;
  },
};

