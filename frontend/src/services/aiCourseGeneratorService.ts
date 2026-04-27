// src/services/aiCourseGeneratorService.ts
// AI Course Generator service — calls TASK-060 backend endpoints.

import api from '../config/api';

// ─── Type definitions ────────────────────────────────────────────────────────

export type SourceType = 'pdf' | 'docx' | 'text' | 'youtube' | 'vimeo';
export type JobStatus =
  | 'pending'
  | 'extracting'
  | 'llm_outlining'
  | 'materialising'
  | 'succeeded'
  | 'failed';

export interface OutlineContent {
  type: 'text' | 'quiz' | 'assignment';
  title: string;
  description: string;
}

export interface OutlineModule {
  title: string;
  contents: OutlineContent[];
}

export interface Outline {
  title: string;
  description: string;
  modules: OutlineModule[];
}

export interface Job {
  id: string;
  source_type: SourceType;
  source_metadata: Record<string, unknown>;
  extracted_char_count: number | null;
  status: JobStatus;
  error: string | null;
  outline_json: Outline | null;
  provider: string | null;
  model: string | null;
  tokens_prompt: number | null;
  tokens_completion: number | null;
  draft_course_id: string | null;
  created_by_email: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobListItem {
  id: string;
  source_type: SourceType;
  status: JobStatus;
  error: string | null;
  provider: string | null;
  model: string | null;
  draft_course_id: string | null;
  created_by_email: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface CreateJobResponse {
  job_id: string;
  status: JobStatus;
}

export interface MaterialiseResponse {
  draft_course_id: string;
  idempotent: boolean;
}

export interface ListJobsParams {
  status?: JobStatus | '';
  created_by?: string;
}

// ─── Constants ────────────────────────────────────────────────────────────────

const BASE = '/v1/admin/course-generator';

export const TERMINAL_STATES: JobStatus[] = ['succeeded', 'failed'];

export const YOUTUBE_HOSTS = new Set([
  'youtube.com',
  'www.youtube.com',
  'youtu.be',
]);
export const VIMEO_HOSTS = new Set(['vimeo.com']);
export const ALLOWED_URL_HOSTS = new Set([...YOUTUBE_HOSTS, ...VIMEO_HOSTS]);

export const MAX_FILE_BYTES = 20 * 1024 * 1024; // 20 MB

// ─── Client-side validation helpers ──────────────────────────────────────────

export function validateUrlHost(url: string): string | null {
  try {
    const { hostname } = new URL(url);
    const host = hostname.toLowerCase();
    if (!ALLOWED_URL_HOSTS.has(host)) {
      return 'Only YouTube and Vimeo URLs are supported.';
    }
    return null;
  } catch {
    return 'Please enter a valid URL.';
  }
}

export function validateOutline(outline: Outline): Record<string, string> {
  const errors: Record<string, string> = {};

  if (!outline.title.trim()) {
    errors['title'] = 'Course title is required.';
  } else if (outline.title.length > 120) {
    errors['title'] = 'Course title must be 120 characters or fewer.';
  }

  if (outline.description.length > 500) {
    errors['description'] = 'Course description must be 500 characters or fewer.';
  }

  if (outline.modules.length < 3) {
    errors['modules'] = 'At least 3 modules are required.';
  } else if (outline.modules.length > 12) {
    errors['modules'] = 'No more than 12 modules are allowed.';
  }

  outline.modules.forEach((mod, mIdx) => {
    if (!mod.title.trim()) {
      errors[`module_${mIdx}_title`] = 'Module title is required.';
    } else if (mod.title.length > 120) {
      errors[`module_${mIdx}_title`] = 'Module title must be 120 characters or fewer.';
    }

    if (mod.contents.length < 2) {
      errors[`module_${mIdx}_contents`] = 'Each module must have at least 2 contents.';
    } else if (mod.contents.length > 6) {
      errors[`module_${mIdx}_contents`] = 'Each module may have at most 6 contents.';
    }

    mod.contents.forEach((c, cIdx) => {
      if (!c.title.trim()) {
        errors[`module_${mIdx}_content_${cIdx}_title`] = 'Content title is required.';
      } else if (c.title.length > 200) {
        errors[`module_${mIdx}_content_${cIdx}_title`] =
          'Content title must be 200 characters or fewer.';
      }
      if (c.description.length > 300) {
        errors[`module_${mIdx}_content_${cIdx}_description`] =
          'Content description must be 300 characters or fewer.';
      }
    });
  });

  return errors;
}

// ─── API service ──────────────────────────────────────────────────────────────

export const aiCourseGeneratorService = {
  /**
   * POST /api/v1/admin/course-generator/
   * Enqueue a new generation job. Payload is multipart/form-data.
   */
  async createJob(payload: FormData): Promise<CreateJobResponse> {
    const res = await api.post(`${BASE}/`, payload);
    return res.data;
  },

  /**
   * GET /api/v1/admin/course-generator/jobs/{id}/
   * Poll job status + outline.
   */
  async getJob(jobId: string): Promise<Job> {
    const res = await api.get(`${BASE}/jobs/${jobId}/`);
    return res.data;
  },

  /**
   * GET /api/v1/admin/course-generator/jobs/
   * List all jobs for the current tenant.
   */
  async listJobs(params?: ListJobsParams): Promise<JobListItem[]> {
    const res = await api.get(`${BASE}/jobs/`, { params });
    return res.data;
  },

  /**
   * POST /api/v1/admin/course-generator/jobs/{id}/materialise/
   * Create draft course from the (possibly edited) outline. Idempotent.
   */
  async materialiseJob(
    jobId: string,
    outlineOverride?: Outline
  ): Promise<MaterialiseResponse> {
    const body: Record<string, unknown> = {};
    if (outlineOverride) {
      body.outline_override = outlineOverride;
    }
    const res = await api.post(`${BASE}/jobs/${jobId}/materialise/`, body);
    return res.data;
  },

  /**
   * DELETE /api/v1/admin/course-generator/jobs/{id}/delete/
   * Note: the URLconf uses .../delete/ suffix (not REST-idiomatic .../  DELETE).
   */
  async deleteJob(jobId: string): Promise<void> {
    await api.delete(`${BASE}/jobs/${jobId}/delete/`);
  },
};
