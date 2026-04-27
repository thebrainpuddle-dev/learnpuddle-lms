// src/services/translationService.ts
// Translation service — calls TASK-058 and TASK-064b backend endpoints.
// Backend base: /api/v1/admin/translations/

import api from '../config/api';

// ─── Types ────────────────────────────────────────────────────────────────────

export type TranslationJobStatus = 'pending' | 'running' | 'success' | 'failed';

export type TranslationFieldKey = 'title' | 'description' | 'body' | 'transcript';

export type FieldReviewStatus = 'pending' | 'approved' | 'rejected';

export interface TranslationJob {
  id: string;
  kind: 'course' | 'content';
  target_id: string;
  target_languages: string[];
  status: TranslationJobStatus;
  started_at: string | null;
  finished_at: string | null;
  fields_translated: number;
  error: string;
  created_at: string;
}

export interface CreateCourseJobResponse {
  job_id: string;
  status: TranslationJobStatus;
  target_languages: string[];
}

export interface ContentTranslationRow {
  id: string;
  source_type: string;
  source_id: string;
  field: TranslationFieldKey;
  target_language: string;
  translated_text: string;
  provider: string;
  model: string;
  source_hash: string;
  translated_at: string;
  updated_at: string;
}

/**
 * Shape returned by ContentTranslationReviewSerializer (TASK-064b).
 * All approve / reject / edit / publish endpoints return this shape.
 */
export interface ContentTranslationReview {
  id: string;
  source_type: string;
  source_id: string;
  field: TranslationFieldKey;
  target_language: string;
  translated_text: string;
  edited_text: string | null;
  review_status: FieldReviewStatus;
  reviewed_by: string | null; // user PK
  reviewed_by_email: string | null;
  reviewed_at: string | null;
  published_at: string | null;
  translated_at: string;
  updated_at: string;
}

export interface ContentTranslationsResponse {
  content_id: string;
  lang: string;
  rows: ContentTranslationRow[];
}

export interface PublishTranslationResponse {
  published_at: string;
  rows_published: number;
  skipped: Record<string, string>;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const BASE = '/v1/admin/translations';

export const TERMINAL_STATES: TranslationJobStatus[] = ['success', 'failed'];

/** Hardcoded supported locales — backend has no /locales/ endpoint. */
export const SUPPORTED_LOCALES: { code: string; label: string }[] = [
  { code: 'es', label: 'Spanish' },
  { code: 'fr', label: 'French' },
  { code: 'de', label: 'German' },
  { code: 'zh', label: 'Chinese (Simplified)' },
  { code: 'ja', label: 'Japanese' },
  { code: 'ar', label: 'Arabic' },
  { code: 'pt', label: 'Portuguese' },
  { code: 'hi', label: 'Hindi' },
];

// ─── Service ──────────────────────────────────────────────────────────────────

export const translationService = {
  /**
   * POST /api/v1/admin/translations/courses/{courseId}/
   * Enqueue a course-level translation job.
   */
  async createCourseJob(
    courseId: string,
    targetLanguages: string[]
  ): Promise<CreateCourseJobResponse> {
    const res = await api.post(`${BASE}/courses/${courseId}/`, {
      target_languages: targetLanguages,
    });
    return res.data;
  },

  /**
   * GET /api/v1/admin/translations/jobs/{jobId}/
   * Poll translation job status.
   */
  async getJob(jobId: string): Promise<TranslationJob> {
    const res = await api.get(`${BASE}/jobs/${jobId}/`);
    return res.data;
  },

  /**
   * GET /api/v1/admin/translations/content/{contentId}/?lang={lang}
   * Retrieve stored translations for a content item.
   */
  async getContentTranslations(
    contentId: string,
    lang: string
  ): Promise<ContentTranslationsResponse> {
    const res = await api.get(`${BASE}/content/${contentId}/`, {
      params: { lang },
    });
    return res.data;
  },

  // ─── TASK-064b review endpoints ─────────────────────────────────────────────

  /**
   * PUT /api/v1/admin/translations/content/{contentId}/fields/{field}/approve/?lang=xx
   * Approve a specific translated field.
   */
  async approveField(
    contentId: string,
    field: TranslationFieldKey,
    lang: string
  ): Promise<ContentTranslationReview> {
    const res = await api.put(
      `${BASE}/content/${contentId}/fields/${field}/approve/`,
      {},
      { params: { lang } }
    );
    return res.data;
  },

  /**
   * PUT /api/v1/admin/translations/content/{contentId}/fields/{field}/reject/?lang=xx
   * Reject a specific translated field.
   */
  async rejectField(
    contentId: string,
    field: TranslationFieldKey,
    lang: string
  ): Promise<ContentTranslationReview> {
    const res = await api.put(
      `${BASE}/content/${contentId}/fields/${field}/reject/`,
      {},
      { params: { lang } }
    );
    return res.data;
  },

  /**
   * PUT /api/v1/admin/translations/content/{contentId}/fields/{field}/edit/?lang=xx
   * Submit an admin-edited correction for a translated field.
   * Sets review_status to 'approved' on success.
   */
  async editField(
    contentId: string,
    field: TranslationFieldKey,
    lang: string,
    editedText: string
  ): Promise<ContentTranslationReview> {
    const res = await api.put(
      `${BASE}/content/${contentId}/fields/${field}/edit/`,
      { edited_text: editedText },
      { params: { lang } }
    );
    return res.data;
  },

  /**
   * POST /api/v1/admin/translations/content/{contentId}/publish/?lang=xx
   * Publish all approved translations for a content item + language.
   */
  async publishTranslation(
    contentId: string,
    lang: string
  ): Promise<PublishTranslationResponse> {
    const res = await api.post(
      `${BASE}/content/${contentId}/publish/`,
      {},
      { params: { lang } }
    );
    return res.data;
  },
};
