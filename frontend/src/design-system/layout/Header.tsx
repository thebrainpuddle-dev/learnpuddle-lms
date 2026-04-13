import React from 'react';
import { useLocation, Link } from 'react-router-dom';
import { Menu, Bell, Search, ChevronRight } from 'lucide-react';
import { cn } from '../theme/cn';
import { useAuthStore } from '../../stores/authStore';

interface HeaderProps {
  onMenuClick: () => void;
}

function getBreadcrumbs(pathname: string): { label: string; href?: string }[] {
  const segments = pathname.split('/').filter(Boolean);
  if (segments.length === 0) return [{ label: 'Home' }];

  const crumbs: { label: string; href?: string }[] = [];
  let path = '';

  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    path += '/' + seg;

    // Format label
    const label = seg
      .replace(/-/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());

    // UUID-like segments → skip
    if (seg.length > 20 && seg.includes('-')) continue;

    if (i < segments.length - 1) {
      crumbs.push({ label, href: path });
    } else {
      crumbs.push({ label });
    }
  }

  return crumbs;
}

export function Header({ onMenuClick }: HeaderProps) {
  const { pathname } = useLocation();
  const { user } = useAuthStore();
  const crumbs = getBreadcrumbs(pathname);

  const greeting = getGreeting();

  return (
    <header className="h-16 bg-surface-card border-b border-surface-border flex items-center px-4 lg:px-6 gap-4">
      {/* Mobile menu button */}
      <button
        onClick={onMenuClick}
        className="lg:hidden p-2 rounded-xl text-content-muted hover:bg-surface-card-hover hover:text-content transition-colors"
      >
        <Menu className="h-5 w-5" />
      </button>

      {/* Breadcrumbs */}
      <nav className="hidden md:flex items-center gap-1.5 text-sm min-w-0">
        {crumbs.map((crumb, i) => (
          <React.Fragment key={i}>
            {i > 0 && <ChevronRight className="h-3.5 w-3.5 text-content-muted flex-shrink-0" />}
            {crumb.href ? (
              <Link
                to={crumb.href}
                className="text-content-muted hover:text-content transition-colors truncate"
              >
                {crumb.label}
              </Link>
            ) : (
              <span className="text-content font-medium truncate">{crumb.label}</span>
            )}
          </React.Fragment>
        ))}
      </nav>

      {/* Mobile: show current page name */}
      <div className="md:hidden text-sm font-medium text-content truncate">
        {crumbs[crumbs.length - 1]?.label}
      </div>

      {/* Spacer */}
      <div className="flex-1" />

      {/* Search (placeholder) */}
      <button className="hidden sm:flex items-center gap-2 px-3 py-2 rounded-xl bg-surface text-content-muted text-sm border border-surface-border hover:border-surface-border hover:bg-surface-card-hover transition-colors">
        <Search className="h-4 w-4" />
        <span className="hidden lg:inline">Search...</span>
        <kbd className="hidden lg:inline-flex h-5 items-center gap-1 rounded border border-surface-border bg-surface px-1.5 text-[10px] font-medium text-content-muted">
          <span className="text-xs">⌘</span>K
        </kbd>
      </button>

      {/* Notifications */}
      <button className="relative p-2 rounded-xl text-content-muted hover:bg-surface-card-hover hover:text-content transition-colors">
        <Bell className="h-5 w-5" />
      </button>

      {/* User avatar (mobile only — desktop avatar is in sidebar) */}
      <div className="lg:hidden h-8 w-8 rounded-full bg-gradient-to-br from-accent to-purple-500 flex items-center justify-center flex-shrink-0">
        <span className="text-white text-xs font-semibold">
          {user?.first_name?.charAt(0)}{user?.last_name?.charAt(0)}
        </span>
      </div>
    </header>
  );
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return 'Good morning';
  if (hour < 17) return 'Good afternoon';
  return 'Good evening';
}
