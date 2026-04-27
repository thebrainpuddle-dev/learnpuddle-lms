// src/services/versioningService.ts
//
// Typed API client for the TASK-048 content-versioning endpoints.
// All endpoints are under /api/v1/admin/ and require SCHOOL_ADMIN or SUPER_ADMIN.

import api from '../config/api';

// ---------------------------------------------------------------------------
// Kind discriminator — maps to URL prefix
// ---------------------------------------------------------------------------

export type VersioningKind = 'course' | 'module' | 'content';

// ---------------------------------------------------------------------------
// API response types
// ---------------------------------------------------------------------------

/**
 * Compact revision row returned by the list endpoint.
 * `snapshot_json` is absent — only the detail endpoint includes it.
 */
export interface ContentRevisionListItem {
  id: string;
  revision_number: number;
  target_type: string | null;
  object_id: string;
  change_summary: string;
  changed_by: string | null;
  changed_by_name: string | null;
  created_at: string; // ISO-8601
}

/**
 * Full revision record including the frozen snapshot.
 * `snapshot_json` shape varies by kind — typed as `unknown` and
 * narrowed via the type-guards below.
 */
export interface ContentRevisionDetail extends ContentRevisionListItem {
  snapshot_json: unknown;
}

/**
 * DRF paginated list response wrapper.
 */
export interface PaginatedRevisions {
  count: number;
  next: string | null;
  previous: string | null;
  results: ContentRevisionListItem[];
}

// ---------------------------------------------------------------------------
// Snapshot shapes (used by JsonDiffView — typed as unknown at the boundary,
// narrowed only when needed for display)
// ---------------------------------------------------------------------------

export interface ContentSnapshot {
  id: string;
  module_id: string | null;
  title: string;
  content_type: string;
  order: number;
  file_url: string;
  file_size: number | null;
  duration: number | null;
  text_content: string;
  maic_classroom_id: string | null;
  ai_chatbot_id: string | null;
  is_mandatory: boolean;
  is_active: boolean;
  is_deleted: boolean;
}

export interface ModuleSnapshot {
  id: string;
  course_id: string | null;
  title: string;
  description: string;
  order: number;
  is_active: boolean;
  is_deleted: boolean;
  contents?: ContentSnapshot[];
}

export interface CourseSnapshot {
  id: string;
  tenant_id: string | null;
  title: string;
  slug: string;
  description: string;
  thumbnail: string | null;
  is_mandatory: boolean;
  deadline: string | null;
  estimated_hours: string | null;
  assigned_to_all: boolean;
  assigned_to_all_students: boolean;
  course_type: string;
  subject_id: string | null;
  is_published: boolean;
  is_active: boolean;
  is_deleted: boolean;
  assigned_teachers: string[];
  assigned_students: string[];
  modules?: ModuleSnapshot[];
}

// ---------------------------------------------------------------------------
// Type guards for snapshot shapes
// ---------------------------------------------------------------------------

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

export function isCourseSnapshot(value: unknown): value is CourseSnapshot {
  return isRecord(value) && typeof (value as Record<string, unknown>).slug === 'string';
}

export function isModuleSnapshot(value: unknown): value is ModuleSnapshot {
  return (
    isRecord(value) &&
    'course_id' in value &&
    typeof (value as Record<string, unknown>).title === 'string' &&
    !('slug' in value)
  );
}

export function isContentSnapshot(value: unknown): value is ContentSnapshot {
  return (
    isRecord(value) &&
    typeof (value as Record<string, unknown>).content_type === 'string' &&
    'module_id' in value
  );
}

// ---------------------------------------------------------------------------
// URL builder
// ---------------------------------------------------------------------------

function buildBase(kind: VersioningKind, objectId: string): string {
  const plural = kind === 'content' ? 'contents' : `${kind}s`;
  return `/v1/admin/${plural}/${objectId}/revisions`;
}

// ---------------------------------------------------------------------------
// Service functions
// ---------------------------------------------------------------------------

/**
 * List revisions for a given object. `page` is 1-based.
 */
export async function listRevisions(
  kind: VersioningKind,
  objectId: string,
  page: number = 1,
): Promise<PaginatedRevisions> {
  const res = await api.get<PaginatedRevisions>(`${buildBase(kind, objectId)}/`, {
    params: { page },
  });
  return res.data;
}

/**
 * Fetch a single revision including its snapshot_json.
 */
export async function getRevision(
  kind: VersioningKind,
  objectId: string,
  revisionNumber: number,
): Promise<ContentRevisionDetail> {
  const res = await api.get<ContentRevisionDetail>(
    `${buildBase(kind, objectId)}/${revisionNumber}/`,
  );
  return res.data;
}

/**
 * Restore an object to the given revision number.
 * Returns the restored object serialized by the backend's existing detail serializer.
 */
export async function restoreRevision(
  kind: VersioningKind,
  objectId: string,
  revisionNumber: number,
): Promise<unknown> {
  const res = await api.post<unknown>(
    `${buildBase(kind, objectId)}/${revisionNumber}/restore/`,
  );
  return res.data;
}
