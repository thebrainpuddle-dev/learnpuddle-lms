// src/services/courseTemplatesService.ts
//
// API service for Course Templates (TASK-049 / TASK-051).
//
// Two namespaces:
//   courseTemplatesService.tenant   — list (published only), preview, clone
//   courseTemplatesService.superAdmin — full CRUD

import api from '../config/api';

// ─── Shared types ────────────────────────────────────────────────────────────

export type TemplateCategory =
  | 'TEACHING_SKILLS'
  | 'IB_PYP'
  | 'IB_MYP'
  | 'IB_DP'
  | 'LEADERSHIP'
  | 'WELLBEING'
  | 'OTHER';

export type TemplateLevel = 'BEGINNER' | 'INTERMEDIATE' | 'ADVANCED';

/** The lightweight shape returned by the list endpoints. */
export interface CourseTemplateListItem {
  id: string;
  slug: string;
  title: string;
  description: string;
  category: TemplateCategory;
  language: string;
  estimated_hours: number;
  level: TemplateLevel;
  thumbnail_url: string;
  is_published: boolean;
  created_at: string;
  updated_at: string;
}

/** A single content item in the blueprint. */
export interface BlueprintContent {
  title: string;
  content_type: string;
  order: number;
  text_content: string;
  file_url: string;
  duration: number | null;
  is_mandatory: boolean;
  meta_json: Record<string, unknown>;
}

/** A single module in the blueprint. */
export interface BlueprintModule {
  title: string;
  description: string;
  order: number;
  contents: BlueprintContent[];
}

/** The blueprint_json schema stored on the template. */
export interface BlueprintJson {
  schema_version?: number;
  course?: {
    title: string;
    description: string;
    estimated_hours: number;
    is_mandatory: boolean;
  };
  modules: BlueprintModule[];
}

/** Full detail — adds blueprint_json + created_by. */
export interface CourseTemplateDetail extends CourseTemplateListItem {
  blueprint_json: BlueprintJson;
  created_by: string | null;
}

/** Payload for tenant clone endpoint. */
export interface CloneTemplatePayload {
  title_override?: string;
  module_prefix?: string;
}

/** Minimal Course shape returned after cloning (CourseDetailSerializer). */
export interface ClonedCourse {
  id: string;
  title: string;
  slug: string;
  [key: string]: unknown;
}

/** Paginated list response from DRF PageNumberPagination. */
export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/** Filters for tenant list endpoint (server-side). */
export interface TenantTemplateFilters {
  category?: TemplateCategory;
  language?: string;
  level?: TemplateLevel;
  page?: number;
}

/** Payload for super-admin create/update. */
export interface TemplateWritePayload {
  slug?: string;
  title?: string;
  description?: string;
  category?: TemplateCategory;
  language?: string;
  estimated_hours?: number;
  level?: TemplateLevel;
  thumbnail_url?: string;
  blueprint_json?: BlueprintJson;
  is_published?: boolean;
}

// ─── Service ─────────────────────────────────────────────────────────────────

export const courseTemplatesService = {
  /**
   * Tenant-facing namespace.
   * All endpoints sit under /v1/admin/course-templates/.
   * Only published templates are returned.
   */
  tenant: {
    /** List published templates with optional server-side filters. */
    listTemplates: async (
      filters: TenantTemplateFilters = {},
    ): Promise<PaginatedResponse<CourseTemplateListItem>> => {
      const params: Record<string, string | number> = {};
      if (filters.category) params.category = filters.category;
      if (filters.language) params.language = filters.language;
      if (filters.level) params.level = filters.level;
      if (filters.page) params.page = filters.page;
      const res = await api.get<PaginatedResponse<CourseTemplateListItem>>(
        '/v1/admin/course-templates/',
        { params },
      );
      return res.data;
    },

    /** Fetch full detail (including blueprint_json) for one published template. */
    previewTemplate: async (id: string): Promise<CourseTemplateDetail> => {
      const res = await api.get<CourseTemplateDetail>(
        `/v1/admin/course-templates/${id}/`,
      );
      return res.data;
    },

    /** Clone a published template into the current tenant. Returns the new Course. */
    cloneTemplate: async (
      id: string,
      body: CloneTemplatePayload = {},
    ): Promise<ClonedCourse> => {
      const res = await api.post<ClonedCourse>(
        `/v1/admin/course-templates/${id}/clone/`,
        body,
      );
      return res.data;
    },
  },

  /**
   * Super-admin namespace.
   * All endpoints sit under /v1/super-admin/course-templates/.
   */
  superAdmin: {
    /** List all templates (published and draft). */
    listAllTemplates: async (
      params: Record<string, string | number | boolean> = {},
    ): Promise<PaginatedResponse<CourseTemplateListItem>> => {
      const res = await api.get<PaginatedResponse<CourseTemplateListItem>>(
        '/v1/super-admin/course-templates/',
        { params },
      );
      return res.data;
    },

    /** Create a new template. */
    createTemplate: async (
      payload: TemplateWritePayload,
    ): Promise<CourseTemplateDetail> => {
      const res = await api.post<CourseTemplateDetail>(
        '/v1/super-admin/course-templates/',
        payload,
      );
      return res.data;
    },

    /** Get full detail for a template. */
    getTemplate: async (id: string): Promise<CourseTemplateDetail> => {
      const res = await api.get<CourseTemplateDetail>(
        `/v1/super-admin/course-templates/${id}/`,
      );
      return res.data;
    },

    /** Partially update a template. */
    updateTemplate: async (
      id: string,
      patch: TemplateWritePayload,
    ): Promise<CourseTemplateDetail> => {
      const res = await api.patch<CourseTemplateDetail>(
        `/v1/super-admin/course-templates/${id}/`,
        patch,
      );
      return res.data;
    },

    /**
     * Delete a template.
     * Without ?hard=true → soft-delete (unpublish).
     * With ?hard=true   → permanent deletion.
     */
    deleteTemplate: async (
      id: string,
      hard = false,
    ): Promise<CourseTemplateDetail | null> => {
      const res = await api.delete<CourseTemplateDetail | ''>(
        `/v1/super-admin/course-templates/${id}/`,
        { params: hard ? { hard: 'true' } : {} },
      );
      // Hard delete returns 204 with no body; soft delete returns the updated record.
      return res.data || null;
    },
  },
};
