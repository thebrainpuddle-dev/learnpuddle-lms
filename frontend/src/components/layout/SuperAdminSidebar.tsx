import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  HomeIcon,
  BuildingOffice2Icon,
  ArrowRightOnRectangleIcon,
  QuestionMarkCircleIcon,
} from '@heroicons/react/24/outline';
import { useAuthStore } from '../../stores/authStore';
import { broadcastLogout } from '../../utils/authSession';
import { useGuidedTour } from '../tour';

const navItems = [
  { to: '/super-admin/dashboard', label: 'Dashboard', icon: HomeIcon, tourId: 'superadmin-nav-dashboard' },
  { to: '/super-admin/schools', label: 'Schools', icon: BuildingOffice2Icon, tourId: 'superadmin-nav-schools' },
];

export const SuperAdminSidebar: React.FC = () => {
  const { clearAuth } = useAuthStore();
  const { startTour } = useGuidedTour();

  return (
    <aside data-tour="superadmin-sidebar" className="fixed inset-y-0 left-0 w-64 bg-slate-900 text-white flex flex-col z-30">
      {/* Brand */}
      <div className="h-16 flex items-center px-6 border-b border-slate-800">
        <span className="text-lg font-bold tracking-tight">Command Center</span>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            data-tour={item.tourId}
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
};
