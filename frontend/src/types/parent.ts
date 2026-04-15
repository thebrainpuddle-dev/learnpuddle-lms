export interface ParentChild {
  id: string;
  first_name: string;
  last_name: string;
  grade_level?: string;
  section?: string;
  email?: string;
  student_id?: string;
  enrollment_date?: string | null;
}

export interface ParentCourseProgress {
  id: string;
  title: string;
  course_type: string;
  is_mandatory: boolean;
  deadline: string | null;
  total_contents: number;
  completed_contents: number;
  progress_percentage: number;
  status: string;
  last_accessed: string | null;
}

export interface ParentAssignment {
  id: string;
  title: string;
  course_title: string;
  due_date: string | null;
  max_score: number;
  is_mandatory: boolean;
  submission_status: string;
  score: number | null;
}

export interface ParentAttendance {
  total_days: number;
  present_days: number;
  absent_days: number;
  attendance_percentage: number;
  note?: string;
}

export interface ParentStudyTime {
  total_video_seconds: number;
  total_video_minutes: number;
  courses_in_progress: number;
  courses_completed: number;
}

export interface ParentRecentActivity {
  course_title: string;
  content_title: string | null;
  status: string;
  last_accessed: string | null;
  completed_at?: string;
}

export interface ParentChildOverview {
  student: ParentChild;
  courses: ParentCourseProgress[];
  assignments: ParentAssignment[];
  attendance: ParentAttendance;
  study_time: ParentStudyTime;
  recent_activity: ParentRecentActivity[];
}

export interface ParentAuthResponse {
  session_token: string;
  refresh_token: string;
  expires_at: string;
  parent_email?: string;
  children: ParentChild[];
}
