// src/components/layout/AdminSidebar.tsx

import React, { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { NavLink } from 'react-router-dom';
import {
  XMarkIcon,
  HomeIcon,
  AcademicCapIcon,
  UserGroupIcon,
  UsersIcon,
  PaperAirplaneIcon,
  MegaphoneIcon,
  ChartBarIcon,
  Cog6ToothIcon,
  ArrowRightOnRectangleIcon,
  FolderIcon,
  QuestionMarkCircleIcon,
} from '@heroicons/react/24/outline';
import { useAuthStore } from '../../stores/authStore';
import { authService } from '../../services/authService';
import { useTenantStore } from '../../stores/tenantStore';
import { broadcastLogout } from '../../utils/authSession';
import { useGuidedTour } from '../tour';

interface AdminSidebarProps {
  open: boolean;
  onClose?: () => void;
}

const ALL_NAV_ITEMS = [
  { name: 'Dashboard', href: '/admin/dashboard', icon: HomeIcon, feature: null, tourId: 'admin-nav-dashboard' },
  { name: 'Courses', href: '/admin/courses', icon: AcademicCapIcon, feature: null, tourId: 'admin-nav-courses' },
  { name: 'Media', href: '/admin/media', icon: FolderIcon, feature: null, tourId: 'admin-nav-media' },
  { name: 'Teachers', href: '/admin/teachers', icon: UserGroupIcon, feature: null, tourId: 'admin-nav-teachers' },
  { name: 'Groups', href: '/admin/groups', icon: UsersIcon, feature: 'groups' as const, tourId: 'admin-nav-groups' },
  { name: 'Analytics', href: '/admin/analytics', icon: ChartBarIcon, feature: null, tourId: 'admin-nav-analytics' },
  { name: 'Reminders', href: '/admin/reminders', icon: PaperAirplaneIcon, feature: 'reminders' as const, tourId: 'admin-nav-reminders' },
  { name: 'Announcements', href: '/admin/announcements', icon: MegaphoneIcon, feature: null, tourId: 'admin-nav-announcements' },
  { name: 'Settings', href: '/admin/settings', icon: Cog6ToothIcon, feature: null, tourId: 'admin-nav-settings' },
];

export const AdminSidebar: React.FC<AdminSidebarProps> = ({ open, onClose }) => {
  const { user, clearAuth, refreshToken } = useAuthStore();
  const { theme, hasFeature } = useTenantStore();
  const { startTour } = useGuidedTour();

  // Filter navigation items based on tenant feature flags
  const navigation = ALL_NAV_ITEMS.filter(
    (item) => item.feature === null || hasFeature(item.feature)
  );
  
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
    <div data-tour="admin-sidebar" className="flex h-full flex-col bg-white border-r border-gray-200">
      {/* Logo */}
      <div className="flex items-center justify-between h-16 px-6 border-b border-gray-200">
        <div className="flex items-center">
          {theme.logo ? (
            <img
              src={theme.logo}
              alt={theme.name}
              className="h-8 w-8 rounded-lg object-cover bg-white"
            />
          ) : (
            <div className="h-8 w-8 bg-primary-600 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold">
                {(theme.name || 'L').charAt(0)}
              </span>
            </div>
          )}
          <span className="ml-3 line-clamp-1 text-lg font-semibold text-gray-900">
            {theme.name}
          </span>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="lg:hidden text-gray-400 hover:text-gray-500"
          >
            <XMarkIcon className="h-6 w-6" />
          </button>
        )}
      </div>
      
      {/* User info */}
      <div className="px-6 py-4 border-b border-gray-200">
        <div className="flex items-center">
          <div className="flex-shrink-0">
            <div className="h-10 w-10 rounded-full bg-primary-100 flex items-center justify-center">
              <span className="text-primary-700 font-medium">
                {user?.first_name?.charAt(0)}{user?.last_name?.charAt(0)}
              </span>
            </div>
          </div>
          <div className="ml-3 min-w-0">
            <p className="truncate text-sm font-medium text-gray-900">
              {user?.first_name} {user?.last_name}
            </p>
            <p className="truncate text-xs text-gray-500">{user?.role}</p>
          </div>
        </div>
      </div>
      
      {/* Navigation */}
      <nav className="flex-1 px-4 py-4 space-y-1 overflow-y-auto">
        {navigation.map((item) => (
          <NavLink
            key={item.name}
            to={item.href}
            data-tour={item.tourId}
            onClick={() => onClose?.()}
            className={({ isActive }) =>
              isActive
                ? 'sidebar-link sidebar-link-active'
                : 'sidebar-link'
            }
          >
            <item.icon className="h-5 w-5 mr-3" />
            {item.name}
          </NavLink>
        ))}
      </nav>
      
      {/* Logout */}
      <div className="px-4 py-4 border-t border-gray-200">
        <button
          type="button"
          data-tour="admin-tour-replay"
          onClick={startTour}
          className="flex items-center w-full px-4 py-3 mb-2 text-gray-700 hover:bg-primary-50 hover:text-primary-700 rounded-lg transition-colors"
        >
          <QuestionMarkCircleIcon className="h-5 w-5 mr-3" />
          Start Tour
        </button>
        <button
          onClick={handleLogout}
          className="flex items-center w-full px-4 py-3 text-gray-700 hover:bg-red-50 hover:text-red-700 rounded-lg transition-colors"
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
            <div className="fixed inset-0 bg-gray-900/80" />
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
              <Dialog.Panel className="pointer-events-auto relative mr-10 flex w-[85vw] max-w-xs flex-1 sm:mr-16">
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
