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
  source: 'MANUAL' | 'AUTOMATED';
  course: string | null;
  assignment: string | null;
  subject: string;
  message: string;
  deadline_override: string | null;
  automation_key: string;
  created_at: string;
  sent_count: number;
  failed_count: number;
}

export interface ReminderAutomationStatus {
  enabled: boolean;
  locked_manual_types: string[];
  lead_days: number[];
  upcoming_courses_count: number;
  last_run_at: string | null;
  next_run_note: string;
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

  async automationStatus(): Promise<ReminderAutomationStatus> {
    const res = await api.get('/reminders/automation-status/');
    return res.data;
  },
};
