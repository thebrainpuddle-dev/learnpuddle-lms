// src/components/layout/MobileBottomNav.tsx
//
// Bottom tab bar for mobile — light white + orange accent.

import React from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  BookOpen,
  ClipboardList,
  Megaphone,
  MoreHorizontal,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';

interface MobileBottomNavProps {
  basePath?: string;
}

const TABS = [
  { label: 'Overview', href: 'dashboard', icon: LayoutDashboard },
  { label: 'Courses', href: 'courses', icon: BookOpen },
  { label: 'Assessments', href: 'assignments', icon: ClipboardList },
  { label: 'Announce', href: 'reminders', icon: Megaphone },
  { label: 'More', href: 'profile', icon: MoreHorizontal },
];

export const MobileBottomNav: React.FC<MobileBottomNavProps> = ({ basePath = '/teacher' }) => {
  const location = useLocation();

  return (
    <nav
      className="fixed bottom-0 inset-x-0 z-40 bg-white/90 backdrop-blur-md border-t border-gray-100/80 lg:hidden safe-bottom"
      aria-label="Mobile navigation"
    >
      <div className="flex items-center justify-around h-14 max-w-lg mx-auto">
        {TABS.map((tab) => {
          const fullHref = `${basePath}/${tab.href}`;
          const active = location.pathname.startsWith(fullHref);

          return (
            <NavLink
              key={tab.label}
              to={fullHref}
              className="relative flex flex-col items-center justify-center flex-1 h-full"
              aria-label={tab.label}
            >
              <tab.icon
                className={cn(
                  'h-[18px] w-[18px] transition-colors',
                  active ? 'text-tp-accent' : 'text-gray-400',
                )}
              />
              <span
                className={cn(
                  'mt-0.5 text-[9px] font-semibold leading-tight tracking-wide',
                  active ? 'text-tp-accent' : 'text-gray-400',
                )}
              >
                {tab.label}
              </span>
              {active && (
                <div className="absolute top-0 left-1/2 -translate-x-1/2 w-6 h-[2px] rounded-full bg-tp-accent" />
              )}
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
};

export default MobileBottomNav;
