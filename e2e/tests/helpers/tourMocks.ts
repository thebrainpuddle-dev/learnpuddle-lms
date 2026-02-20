import type { Page, Route } from '@playwright/test';

type Role = 'SUPER_ADMIN' | 'SCHOOL_ADMIN' | 'TEACHER';

const now = () => new Date().toISOString();

function json(route: Route, data: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(data),
  });
}

function userForRole(role: Role) {
  if (role === 'SUPER_ADMIN') {
    return {
      id: 'user-super-admin',
      email: 'admin@learnpuddle.com',
      first_name: 'Platform',
      last_name: 'Admin',
      role: 'SUPER_ADMIN',
      is_active: true,
      email_verified: true,
      created_at: now(),
    };
  }

  if (role === 'SCHOOL_ADMIN') {
    return {
      id: 'user-school-admin',
      email: 'admin@demo.learnpuddle.com',
      first_name: 'School',
      last_name: 'Admin',
      role: 'SCHOOL_ADMIN',
      is_active: true,
      email_verified: true,
      created_at: now(),
    };
  }

  return {
    id: 'user-teacher',
    email: 'teacher@demo.learnpuddle.com',
    first_name: 'Demo',
    last_name: 'Teacher',
    role: 'TEACHER',
    designation: 'TGT (Trained Graduate Teacher)',
    subjects: ['Mathematics'],
    grades: ['Class 9'],
    is_active: true,
    email_verified: true,
    created_at: now(),
  };
}

const tenantListItem = {
  id: 'tenant-1',
  name: 'Demo International School',
  slug: 'demo-international-school',
  subdomain: 'demo',
  email: 'principal@demo.learnpuddle.com',
  is_active: true,
  is_trial: false,
  trial_end_date: null,
  plan: 'PRO',
  plan_started_at: now(),
  plan_expires_at: null,
  max_teachers: 150,
  max_courses: 300,
  max_storage_mb: 10240,
  primary_color: '#2563eb',
  logo: null,
  teacher_count: 42,
  admin_count: 3,
  course_count: 18,
  created_at: now(),
  updated_at: now(),
};

const tenantDetail = {
  ...tenantListItem,
  phone: '+1-555-0100',
  address: '100 Demo Street',
  secondary_color: '#0f766e',
  font_family: 'Inter',
  max_video_duration_minutes: 60,
  feature_video_upload: true,
  feature_auto_quiz: true,
  feature_transcripts: true,
  feature_reminders: true,
  feature_custom_branding: true,
  feature_reports_export: true,
  feature_groups: true,
  feature_certificates: true,
  internal_notes: 'Demo tenant notes.',
  published_course_count: 12,
  admin_email: 'principal@demo.learnpuddle.com',
  admin_name: 'Principal Demo',
};

const teacherCourses = [
  {
    id: 'course-1',
    title: 'Classroom Excellence',
    slug: 'classroom-excellence',
    description: 'Core course for classroom practices.',
    thumbnail: null,
    is_mandatory: true,
    deadline: null,
    estimated_hours: '4',
    is_published: true,
    is_active: true,
    created_at: now(),
    updated_at: now(),
    progress_percentage: 35,
    completed_content_count: 1,
    total_content_count: 3,
  },
];

const adminCourseList = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 'admin-course-1',
      title: 'Teacher Onboarding',
      slug: 'teacher-onboarding',
      description: 'Foundational onboarding course.',
      thumbnail: null,
      thumbnail_url: null,
      is_mandatory: true,
      deadline: null,
      estimated_hours: 6,
      assigned_to_all: true,
      is_published: true,
      is_active: true,
      module_count: 2,
      content_count: 6,
      assigned_teacher_count: 40,
      created_at: now(),
      updated_at: now(),
    },
  ],
};

const groupList = [
  {
    id: 'group-1',
    name: 'Mathematics Faculty',
    description: 'Math teachers',
    group_type: 'SUBJECT',
    created_at: now(),
    updated_at: now(),
  },
];

const teacherList = {
  count: 2,
  next: null,
  previous: null,
  results: [
    {
      id: 'teacher-1',
      email: 'teacher1@demo.learnpuddle.com',
      first_name: 'Anita',
      last_name: 'Sharma',
      role: 'TEACHER',
      department: 'Math',
      is_active: true,
      email_verified: true,
      created_at: now(),
    },
    {
      id: 'teacher-2',
      email: 'teacher2@demo.learnpuddle.com',
      first_name: 'Rahul',
      last_name: 'Verma',
      role: 'TEACHER',
      department: 'Science',
      is_active: true,
      email_verified: true,
      created_at: now(),
    },
  ],
};

const notifications = [
  {
    id: 'notif-1',
    notification_type: 'REMINDER',
    title: 'Assignment Reminder',
    message: 'Please review your pending assignment.',
    is_read: false,
    created_at: now(),
  },
];

function roleFromAuthHeader(authHeader: string | undefined): Role {
  const token = String(authHeader || '').toLowerCase();
  if (token.includes('super-admin')) return 'SUPER_ADMIN';
  if (token.includes('school-admin')) return 'SCHOOL_ADMIN';
  return 'TEACHER';
}

export async function setupTourApiMocks(page: Page) {
  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path.endsWith('/api/tenants/theme/')) {
      return json(route, {
        name: 'Demo International School',
        subdomain: 'demo',
        logo_url: null,
        primary_color: '#2563eb',
        secondary_color: '#0f766e',
        font_family: 'Inter',
        tenant_found: true,
      });
    }

    if (path.endsWith('/api/users/auth/login/')) {
      const body = request.postDataJSON() as { email?: string; portal?: string };
      if (body.portal === 'super_admin') {
        return json(route, {
          user: userForRole('SUPER_ADMIN'),
          tokens: { access: 'access-super-admin', refresh: 'refresh-super-admin' },
        });
      }
      if (body.email?.includes('admin@')) {
        return json(route, {
          user: userForRole('SCHOOL_ADMIN'),
          tokens: { access: 'access-school-admin', refresh: 'refresh-school-admin' },
        });
      }
      return json(route, {
        user: userForRole('TEACHER'),
        tokens: { access: 'access-teacher', refresh: 'refresh-teacher' },
      });
    }

    if (path.endsWith('/api/users/auth/me/')) {
      const role = roleFromAuthHeader(request.headers()['authorization']);
      return json(route, userForRole(role));
    }

    if (path.endsWith('/api/tenants/config/')) {
      return json(route, {
        plan: 'PRO',
        features: {
          video_upload: true,
          auto_quiz: true,
          transcripts: true,
          reminders: true,
          custom_branding: true,
          reports_export: true,
          groups: true,
          certificates: true,
        },
        limits: {
          max_teachers: 200,
          max_courses: 300,
          max_storage_mb: 20480,
          max_video_duration_minutes: 90,
        },
        usage: {
          teachers: { used: 42, limit: 200 },
          courses: { used: 18, limit: 300 },
          storage_mb: { used: 1200, limit: 20480 },
        },
      });
    }

    if (path.endsWith('/api/super-admin/stats/')) {
      return json(route, {
        total_tenants: 12,
        active_tenants: 10,
        trial_tenants: 2,
        total_users: 780,
        total_teachers: 640,
        plan_distribution: { FREE: 1, STARTER: 2, PRO: 7, ENTERPRISE: 2 },
        recent_onboards: [
          { id: 'tenant-1', name: 'Demo International School', subdomain: 'demo', created_at: now() },
        ],
        schools_near_limits: [
          { id: 'tenant-1', name: 'Demo International School', resource: 'Teachers', used: 42, limit: 50 },
        ],
      });
    }

    if (path.endsWith('/api/super-admin/tenants/') && method === 'GET') {
      return json(route, { count: 1, results: [tenantListItem] });
    }

    if (path.match(/\/api\/super-admin\/tenants\/[^/]+\/usage\/$/)) {
      return json(route, {
        teachers: { used: 42, limit: 50 },
        courses: { used: 18, limit: 100 },
        storage_mb: { used: 1200, limit: 4096 },
      });
    }

    if (path.match(/\/api\/super-admin\/tenants\/[^/]+\/$/)) {
      return json(route, tenantDetail);
    }

    if (path.endsWith('/api/tenants/stats/')) {
      return json(route, {
        total_teachers: 42,
        active_teachers: 40,
        inactive_teachers: 2,
        total_admins: 3,
        total_courses: 18,
        published_courses: 12,
        total_content_items: 120,
        avg_completion_pct: 58,
        course_completions: 91,
        courses_in_progress: 36,
        content_completions: 500,
        total_assignments: 45,
        total_submissions: 120,
        graded_submissions: 95,
        pending_review: 6,
        top_teachers: [{ name: 'Anita Sharma', completed_courses: 7 }],
        recent_activity: [
          {
            teacher_name: 'Rahul Verma',
            course_title: 'Teacher Onboarding',
            content_title: 'Module 1',
            completed_at: now(),
          },
        ],
      });
    }

    if (path.endsWith('/api/tenants/analytics/')) {
      return json(route, {
        course_breakdown: [
          { course_id: 'admin-course-1', title: 'Teacher Onboarding', assigned: 40, completed: 20, in_progress: 15, not_started: 5 },
        ],
        monthly_trend: [{ month: 'Jan', completions: 12 }, { month: 'Feb', completions: 15 }],
        assignment_breakdown: { total: 10, manual: 4, auto_quiz: 3, auto_reflection: 3 },
        teacher_engagement: { highly_active: 8, active: 20, low_activity: 10, inactive: 4 },
        department_stats: [{ department: 'Math', count: 12 }, { department: 'Science', count: 10 }],
      });
    }

    if (path.endsWith('/api/courses/') && method === 'GET') {
      return json(route, adminCourseList);
    }

    if (path.endsWith('/api/reports/courses/')) {
      return json(route, [{ id: 'admin-course-1', title: 'Teacher Onboarding', deadline: null }]);
    }

    if (path.endsWith('/api/reports/assignments/')) {
      return json(route, [{ id: 'assignment-1', title: 'Reflection 1', course_id: 'admin-course-1', due_date: null }]);
    }

    if (path.endsWith('/api/teachers/') && method === 'GET') {
      return json(route, teacherList);
    }

    if (path.endsWith('/api/teacher-groups/') && method === 'GET') {
      return json(route, { count: 1, results: groupList });
    }

    if (path.match(/\/api\/teacher-groups\/[^/]+\/members\/$/) && method === 'GET') {
      return json(route, { count: 1, results: teacherList.results.slice(0, 1) });
    }

    if (path.endsWith('/api/media/stats/')) {
      return json(route, { total: 1, VIDEO: 1, DOCUMENT: 0, LINK: 0 });
    }

    if (path.endsWith('/api/media/') && method === 'GET') {
      return json(route, {
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            id: 'media-1',
            title: 'Welcome Video',
            media_type: 'VIDEO',
            file_url: 'https://example.com/video.m3u8',
            file_name: 'welcome.mp4',
            file_size: 1200000,
            mime_type: 'video/mp4',
            duration: 240,
            thumbnail_url: '',
            tags: [],
            is_active: true,
            uploaded_by: null,
            uploaded_by_name: 'Admin',
            created_at: now(),
            updated_at: now(),
          },
        ],
      });
    }

    if (path.endsWith('/api/notifications/announcements/') && method === 'GET') {
      return json(route, { announcements: [] });
    }

    if (path.endsWith('/api/reminders/history/')) {
      return json(route, { results: [] });
    }

    if (path.endsWith('/api/tenants/settings/')) {
      return json(route, {
        id: 'tenant-1',
        name: 'Demo International School',
        subdomain: 'demo',
        logo: null,
        logo_url: null,
        primary_color: '#2563eb',
        secondary_color: '#0f766e',
        font_family: 'Inter',
        is_active: true,
        is_trial: false,
        trial_end_date: null,
      });
    }

    if (path.endsWith('/api/users/auth/2fa/status/')) {
      return json(route, {
        enabled: false,
        required: false,
        totp_configured: false,
        backup_codes_remaining: 0,
        can_disable: false,
      });
    }

    if (path.endsWith('/api/users/auth/sso/status/')) {
      return json(route, {
        has_password: true,
        linked_providers: [],
        can_unlink: false,
      });
    }

    if (path.endsWith('/api/users/auth/sso/providers/')) {
      return json(route, {
        providers: [],
        sso_enabled: false,
        sso_required: false,
      });
    }

    if (path.endsWith('/api/teacher/dashboard/')) {
      return json(route, {
        stats: {
          overall_progress: 35,
          total_courses: 1,
          completed_courses: 0,
          pending_assignments: 1,
        },
        continue_learning: {
          course_id: 'course-1',
          course_title: 'Classroom Excellence',
          content_id: 'content-1',
          content_title: 'Lesson 1',
          progress_percentage: 35,
        },
        deadlines: [{ type: 'assignment', id: 'assignment-1', title: 'Reflection 1', days_left: 3 }],
      });
    }

    if (path.endsWith('/api/teacher/courses/')) {
      return json(route, teacherCourses);
    }

    if (path.match(/\/api\/teacher\/courses\/[^/]+\/$/)) {
      return json(route, {
        ...teacherCourses[0],
        progress: {
          completed_content_count: 1,
          total_content_count: 3,
          percentage: 35,
        },
        modules: [
          {
            id: 'module-1',
            title: 'Module 1',
            description: 'Getting started',
            order: 1,
            is_active: true,
            contents: [
              {
                id: 'content-1',
                title: 'Lesson 1',
                content_type: 'TEXT',
                order: 1,
                file_url: null,
                is_mandatory: true,
                is_active: true,
                status: 'IN_PROGRESS',
                progress_percentage: 35,
                video_progress_seconds: 0,
                is_completed: false,
                text_content: 'Welcome lesson',
              },
            ],
          },
        ],
      });
    }

    if (path.endsWith('/api/teacher/assignments/')) {
      return json(route, [
        {
          id: 'assignment-1',
          course_id: 'course-1',
          course_title: 'Classroom Excellence',
          title: 'Reflection 1',
          description: 'Submit your reflection.',
          instructions: 'Write and submit',
          due_date: null,
          max_score: '10.00',
          passing_score: '6.00',
          is_mandatory: true,
          is_active: true,
          submission_status: 'PENDING',
          score: null,
          feedback: '',
          is_quiz: false,
        },
      ]);
    }

    if (path.endsWith('/api/notifications/')) {
      return json(route, notifications);
    }

    if (path.endsWith('/api/notifications/unread-count/')) {
      return json(route, { count: 1 });
    }

    if (path.match(/\/api\/notifications\/[^/]+\/read\/$/)) {
      return json(route, { ...notifications[0], is_read: true });
    }

    if (path.endsWith('/api/notifications/mark-all-read/')) {
      return json(route, { marked_read: 1 });
    }

    // Generic fallback for any API not explicitly mocked.
    return json(route, {});
  });
}

