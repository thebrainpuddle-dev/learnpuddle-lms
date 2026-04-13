import React, { Fragment, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { Dialog, Transition } from '@headlessui/react';
import {
  LayoutDashboard,
  BookOpen,
  Users,
  BarChart3,
  Settings,
  Trophy,
  Award,
  MessageSquare,
  Bell,
  CreditCard,
  Grid3X3,
  ChevronLeft,
  ChevronRight,
  LogOut,
  X,
  ClipboardList,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '../theme/cn';
import { useAuthStore } from '../../stores/authStore';
import { useTenantStore, type TenantFeatures } from '../../stores/tenantStore';
import { authService } from '../../services/authService';
import { broadcastLogout } from '../../utils/authSession';

// ─── Navigation Config ──────────────────────────────────────────────────────

export interface NavItem {
  label: string;
  href: string;
  icon: LucideIcon;
  feature?: keyof TenantFeatures;
  badge?: number;
}

export interface NavSection {
  title?: string;
  items: NavItem[];
}

const ADMIN_NAV: NavSection[] = [
  {
    items: [
      { label: 'Dashboard', href: '/admin/dashboard', icon: LayoutDashboard },
    ],
  },
  {
    title: 'Content',
    items: [
      { label: 'Courses', href: '/admin/courses', icon: BookOpen },
    ],
  },
  {
    title: 'People',
    items: [
      { label: 'Teachers', href: '/admin/teachers', icon: Users },
      { label: 'Groups', href: '/admin/groups', icon: Grid3X3, feature: 'groups' },
    ],
  },
  {
    title: 'Insights',
    items: [
      { label: 'Certifications', href: '/admin/certifications', icon: Award },
      { label: 'Analytics', href: '/admin/analytics', icon: BarChart3 },
    ],
  },
  {
    title: 'Engagement',
    items: [
      { label: 'Reminders', href: '/admin/reminders', icon: Bell },
    ],
  },
  {
    items: [
      { label: 'Billing', href: '/admin/billing', icon: CreditCard },
      { label: 'Settings', href: '/admin/settings', icon: Settings },
    ],
  },
];

const TEACHER_NAV: NavSection[] = [
  {
    items: [
      { label: 'Dashboard', href: '/teacher/dashboard', icon: LayoutDashboard },
      { label: 'My Courses', href: '/teacher/courses', icon: BookOpen },
      { label: 'Assignments', href: '/teacher/assignments', icon: ClipboardList },
    ],
  },
  {
    title: 'Growth',
    items: [
      { label: 'Achievements', href: '/teacher/gamification', icon: Trophy },
    ],
  },
];

const SUPER_ADMIN_NAV: NavSection[] = [
  {
    items: [
      { label: 'Dashboard', href: '/super-admin/dashboard', icon: LayoutDashboard },
      { label: 'Organizations', href: '/super-admin/schools', icon: Grid3X3 },
      { label: 'Operations', href: '/super-admin/operations', icon: Settings },
      { label: 'Demo Bookings', href: '/super-admin/demo-bookings', icon: MessageSquare },
    ],
  },
];

function getNavForRole(role?: string): NavSection[] {
  if (role === 'SUPER_ADMIN') return SUPER_ADMIN_NAV;
  if (role === 'SCHOOL_ADMIN' || role === 'ADMIN') return ADMIN_NAV;
  return TEACHER_NAV;
}

// ─── Sidebar Content ────────────────────────────────────────────────────────

interface SidebarContentProps {
  collapsed: boolean;
  onCollapse: (val: boolean) => void;
  onNavClick?: () => void;
}

function SidebarContent({ collapsed, onCollapse, onNavClick }: SidebarContentProps) {
  const { user, clearAuth, refreshToken } = useAuthStore();
  const { theme, hasFeature } = useTenantStore();
  const location = useLocation();
  const sections = getNavForRole(user?.role);

  const handleLogout = async () => {
    try {
      if (refreshToken) await authService.logout(refreshToken);
    } catch {
      // proceed regardless
    } finally {
      broadcastLogout('manual_logout');
      clearAuth();
      window.location.href = '/login';
    }
  };

  return (
    <div className={cn(
      'flex h-full flex-col bg-sidebar transition-all duration-300',
      collapsed ? 'w-[72px]' : 'w-[280px]',
    )}>
      {/* ─── Logo ──────────────────────────────────────────────── */}
      <div className="flex items-center h-16 px-4 border-b border-sidebar-border">
        {theme.logo ? (
          <img
            src={theme.logo}
            alt={theme.name}
            className="h-9 w-9 rounded-xl object-cover flex-shrink-0"
          />
        ) : (
          <div className="h-9 w-9 rounded-xl bg-gradient-to-br from-accent to-purple-500 flex items-center justify-center flex-shrink-0">
            <span className="text-white font-bold text-sm">
              {(theme.name || 'L').charAt(0)}
            </span>
          </div>
        )}
        {!collapsed && (
          <span className="ml-3 text-base font-semibold text-white truncate">
            {theme.name}
          </span>
        )}
      </div>

      {/* ─── Navigation ────────────────────────────────────────── */}
      <nav className="flex-1 px-3 py-4 space-y-6 overflow-y-auto dark-scrollbar">
        {sections.map((section, si) => {
          const visibleItems = section.items.filter(
            (item) => !item.feature || hasFeature(item.feature)
          );
          if (visibleItems.length === 0) return null;

          return (
            <div key={si}>
              {section.title && !collapsed && (
                <div className="px-3 mb-2 text-[11px] font-semibold uppercase tracking-wider text-sidebar-text/50">
                  {section.title}
                </div>
              )}
              <div className="space-y-1">
                {visibleItems.map((item) => {
                  const isActive = location.pathname === item.href ||
                    (item.href !== '/admin/dashboard' &&
                     item.href !== '/teacher/dashboard' &&
                     item.href !== '/super-admin/dashboard' &&
                     location.pathname.startsWith(item.href));

                  return (
                    <NavLink
                      key={item.href}
                      to={item.href}
                      onClick={onNavClick}
                      title={collapsed ? item.label : undefined}
                      className={cn(
                        'sidebar-link group relative',
                        isActive && 'sidebar-link-active',
                      )}
                    >
                      {isActive && (
                        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full bg-sidebar-accent" />
                      )}
                      <item.icon className={cn(
                        'h-5 w-5 flex-shrink-0 transition-colors',
                        isActive ? 'text-sidebar-accent-glow' : 'text-sidebar-text group-hover:text-sidebar-text-active',
                      )} />
                      {!collapsed && (
                        <span className="truncate">{item.label}</span>
                      )}
                      {!collapsed && item.badge !== undefined && item.badge > 0 && (
                        <span className="ml-auto bg-accent text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                          {item.badge}
                        </span>
                      )}
                    </NavLink>
                  );
                })}
              </div>
            </div>
          );
        })}
      </nav>

      {/* ─── Bottom section ────────────────────────────────────── */}
      <div className="px-3 py-3 border-t border-sidebar-border space-y-1">
        {/* User info */}
        <div className={cn(
          'flex items-center px-3 py-2 rounded-xl',
          collapsed ? 'justify-center' : 'gap-3',
        )}>
          <div className="h-8 w-8 rounded-full bg-gradient-to-br from-accent to-purple-500 flex items-center justify-center flex-shrink-0">
            <span className="text-white text-xs font-semibold">
              {user?.first_name?.charAt(0)}{user?.last_name?.charAt(0)}
            </span>
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <p className="text-sm font-medium text-white truncate">
                {user?.first_name} {user?.last_name}
              </p>
              <p className="text-xs text-sidebar-text truncate">{user?.email}</p>
            </div>
          )}
        </div>

        {/* Logout */}
        <button
          onClick={handleLogout}
          title={collapsed ? 'Logout' : undefined}
          className={cn(
            'flex items-center w-full px-3 py-2.5 rounded-xl text-sidebar-text transition-colors',
            'hover:bg-red-500/10 hover:text-red-400',
            collapsed ? 'justify-center' : 'gap-3',
          )}
        >
          <LogOut className="h-5 w-5 flex-shrink-0" />
          {!collapsed && <span>Logout</span>}
        </button>

        {/* Collapse toggle (desktop only) */}
        <button
          onClick={() => onCollapse(!collapsed)}
          className={cn(
            'hidden lg:flex items-center w-full px-3 py-2.5 rounded-xl text-sidebar-text transition-colors',
            'hover:bg-sidebar-hover hover:text-sidebar-text-active',
            collapsed ? 'justify-center' : 'gap-3',
          )}
        >
          {collapsed ? (
            <ChevronRight className="h-5 w-5" />
          ) : (
            <>
              <ChevronLeft className="h-5 w-5" />
              <span>Collapse</span>
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ─── Main Sidebar Export ─────────────────────────────────────────────────────

interface SidebarProps {
  mobileOpen: boolean;
  onMobileClose: () => void;
}

export function Sidebar({ mobileOpen, onMobileClose }: SidebarProps) {
  const [collapsed, setCollapsed] = useState(false);

  return (
    <>
      {/* Desktop sidebar */}
      <div className="hidden lg:flex flex-shrink-0">
        <SidebarContent
          collapsed={collapsed}
          onCollapse={setCollapsed}
        />
      </div>

      {/* Mobile sidebar (drawer) */}
      <Transition.Root show={mobileOpen} as={Fragment}>
        <Dialog as="div" className="relative z-50 lg:hidden" onClose={onMobileClose}>
          <Transition.Child
            as={Fragment}
            enter="transition-opacity ease-linear duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="transition-opacity ease-linear duration-300"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" />
          </Transition.Child>

          <div className="fixed inset-0 flex pointer-events-none">
            <Transition.Child
              as={Fragment}
              enter="transition ease-in-out duration-300 transform"
              enterFrom="-translate-x-full"
              enterTo="translate-x-0"
              leave="transition ease-in-out duration-300 transform"
              leaveFrom="translate-x-0"
              leaveTo="-translate-x-full"
            >
              <Dialog.Panel className="pointer-events-auto relative flex w-[280px]">
                <SidebarContent
                  collapsed={false}
                  onCollapse={() => {}}
                  onNavClick={onMobileClose}
                />
                <button
                  onClick={onMobileClose}
                  className="absolute top-4 -right-12 p-2 rounded-full bg-black/40 text-white hover:bg-black/60"
                >
                  <X className="h-5 w-5" />
                </button>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </Dialog>
      </Transition.Root>
    </>
  );
}
