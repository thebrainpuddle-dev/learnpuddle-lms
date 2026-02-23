export type OpsPortal = 'SUPER_ADMIN' | 'TENANT_ADMIN' | 'TEACHER' | 'UNKNOWN';

export interface OpsClientContext {
  portal: OpsPortal;
  tabKey: string;
  routePath: string;
  componentName: string;
}

function getPortal(pathname: string): OpsPortal {
  if (pathname.startsWith('/super-admin')) return 'SUPER_ADMIN';
  if (pathname.startsWith('/admin')) return 'TENANT_ADMIN';
  if (pathname.startsWith('/teacher')) return 'TEACHER';
  return 'UNKNOWN';
}

function mapTenantAdminTab(pathname: string, tabParam: string): string {
  if (pathname.startsWith('/admin/dashboard')) return 'dashboard';
  if (
    pathname.startsWith('/admin/courses/new') ||
    (pathname.includes('/admin/courses/') && pathname.endsWith('/edit'))
  ) {
    if (tabParam === 'audience') return 'course_audience';
    if (tabParam === 'assignments') return 'assignment_builder';
    if (tabParam === 'content') return 'course_content';
    return 'course_editor';
  }
  if (pathname.startsWith('/admin/courses')) return 'courses';
  if (pathname.startsWith('/admin/media')) return 'media';
  if (pathname.startsWith('/admin/teachers')) return 'teachers';
  if (pathname.startsWith('/admin/groups')) return 'groups';
  if (pathname.startsWith('/admin/reminders')) return 'reminders';
  if (pathname.startsWith('/admin/announcements')) return 'announcements';
  if (pathname.startsWith('/admin/analytics')) return 'reports';
  if (pathname.startsWith('/admin/settings')) return 'settings';
  return 'admin';
}

function mapTeacherTab(pathname: string): string {
  if (pathname.startsWith('/teacher/dashboard')) return 'dashboard';
  if (pathname.startsWith('/teacher/courses/') && !pathname.endsWith('/courses')) return 'course_view';
  if (pathname.startsWith('/teacher/courses')) return 'courses';
  if (pathname.startsWith('/teacher/assignments')) return 'assignments';
  if (pathname.startsWith('/teacher/quizzes')) return 'quiz';
  if (pathname.startsWith('/teacher/reminders')) return 'reminders';
  if (pathname.startsWith('/teacher/profile')) return 'profile';
  return 'teacher';
}

function mapSuperAdminTab(pathname: string): string {
  if (pathname.startsWith('/super-admin/operations')) return 'operations';
  if (pathname.startsWith('/super-admin/dashboard')) return 'dashboard';
  if (pathname.startsWith('/super-admin/schools')) return 'schools';
  return 'super_admin';
}

export function getOpsClientContext(pathname: string, search: string): OpsClientContext {
  const safePath = pathname || '/';
  const params = new URLSearchParams(search || '');
  const tabParam = (params.get('tab') || '').toLowerCase();
  const portal = getPortal(safePath);

  let tabKey = 'unknown';
  if (portal === 'TENANT_ADMIN') {
    tabKey = mapTenantAdminTab(safePath, tabParam);
  } else if (portal === 'TEACHER') {
    tabKey = mapTeacherTab(safePath);
  } else if (portal === 'SUPER_ADMIN') {
    tabKey = mapSuperAdminTab(safePath);
  }

  return {
    portal,
    tabKey,
    routePath: safePath.slice(0, 255),
    componentName: `${portal}:${tabKey}`.slice(0, 128),
  };
}
