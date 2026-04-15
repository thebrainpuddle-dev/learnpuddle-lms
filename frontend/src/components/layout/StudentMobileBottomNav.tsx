// src/components/layout/StudentMobileBottomNav.tsx
//
// Bottom tab bar for student mobile — indigo accent.

import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  BookOpen,
  ClipboardList,
  Trophy,
  MoreHorizontal,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';

const TABS = [
  { label: 'Dashboard', href: '/student/dashboard', icon: LayoutDashboard },
  { label: 'Courses', href: '/student/courses', icon: BookOpen },
  { label: 'Tasks', href: '/student/assignments', icon: ClipboardList },
  { label: 'Awards', href: '/student/achievements', icon: Trophy },
  { label: 'More', href: '/student/profile', icon: MoreHorizontal },
];

export const StudentMobileBottomNav: React.FC = () => {
  const location = useLocation();

  return (
    <nav
      className="fixed bottom-0 inset-x-0 z-40 bg-white/90 backdrop-blur-md border-t border-gray-100/80 lg:hidden safe-bottom"
      aria-label="Mobile navigation"
    >
      <div className="flex items-center justify-around h-14 max-w-lg mx-auto">
        {TABS.map((tab) => {
          const active = location.pathname.startsWith(tab.href);

          return (
            <NavLink
              key={tab.label}
              to={tab.href}
              className="relative flex flex-col items-center justify-center flex-1 h-full min-h-[44px] min-w-[44px]"
              aria-label={tab.label}
            >
              <tab.icon
                className={cn(
                  'h-[18px] w-[18px] transition-colors',
                  active ? 'text-indigo-600' : 'text-gray-400',
                )}
              />
              <span
                className={cn(
                  'mt-0.5 text-[9px] font-semibold leading-tight tracking-wide',
                  active ? 'text-indigo-600' : 'text-gray-400',
                )}
              >
                {tab.label}
              </span>
              {active && (
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-6 h-[2px] rounded-full bg-indigo-600" />
              )}
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
};
