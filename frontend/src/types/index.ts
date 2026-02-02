// src/types/index.ts

export interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
  role: 'SCHOOL_ADMIN' | 'TEACHER' | 'HOD' | 'IB_COORDINATOR';
  employee_id?: string;
  subjects?: string[];
  grades?: string[];
  department?: string;
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
  is_active: boolean;
}

export interface Course {
  id: string;
  title: string;
  slug: string;
  description: string;
  thumbnail?: string;
  is_mandatory: boolean;
  deadline?: string;
  estimated_hours: number;
  is_published: boolean;
  is_active: boolean;
  module_count?: number;
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
