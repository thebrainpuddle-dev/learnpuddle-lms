import React, { Fragment, useState, useRef, useEffect, useCallback } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Transition } from '@headlessui/react';
import {
  LayoutDashboard,
  BookOpen,
  Users,
  BarChart3,
  Settings,
  Trophy,
  Award,
  Bell,
  CreditCard,
  Megaphone,
  Grid3X3,
  LogOut,
  Search,
  Menu,
  X,
  ClipboardList,
  ChevronDown,
  GraduationCap,
  Contact,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '../theme/cn';
import { useAuthStore } from '../../stores/authStore';
import { useTenantStore, type TenantFeatures } from '../../stores/tenantStore';
import { authService } from '../../services/authService';
import { broadcastLogout } from '../../utils/authSession';
import { CommandPalette } from '../../components/shared/CommandPalette';

// ─── Nav types ───────────────────────────────────────────────────────────────

interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  feature?: keyof TenantFeatures;
}

interface NavGroup {
  label: string;
  icon: LucideIcon;
  items: NavItem[];
}

type NavEntry = NavItem | NavGroup;

function isGroup(entry: NavEntry): entry is NavGroup {
  return 'items' in entry;
}

// ─── Role-based navigation ───────────────────────────────────────────────────

const ADMIN_NAV: NavEntry[] = [
  { label: 'Dashboard', href: '/admin/dashboard', icon: LayoutDashboard },
  { label: 'Courses', href: '/admin/courses', icon: BookOpen },
  {
    label: 'People',
    icon: Users,
    items: [
      { label: 'Teachers', href: '/admin/teachers', icon: Users },
      { label: 'Students', href: '/admin/students', icon: GraduationCap },
      { label: 'Groups', href: '/admin/groups', icon: Grid3X3, feature: 'groups' },
      { label: 'Directory', href: '/admin/directory', icon: Contact },
    ],
  },
  {
    label: 'Insights',
    icon: BarChart3,
    items: [
      { label: 'Certifications', href: '/admin/certifications', icon: Award },
      { label: 'Analytics', href: '/admin/analytics', icon: BarChart3 },
    ],
  },
  {
    label: 'More',
    icon: Settings,
    items: [
      { label: 'Reminders', href: '/admin/reminders', icon: Bell },
      { label: 'Billing', href: '/admin/billing', icon: CreditCard },
      { label: 'Settings', href: '/admin/settings', icon: Settings },
    ],
  },
];

const TEACHER_NAV: NavEntry[] = [
  { label: 'Dashboard', href: '/teacher/dashboard', icon: LayoutDashboard },
  { label: 'My Courses', href: '/teacher/courses', icon: BookOpen },
  { label: 'Assignments', href: '/teacher/assignments', icon: ClipboardList },
  { label: 'Achievements', href: '/teacher/gamification', icon: Trophy },
];

const SUPER_ADMIN_NAV: NavEntry[] = [
  { label: 'Dashboard', href: '/super-admin/dashboard', icon: LayoutDashboard },
  { label: 'Organizations', href: '/super-admin/schools', icon: Grid3X3 },
  { label: 'Operations', href: '/super-admin/operations', icon: Settings },
  { label: 'Demo Bookings', href: '/super-admin/demo-bookings', icon: Megaphone },
];

function getNavForRole(role?: string): NavEntry[] {
  if (role === 'SUPER_ADMIN') return SUPER_ADMIN_NAV;
  if (role === 'SCHOOL_ADMIN' || role === 'ADMIN') return ADMIN_NAV;
  return TEACHER_NAV;
}

// ─── Dropdown component ─────────────────────────────────────────────────────

function NavDropdown({ group, hasFeature }: { group: NavGroup; hasFeature: (f: keyof TenantFeatures) => boolean }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const location = useLocation();
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const visibleItems = group.items.filter(item => !item.feature || hasFeature(item.feature));
  if (visibleItems.length === 0) return null;

  const isAnyActive = visibleItems.some(
    item => location.pathname === item.href || location.pathname.startsWith(item.href + '/')
  );

  const handleMouseEnter = () => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    setOpen(true);
  };

  const handleMouseLeave = () => {
    timeoutRef.current = setTimeout(() => setOpen(false), 150);
  };

  useEffect(() => {
    return () => { if (timeoutRef.current) clearTimeout(timeoutRef.current); };
  }, []);

  return (
    <div
      ref={ref}
      className="relative"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <button
        onClick={() => setOpen(!open)}
        className={cn(
          'topnav-link',
          isAnyActive && 'topnav-link-active',
        )}
      >
        <span>{group.label}</span>
        <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')} />
      </button>

      <Transition
        show={open}
        as={Fragment}
        enter="transition ease-out duration-150"
        enterFrom="opacity-0 translate-y-1"
        enterTo="opacity-100 translate-y-0"
        leave="transition ease-in duration-100"
        leaveFrom="opacity-100 translate-y-0"
        leaveTo="opacity-0 translate-y-1"
      >
        <div className="absolute top-full left-0 mt-1 w-52 bg-white rounded-xl shadow-dropdown border border-surface-border p-1.5 z-50">
          {visibleItems.map((item) => {
            const isActive = location.pathname === item.href ||
              location.pathname.startsWith(item.href + '/');
            return (
              <NavLink
                key={item.href}
                to={item.href}
                onClick={() => setOpen(false)}
                className={cn(
                  'flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors',
                  isActive
                    ? 'bg-accent-50 text-accent-dark font-medium'
                    : 'text-content-secondary hover:text-content hover:bg-surface-card-hover',
                )}
              >
                <item.icon className="h-4 w-4 flex-shrink-0" />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </div>
      </Transition>
    </div>
  );
}

// ─── Mobile Menu ────────────────────────────────────────────────────────────

function MobileMenu({
  open,
  onClose,
  entries,
  hasFeature,
  onLogout,
}: {
  open: boolean;
  onClose: () => void;
  entries: NavEntry[];
  hasFeature: (f: keyof TenantFeatures) => boolean;
  onLogout: () => void;
}) {
  const location = useLocation();

  return (
    <Transition show={open} as={Fragment}>
      <div className="fixed inset-0 z-50 lg:hidden">
        <Transition.Child
          as={Fragment}
          enter="transition-opacity duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="transition-opacity duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/30 backdrop-blur-sm" onClick={onClose} />
        </Transition.Child>

        <Transition.Child
          as={Fragment}
          enter="transition-transform duration-300"
          enterFrom="-translate-x-full"
          enterTo="translate-x-0"
          leave="transition-transform duration-200"
          leaveFrom="translate-x-0"
          leaveTo="-translate-x-full"
        >
          <div className="fixed inset-y-0 left-0 w-[300px] bg-white shadow-xl overflow-y-auto">
            <div className="flex items-center justify-between px-5 py-4 border-b border-surface-border">
              <span className="text-lg font-bold text-content">Menu</span>
              <button onClick={onClose} className="p-1.5 rounded-lg hover:bg-surface-card-hover">
                <X className="h-5 w-5 text-content-muted" />
              </button>
            </div>

            <nav className="p-3 space-y-1">
              {entries.map((entry) => {
                if (isGroup(entry)) {
                  const visibleItems = entry.items.filter(item => !item.feature || hasFeature(item.feature));
                  if (visibleItems.length === 0) return null;
                  return (
                    <div key={entry.label}>
                      <p className="px-3 pt-4 pb-1 text-[10px] uppercase tracking-wider font-semibold text-content-muted">
                        {entry.label}
                      </p>
                      {visibleItems.map((item) => {
                        const isActive = location.pathname === item.href;
                        return (
                          <NavLink
                            key={item.href}
                            to={item.href}
                            onClick={onClose}
                            className={cn(
                              'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors',
                              isActive
                                ? 'bg-accent-50 text-accent-dark font-medium'
                                : 'text-content-secondary hover:text-content hover:bg-surface-card-hover',
                            )}
                          >
                            <item.icon className="h-4.5 w-4.5 flex-shrink-0" />
                            <span>{item.label}</span>
                          </NavLink>
                        );
                      })}
                    </div>
                  );
                }

                const isActive = location.pathname === entry.href;
                return (
                  <NavLink
                    key={entry.href}
                    to={entry.href}
                    onClick={onClose}
                    className={cn(
                      'flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm transition-colors',
                      isActive
                        ? 'bg-accent-50 text-accent-dark font-medium'
                        : 'text-content-secondary hover:text-content hover:bg-surface-card-hover',
                    )}
                  >
                    <entry.icon className="h-4.5 w-4.5 flex-shrink-0" />
                    <span>{entry.label}</span>
                  </NavLink>
                );
              })}
            </nav>

            <div className="p-3 mt-4 border-t border-surface-border">
              <button
                onClick={onLogout}
                className="flex items-center gap-3 w-full px-3 py-2.5 rounded-xl text-sm text-danger hover:bg-danger-bg transition-colors"
              >
                <LogOut className="h-4.5 w-4.5" />
                <span>Logout</span>
              </button>
            </div>
          </div>
        </Transition.Child>
      </div>
    </Transition>
  );
}

// ─── Main TopNav Export ──────────────────────────────────────────────────────

export function TopNav() {
  const { user, clearAuth, refreshToken } = useAuthStore();
  const { theme, hasFeature } = useTenantStore();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const entries = getNavForRole(user?.role);

  const tenantName = theme?.name || 'LearnPuddle';
  const tenantInitial = tenantName.charAt(0).toUpperCase();

  // Global Cmd+K / Ctrl+K keyboard shortcut
  const handleGlobalKeyDown = useCallback((e: KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      setCommandPaletteOpen((prev) => !prev);
    }
  }, []);

  useEffect(() => {
    document.addEventListener('keydown', handleGlobalKeyDown);
    return () => document.removeEventListener('keydown', handleGlobalKeyDown);
  }, [handleGlobalKeyDown]);

  const handleLogout = async () => {
    try {
      if (refreshToken) await authService.logout(refreshToken);
    } catch {
      // proceed regardless
    } finally {
      broadcastLogout('manual_logout', undefined, user?.email);
      clearAuth();
      window.location.href = '/login';
    }
  };

  return (
    <>
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-surface-border shadow-nav">
        <div className="max-w-[1440px] mx-auto px-4 lg:px-6">
          <div className="flex items-center h-16 gap-6">
            {/* ─── Logo ─────────────────────────────────────────── */}
            <div className="flex items-center gap-2.5 flex-shrink-0">
              {theme?.logo ? (
                <img
                  src={theme.logo}
                  alt={tenantName}
                  className="h-9 w-9 rounded-full object-cover"
                />
              ) : (
                <div className="h-9 w-9 rounded-full bg-gradient-to-br from-accent to-accent-dark flex items-center justify-center">
                  <span className="text-white font-bold text-sm">{tenantInitial}</span>
                </div>
              )}
              <span className="hidden sm:block text-base font-bold text-content">
                {tenantName}
              </span>
            </div>

            {/* ─── Desktop Nav ──────────────────────────────────── */}
            <nav className="hidden lg:flex items-center gap-1 flex-1">
              {entries.map((entry) => {
                if (isGroup(entry)) {
                  return (
                    <NavDropdown
                      key={entry.label}
                      group={entry}
                      hasFeature={hasFeature}
                    />
                  );
                }

                const dashboards = ['/admin/dashboard', '/teacher/dashboard', '/super-admin/dashboard'];
                const isActive = dashboards.includes(entry.href)
                  ? location.pathname === entry.href
                  : location.pathname === entry.href || location.pathname.startsWith(entry.href + '/');

                return (
                  <NavLink
                    key={entry.href}
                    to={entry.href}
                    className={cn(
                      'topnav-link',
                      isActive && 'topnav-link-active',
                    )}
                  >
                    <span>{entry.label}</span>
                  </NavLink>
                );
              })}
            </nav>

            {/* ─── Right Side ──────────────────────────────────── */}
            <div className="flex items-center gap-2 ml-auto">
              {/* Search — opens Command Palette */}
              <button
                onClick={() => setCommandPaletteOpen(true)}
                className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface text-content-muted text-sm border border-surface-border hover:bg-surface-card-hover transition-colors"
              >
                <Search className="h-4 w-4" />
                <span className="hidden lg:inline text-xs">Search...</span>
                <kbd className="hidden lg:inline-flex h-5 items-center gap-0.5 rounded border border-surface-border bg-white px-1.5 text-[10px] font-medium text-content-muted">
                  <span className="text-xs">⌘</span>K
                </kbd>
              </button>

              {/* Notifications */}
              <button className="relative p-2 rounded-lg text-content-muted hover:bg-surface-card-hover hover:text-content transition-colors">
                <Bell className="h-5 w-5" />
              </button>

              {/* User Avatar + Name */}
              <div className="hidden sm:flex items-center gap-2 pl-2 ml-1 border-l border-surface-border">
                <div className="h-8 w-8 rounded-full bg-gradient-to-br from-accent to-accent-dark flex items-center justify-center flex-shrink-0">
                  <span className="text-white text-xs font-semibold">
                    {user?.first_name?.charAt(0)}{user?.last_name?.charAt(0)}
                  </span>
                </div>
                <div className="hidden md:block min-w-0">
                  <p className="text-sm font-medium text-content truncate leading-tight">
                    {user?.first_name} {user?.last_name}
                  </p>
                  <p className="text-[10px] text-content-muted truncate leading-tight">
                    {user?.role === 'SCHOOL_ADMIN' ? 'Admin' : user?.role === 'SUPER_ADMIN' ? 'Platform Admin' : 'Teacher'}
                  </p>
                </div>
              </div>

              {/* Logout (desktop) */}
              <button
                onClick={handleLogout}
                title="Logout"
                className="hidden lg:flex p-2 rounded-lg text-content-muted hover:text-danger hover:bg-danger-bg transition-colors"
              >
                <LogOut className="h-4.5 w-4.5" />
              </button>

              {/* Mobile menu button */}
              <button
                onClick={() => setMobileOpen(true)}
                className="lg:hidden p-2 rounded-lg text-content-muted hover:bg-surface-card-hover transition-colors"
              >
                <Menu className="h-5 w-5" />
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Mobile menu drawer */}
      <MobileMenu
        open={mobileOpen}
        onClose={() => setMobileOpen(false)}
        entries={entries}
        hasFeature={hasFeature}
        onLogout={handleLogout}
      />

      {/* Command Palette (Cmd+K) */}
      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
      />
    </>
  );
}
