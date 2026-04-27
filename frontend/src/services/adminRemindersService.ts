import api from '../config/api';

export interface ReminderPreviewResponse {
  recipient_count: number;
  recipients_preview: { id: string; name: string; email: string }[];
  resolved_subject: string;
  resolved_message: string;
}

/** All reminder type keys accepted by the backend. */
export type ReminderType = 'COURSE_DEADLINE' | 'ASSIGNMENT_DUE' | 'CUSTOM';

/** Shared fields present in every reminder payload variant. */
interface ReminderPayloadBase {
  /**
   * Target teacher IDs. Omit (or pass undefined) to target all eligible
   * teachers — the backend interprets a missing field as "send to everyone".
   */
  teacher_ids?: string[];
  /** Override subject line (optional — falls back to rule template). */
  subject?: string;
  /** Override message body (optional — falls back to rule template). */
  message?: string;
  /** ISO-8601 datetime; reserved for scheduled send (backend support pending). */
  scheduled_at?: string;
}

/** Payload for ASSIGNMENT_DUE reminders — `assignment_id` is required. */
export interface AssignmentDuePayload extends ReminderPayloadBase {
  reminder_type: 'ASSIGNMENT_DUE';
  /** Assignment UUID — required when reminder_type is "ASSIGNMENT_DUE". */
  assignment_id: string;
}

/** Payload for non-assignment reminder types. */
export interface NonAssignmentPayload extends ReminderPayloadBase {
  reminder_type: Exclude<ReminderType, 'ASSIGNMENT_DUE'>;
  assignment_id?: never;
}

/**
 * Discriminated union payload accepted by both /reminders/preview/ and
 * /reminders/send/. TypeScript enforces that `assignment_id` is present
 * (and a string) whenever `reminder_type === 'ASSIGNMENT_DUE'`, and absent
 * (or `never`) for all other types — preventing silent typo errors at call sites.
 */
export type ReminderPayload = AssignmentDuePayload | NonAssignmentPayload;

/** Response returned by /reminders/send/. */
export interface ReminderSendResponse {
  sent: number;
  failed: number;
}

export interface ReminderCampaign {
  id: string;
  reminder_type: ReminderType;
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
  async preview(payload: ReminderPayload): Promise<ReminderPreviewResponse> {
    const res = await api.post('/reminders/preview/', payload);
    return res.data;
  },

  async send(payload: ReminderPayload): Promise<ReminderSendResponse> {
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
