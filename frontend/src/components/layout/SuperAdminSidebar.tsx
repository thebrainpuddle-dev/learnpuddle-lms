import React, { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { NavLink } from 'react-router-dom';
import {
  XMarkIcon,
  HomeIcon,
  SignalIcon,
  BuildingOffice2Icon,
  ArrowRightOnRectangleIcon,
  QuestionMarkCircleIcon,
} from '@heroicons/react/24/outline';
import { useAuthStore } from '../../stores/authStore';
import { broadcastLogout } from '../../utils/authSession';
import { useGuidedTour } from '../tour';

const navItems = [
  { to: '/super-admin/dashboard', label: 'Dashboard', icon: HomeIcon, tourId: 'superadmin-nav-dashboard' },
  { to: '/super-admin/operations', label: 'Operations', icon: SignalIcon, tourId: 'superadmin-nav-operations' },
  { to: '/super-admin/schools', label: 'Schools', icon: BuildingOffice2Icon, tourId: 'superadmin-nav-schools' },
];

interface SuperAdminSidebarProps {
  open: boolean;
  onClose?: () => void;
}

export const SuperAdminSidebar: React.FC<SuperAdminSidebarProps> = ({ open, onClose }) => {
  const { clearAuth } = useAuthStore();
  const { startTour } = useGuidedTour();

  const SidebarContent = () => (
    <aside data-tour="superadmin-sidebar" className="flex h-full w-full flex-col bg-slate-900 text-white">
      {/* Brand */}
      <div className="flex h-16 items-center justify-between border-b border-slate-800 px-6">
        <span className="text-lg font-bold tracking-tight">Command Center</span>
        {onClose && (
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white lg:hidden"
            aria-label="Close navigation"
          >
            <XMarkIcon className="h-6 w-6" />
          </button>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            data-tour={item.tourId}
            onClick={() => onClose?.()}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-slate-800 text-white'
                  : 'text-slate-300 hover:bg-slate-800 hover:text-white'
              }`
            }
          >
            <item.icon className="h-5 w-5" />
            {item.label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-3 border-t border-slate-800">
        <button
          type="button"
          onClick={startTour}
          data-tour="superadmin-tour-replay"
          className="flex items-center gap-3 w-full mb-2 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
        >
          <QuestionMarkCircleIcon className="h-5 w-5" />
          Start Tour
        </button>
        <button
          onClick={() => {
            broadcastLogout('manual_logout');
            clearAuth();
            window.location.href = '/super-admin/login';
          }}
          className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium text-slate-300 hover:bg-slate-800 hover:text-white transition-colors"
        >
          <ArrowRightOnRectangleIcon className="h-5 w-5" />
          Sign out
        </button>
      </div>
    </aside>
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

  return <SidebarContent />;
};
