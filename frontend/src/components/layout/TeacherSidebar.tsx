// src/components/layout/TeacherSidebar.tsx

import React, { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { NavLink } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  XMarkIcon,
  HomeIcon,
  BookOpenIcon,
  ClipboardDocumentListIcon,
  UserCircleIcon,
  ArrowRightOnRectangleIcon,
  BellAlertIcon,
  QuestionMarkCircleIcon,
} from '@heroicons/react/24/outline';
import { useAuthStore } from '../../stores/authStore';
import { authService } from '../../services/authService';
import { useTenantStore } from '../../stores/tenantStore';
import { notificationService } from '../../services/notificationService';
import { broadcastLogout } from '../../utils/authSession';
import { useGuidedTour } from '../tour';

interface TeacherSidebarProps {
  open: boolean;
  onClose?: () => void;
}

const navigation = [
  { name: 'Dashboard', href: '/teacher/dashboard', icon: HomeIcon, tourId: 'teacher-nav-dashboard' },
  { name: 'My Courses', href: '/teacher/courses', icon: BookOpenIcon, tourId: 'teacher-nav-courses' },
  { name: 'Assignments', href: '/teacher/assignments', icon: ClipboardDocumentListIcon, tourId: 'teacher-nav-assignments' },
  { name: 'Reminders', href: '/teacher/reminders', icon: BellAlertIcon, badgeKey: 'reminders' as const, tourId: 'teacher-nav-reminders' },
  { name: 'Profile', href: '/teacher/profile', icon: UserCircleIcon, tourId: 'teacher-nav-profile' },
];

export const TeacherSidebar: React.FC<TeacherSidebarProps> = ({ open, onClose }) => {
  const { user, clearAuth, refreshToken } = useAuthStore();
  const { theme } = useTenantStore();
  const { startTour } = useGuidedTour();

  // Poll unread reminder count for sidebar badge (every 30s)
  const { data: unreadReminderCount = 0 } = useQuery({
    queryKey: ['unreadReminderCount'],
    queryFn: () => notificationService.getUnreadCount({ type: 'REMINDER' }),
    refetchInterval: 30000,
  });
  
  const handleLogout = async () => {
    try {
      if (refreshToken) {
        await authService.logout(refreshToken);
      }
    } catch (error) {
      console.error('Logout error:', error);
    } finally {
      broadcastLogout('manual_logout');
      clearAuth();
      window.location.href = '/login';
    }
  };
  
  const SidebarContent = () => (
    <div data-tour="teacher-sidebar" className="flex flex-col h-full bg-gradient-to-b from-slate-900 to-slate-800">
      {/* Logo */}
      <div className="flex items-center justify-between h-16 px-6 border-b border-slate-700">
        <div className="flex items-center">
          {theme.logo ? (
            <img
              src={theme.logo}
              alt={theme.name}
              className="h-8 w-8 rounded-lg object-cover bg-white"
            />
          ) : (
            <div className="h-8 w-8 bg-emerald-500 rounded-lg flex items-center justify-center">
              <BookOpenIcon className="h-5 w-5 text-white" />
            </div>
          )}
          <span className="ml-3 text-lg font-semibold text-white">
            {theme.name}
          </span>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="lg:hidden text-slate-400 hover:text-white"
          >
            <XMarkIcon className="h-6 w-6" />
          </button>
        )}
      </div>
      
      {/* User info */}
      <div className="px-6 py-4 border-b border-slate-700">
        <div className="flex items-center">
          <div className="flex-shrink-0">
            <div className="h-10 w-10 rounded-full bg-emerald-500/20 flex items-center justify-center ring-2 ring-emerald-500/50">
              <span className="text-emerald-400 font-medium">
                {user?.first_name?.charAt(0)}{user?.last_name?.charAt(0)}
              </span>
            </div>
          </div>
          <div className="ml-3">
            <p className="text-sm font-medium text-white">
              {user?.first_name} {user?.last_name}
            </p>
            <p className="text-xs text-slate-400">{user?.role?.replace('_', ' ')}</p>
          </div>
        </div>
      </div>
      
      {/* Navigation */}
      <nav className="flex-1 px-4 py-4 space-y-1 overflow-y-auto">
        {navigation.map((item) => {
          const badge = ('badgeKey' in item && item.badgeKey === 'reminders') ? unreadReminderCount : 0;
          return (
            <NavLink
              key={item.name}
              to={item.href}
              data-tour={item.tourId}
              className={({ isActive }) =>
                `flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-all duration-200 ${
                  isActive
                    ? 'bg-emerald-500/20 text-emerald-400 shadow-lg shadow-emerald-500/10'
                    : 'text-slate-300 hover:bg-slate-700/50 hover:text-white'
                }`
              }
            >
              <item.icon className="h-5 w-5 mr-3" />
              {item.name}
              {badge > 0 && (
                <span className="ml-auto inline-flex items-center justify-center h-5 min-w-[1.25rem] px-1.5 rounded-full bg-red-500 text-white text-xs font-medium">
                  {badge > 99 ? '99+' : badge}
                </span>
              )}
            </NavLink>
          );
        })}
      </nav>
      
      {/* Logout */}
      <div className="px-4 py-4 border-t border-slate-700">
        <button
          type="button"
          data-tour="teacher-tour-replay"
          onClick={startTour}
          className="flex items-center w-full px-4 py-3 mb-2 text-slate-300 hover:bg-emerald-500/10 hover:text-emerald-300 rounded-lg transition-colors"
        >
          <QuestionMarkCircleIcon className="h-5 w-5 mr-3" />
          Start Tour
        </button>
        <button
          onClick={handleLogout}
          className="flex items-center w-full px-4 py-3 text-slate-300 hover:bg-red-500/10 hover:text-red-400 rounded-lg transition-colors"
        >
          <ArrowRightOnRectangleIcon className="h-5 w-5 mr-3" />
          Logout
        </button>
      </div>
    </div>
  );
  
  // Mobile version (drawer)
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
            <div className="fixed inset-0 bg-slate-900/80" />
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
              <Dialog.Panel className="relative mr-16 flex w-full max-w-xs flex-1">
                <SidebarContent />
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </Dialog>
      </Transition.Root>
    );
  }
  
  // Desktop version
  return <SidebarContent />;
};
