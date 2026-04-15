// src/components/layout/StudentSidebar.tsx
//
// Polished sidebar for student portal — indigo accent, section labels.

import React, { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  BookOpen,
  ClipboardList,
  Trophy,
  UserCircle,
  Settings,
  HelpCircle,
  LogOut,
  X,
  Presentation,
  Bot,
  Sparkles,
  MessageSquare,
  CalendarDays,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';
import { useAuthStore } from '../../stores/authStore';
import { useTenantStore } from '../../stores/tenantStore';
import { authService } from '../../services/authService';
import { broadcastLogout } from '../../utils/authSession';

interface StudentSidebarProps {
  open: boolean;
  onClose?: () => void;
}

const MY_LEARNING_NAV = [
  { label: 'Dashboard', href: '/student/dashboard', icon: LayoutDashboard },
  { label: 'My Courses', href: '/student/courses', icon: BookOpen },
  { label: 'Assignments', href: '/student/assignments', icon: ClipboardList },
  { label: 'Achievements', href: '/student/achievements', icon: Trophy },
  { label: 'Attendance', href: '/student/attendance', icon: CalendarDays },
];

const AI_TOOLS_NAV = [
  { label: 'AI Classroom', href: '/student/ai-classroom', icon: Presentation },
  { label: 'AI Tutor', href: '/student/chatbots', icon: Bot },
  { label: 'Study Summaries', href: '/student/study-notes', icon: Sparkles },
  { label: 'Discussions', href: '/student/discussions', icon: MessageSquare },
];

const BOTTOM_ITEMS = [
  { label: 'Profile', href: '/student/profile', icon: UserCircle },
  { label: 'Settings', href: '/student/settings', icon: Settings },
];

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-3 pt-5 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-300">
      {children}
    </p>
  );
}

function NavItem({
  item,
  onClose,
}: {
  item: { label: string; href: string; icon: React.ElementType };
  onClose?: () => void;
}) {
  return (
    <NavLink
      to={item.href}
      onClick={onClose}
      className={({ isActive }) =>
        cn(
          'relative flex items-center gap-2.5 px-3 py-[9px] rounded-lg text-[13px] font-medium transition-all duration-150',
          isActive
            ? 'bg-indigo-50 text-indigo-600'
            : 'text-gray-500 hover:bg-gray-50 hover:text-tp-text',
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-4 rounded-r-full bg-indigo-600" />
          )}
          <item.icon className={cn('h-[18px] w-[18px] flex-shrink-0', isActive ? 'text-indigo-600' : 'text-gray-400')} />
          <span>{item.label}</span>
        </>
      )}
    </NavLink>
  );
}

export const StudentSidebar: React.FC<StudentSidebarProps> = ({ open, onClose }) => {
  const { user, clearAuth, refreshToken } = useAuthStore();
  const { theme } = useTenantStore();

  const tenantName = theme?.name || 'LearnPuddle';
  const tenantInitial = tenantName.charAt(0).toUpperCase();

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

  const SidebarContent = () => (
    <div className="flex flex-col h-full bg-white border-r border-gray-100">
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-4 h-[60px] flex-shrink-0 border-b border-gray-100">
        {theme?.logo ? (
          <img
            src={theme.logo}
            alt={tenantName}
            className="h-8 w-8 rounded-full object-cover"
          />
        ) : (
          <div className="h-8 w-8 rounded-full bg-gradient-to-br from-indigo-500 to-indigo-600 flex items-center justify-center flex-shrink-0 shadow-sm">
            <span className="text-white font-bold text-[13px]">{tenantInitial}</span>
          </div>
        )}
        <span className="text-tp-text font-semibold text-[15px] truncate tracking-tight">
          {tenantName}
        </span>

        {onClose && (
          <button
            onClick={onClose}
            className="ml-auto lg:hidden p-1 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-50"
          >
            <X className="h-5 w-5" />
          </button>
        )}
      </div>

      {/* User */}
      <div className="px-4 py-3.5 border-b border-gray-100">
        <div className="flex items-center gap-2.5">
          <div className="h-9 w-9 rounded-full bg-gradient-to-br from-indigo-100 to-indigo-50 flex items-center justify-center ring-2 ring-indigo-100 flex-shrink-0">
            <span className="text-indigo-600 font-semibold text-[12px]">
              {user?.first_name?.charAt(0)}
              {user?.last_name?.charAt(0)}
            </span>
          </div>
          <div className="min-w-0">
            <p className="text-[13px] font-medium text-tp-text truncate leading-tight">
              {user?.first_name} {user?.last_name}
            </p>
            {user?.grade_name || user?.section_name ? (
              <p className="text-[11px] text-indigo-500 font-medium truncate">
                {[user.grade_name, user.section_name && `Section ${user.section_name}`].filter(Boolean).join(' · ')}
              </p>
            ) : (
              <p className="text-[11px] text-gray-400 font-medium">Student</p>
            )}
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 overflow-y-auto tp-scrollbar">
        <SectionLabel>My Learning</SectionLabel>
        <div className="space-y-0.5">
          {MY_LEARNING_NAV.map((item) => (
            <NavItem key={item.href} item={item} onClose={onClose} />
          ))}
        </div>

        <SectionLabel>AI Tools</SectionLabel>
        <div className="space-y-0.5">
          {AI_TOOLS_NAV.map((item) => (
            <NavItem key={item.href} item={item} onClose={onClose} />
          ))}
        </div>
      </nav>

      {/* Bottom */}
      <div className="px-3 py-3 border-t border-gray-100 space-y-0.5">
        {BOTTOM_ITEMS.map((item) => (
          <NavItem key={item.href} item={item} onClose={onClose} />
        ))}

        <a
          href="mailto:support@learnpuddle.com"
          className="relative flex items-center gap-2.5 px-3 py-[9px] rounded-lg text-[13px] font-medium text-gray-500 hover:bg-gray-50 hover:text-tp-text transition-all duration-150"
        >
          <HelpCircle className="h-[18px] w-[18px] flex-shrink-0 text-gray-400" />
          <span>Support</span>
        </a>

        <button
          onClick={handleLogout}
          className="flex items-center gap-2.5 w-full px-3 py-[9px] rounded-lg text-[13px] font-medium text-gray-500 hover:bg-red-50 hover:text-red-500 transition-colors"
        >
          <LogOut className="h-[18px] w-[18px] flex-shrink-0" />
          <span>Logout</span>
        </button>
      </div>
    </div>
  );

  if (onClose) {
    return (
      <Transition.Root show={open} as={Fragment}>
        <Dialog as="div" className="relative z-50 lg:hidden" onClose={onClose}>
          <Transition.Child
            as={Fragment}
            enter="transition-opacity ease-linear duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="transition-opacity ease-linear duration-300"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-black/20 backdrop-blur-[2px]" />
          </Transition.Child>

          <div className="fixed inset-0 flex">
            <Transition.Child
              as={Fragment}
              enter="transition ease-in-out duration-300 transform"
              enterFrom="-translate-x-full"
              enterTo="translate-x-0"
              leave="transition ease-in-out duration-300 transform"
              leaveFrom="translate-x-0"
              leaveTo="-translate-x-full"
            >
              <Dialog.Panel className="relative mr-10 flex w-[85vw] max-w-xs flex-1">
                <SidebarContent />
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </Dialog>
      </Transition.Root>
    );
  }

  return <SidebarContent />;
};
