// course-editor/types.ts — Shared types for the Course Editor feature

import type { MediaAsset } from '../../../services/adminMediaService';
import type {
  AdminAssignment,
  AdminAssignmentPayload,
  AdminQuizQuestion,
} from '../../../services/adminService';

// ── Domain models ──────────────────────────────────────────────────────

export interface Teacher {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
}

export interface TeacherGroup {
  id: string;
  name: string;
  description: string;
  group_type: string;
  member_count?: number;
}

export interface Content {
  id: string;
  title: string;
  content_type: 'VIDEO' | 'DOCUMENT' | 'TEXT' | 'LINK' | 'AI_CLASSROOM' | 'CHATBOT';
  order: number;
  file_url: string | null;
  text_content: string;
  is_mandatory: boolean;
  duration: number | null;
  file_size: number | null;
  video_status?: 'UPLOADED' | 'PROCESSING' | 'READY' | 'FAILED' | null;
  maic_classroom_id?: string | null;
  ai_chatbot_id?: string | null;
}

export interface Module {
  id: string;
  title: string;
  description: string;
  order: number;
  contents: Content[];
}

export interface Course {
  id: string;
  title: string;
  slug: string;
  description: string;
  thumbnail: string | null;
  thumbnail_url: string | null;
  is_mandatory: boolean;
  deadline: string | null;
  estimated_hours: number;
  assigned_to_all: boolean;
  assigned_groups: string[];
  assigned_teachers: string[];
  target_sections: string[];
  is_published: boolean;
  modules: Module[];
}

// ── Editor-specific types ──────────────────────────────────────────────

export type EditorTab = 'details' | 'content' | 'ai' | 'audience';
export type TextEditorMode = 'WYSIWYG' | 'MARKDOWN';
export type LibraryMediaFilter = 'ALL' | MediaAsset['media_type'];
export type AssignmentScopeFilter = 'ALL' | 'COURSE' | 'MODULE';

export interface CourseFormData {
  title: string;
  description: string;
  is_mandatory: boolean;
  deadline: string;
  estimated_hours: number;
  assigned_to_all: boolean;
  assigned_groups: string[];
  assigned_teachers: string[];
  target_sections: string[];
}

export interface NewContentData {
  title: string;
  content_type: Content['content_type'];
  text_content: string;
  file_url: string;
  is_mandatory: boolean;
}

export interface CreateGroupForm {
  name: string;
  description: string;
  group_type: string;
}

export interface ConfirmDeleteTarget {
  type: 'module' | 'content';
  moduleId: string;
  contentId?: string;
  label: string;
}

export type UploadPhase = 'idle' | 'uploading' | 'processing' | 'done';

// ── Re-exports for convenience ─────────────────────────────────────────

export type { AdminAssignment, AdminAssignmentPayload, AdminQuizQuestion, MediaAsset };
