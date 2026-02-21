// src/types/index.ts

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: 'SUPER_ADMIN' | 'SCHOOL_ADMIN' | 'TEACHER' | 'HOD' | 'IB_COORDINATOR';
  employee_id?: string;
  subjects?: string[];
  grades?: string[];
  department?: string;
  designation?: string;
  bio?: string;
  profile_picture?: string;
  profile_picture_url?: string;
  notification_preferences?: Record<string, boolean>;
  is_active: boolean;
  email_verified: boolean;
  created_at: string;
}

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  subdomain: string;
  logo?: string;
  primary_color: string;
  secondary_color?: string;
  font_family?: string;
  is_active: boolean;
  is_trial?: boolean;
  plan?: string;
  // Feature flags
  feature_video_upload?: boolean;
  feature_auto_quiz?: boolean;
  feature_transcripts?: boolean;
  feature_reminders?: boolean;
  feature_custom_branding?: boolean;
  feature_reports_export?: boolean;
  feature_groups?: boolean;
  feature_certificates?: boolean;
  feature_teacher_authoring?: boolean;
  // Limits
  max_teachers?: number;
  max_courses?: number;
  max_storage_mb?: number;
}

export interface Course {
  id: string;
  title: string;
  slug: string;
  description: string;
  thumbnail?: string;
  thumbnail_url?: string;
  is_mandatory: boolean;
  deadline?: string;
  estimated_hours: number;
  is_published: boolean;
  is_active: boolean;
  module_count?: number;
  content_count?: number;
  assigned_teacher_count?: number;
  completion_rate?: number;
  created_by_name?: string;
  created_at: string;
  updated_at: string;
}

export interface Module {
  id: string;
  title: string;
  description: string;
  order: number;
  is_active: boolean;
  content_count?: number;
  contents?: ContentWithProgress[];
}

export interface Content {
  id: string;
  title: string;
  content_type: 'VIDEO' | 'DOCUMENT' | 'LINK' | 'TEXT';
  order: number;
  file_url?: string;
  file_size?: number;
  duration?: number;
  text_content?: string;
  is_mandatory: boolean;
  video_status?: string;
}

/**
 * Content as returned by the teacher course detail endpoint,
 * enriched with progress and video metadata.
 */
export interface ContentWithProgress extends Content {
  status?: string;
  progress_percentage?: number;
  video_progress_seconds?: number;
  is_completed?: boolean;
  hls_url?: string;
  thumbnail_url?: string;
  has_transcript?: boolean;
  transcript_vtt_url?: string;
}

export interface Assignment {
  id: string;
  title: string;
  description: string;
  instructions?: string;
  assignment_type: string;
  course_id?: string;
  course_title?: string;
  module_title?: string;
  deadline?: string;
  max_score?: number;
  passing_score?: number;
  is_mandatory?: boolean;
  submission_status?: string;
  score?: number | null;
  feedback?: string;
  is_quiz?: boolean;
  created_at?: string;
}

export interface TeacherProgress {
  id: string;
  course: string;
  content?: string;
  status: 'NOT_STARTED' | 'IN_PROGRESS' | 'COMPLETED';
  progress_percentage: number;
  started_at?: string;
  completed_at?: string;
  last_accessed: string;
}

export interface AuthTokens {
  access: string;
  refresh: string;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface ApiResponse<T> {
  data: T;
  message?: string;
  error?: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

/**
 * Search results returned by the teacher global search endpoint.
 */
export interface SearchResults {
  courses: Array<{ id: string; title: string; type: 'course' }>;
  assignments: Array<{ id: string; title: string; course_id: string; type: 'assignment' }>;
}

/**
 * Superadmin tenant onboard details.
 */
export interface TenantDetail extends Tenant {
  email?: string;
  teacher_count?: number;
  course_count?: number;
  created_at?: string;
  trial_expires_at?: string;
}
