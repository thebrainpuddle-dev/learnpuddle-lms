// src/components/layout/TeacherHeader.tsx
//
// Polished header — refined search, notification dropdown.

import React, { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Menu,
  Search,
  Bell,
  Check,
  GraduationCap,
  Clock,
  Megaphone,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';
import { notificationService, Notification } from '../../services/notificationService';
import { formatDistanceToNow } from 'date-fns';

interface TeacherHeaderProps {
  onMenuClick: () => void;
}

const NotifIcon: React.FC<{ type: Notification['notification_type'] }> = ({ type }) => {
  const base = 'h-4 w-4';
  switch (type) {
    case 'COURSE_ASSIGNED':
      return <GraduationCap className={cn(base, 'text-tp-accent')} />;
    case 'ASSIGNMENT_DUE':
      return <Clock className={cn(base, 'text-amber-500')} />;
    case 'REMINDER':
      return <Bell className={cn(base, 'text-red-400')} />;
    case 'ANNOUNCEMENT':
      return <Megaphone className={cn(base, 'text-blue-500')} />;
    default:
      return <Bell className={cn(base, 'text-gray-400')} />;
  }
};

export const TeacherHeader: React.FC<TeacherHeaderProps> = ({ onMenuClick }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const { data: unreadCount = 0 } = useQuery({
    queryKey: ['notificationUnreadCount'],
    queryFn: () => notificationService.getUnreadCount(),
    refetchInterval: 30000,
  });

  const { data: notifications = [], isLoading } = useQuery({
    queryKey: ['notifications'],
    queryFn: () => notificationService.getNotifications({ limit: 10 }),
    enabled: dropdownOpen,
  });

  const markAsReadMutation = useMutation({
    mutationFn: notificationService.markAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
      queryClient.invalidateQueries({ queryKey: ['notificationUnreadCount'] });
    },
  });

  const markAllAsReadMutation = useMutation({
    mutationFn: notificationService.markAllAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
      queryClient.invalidateQueries({ queryKey: ['notificationUnreadCount'] });
    },
  });

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleNotificationClick = (notification: Notification) => {
    if (!notification.is_read) markAsReadMutation.mutate(notification.id);
    if (notification.course) {
      navigate(`/teacher/courses/${notification.course}`);
    } else if (notification.assignment) {
      navigate('/teacher/assignments');
    } else {
      navigate('/teacher/reminders');
    }
    setDropdownOpen(false);
  };

  return (
    <header className="sticky top-0 z-30 flex items-center h-[56px] px-4 lg:px-6 bg-white/80 backdrop-blur-md border-b border-gray-100/80 flex-shrink-0">
      {/* Mobile menu */}
      <button
        onClick={onMenuClick}
        className="lg:hidden p-2 -ml-1 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors mr-2"
      >
        <Menu className="h-5 w-5" />
      </button>

      {/* Search */}
      <div className="flex-1 max-w-sm">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-[14px] w-[14px] text-gray-400" />
          <input
            type="text"
            placeholder="Search courses, assessments..."
            onFocus={() => setSearchFocused(true)}
            onBlur={() => setSearchFocused(false)}
            className={cn(
              'w-full pl-9 pr-4 py-[7px] rounded-lg text-[13px] border transition-all duration-200',
              'text-tp-text placeholder:text-gray-400',
              searchFocused
                ? 'border-tp-accent/40 ring-2 ring-tp-accent/10 bg-white shadow-sm'
                : 'border-gray-200 bg-gray-50/80 hover:bg-gray-50',
            )}
          />
          {!searchFocused && (
            <kbd className="absolute right-3 top-1/2 -translate-y-1/2 hidden sm:inline-flex items-center px-1.5 py-0.5 rounded border border-gray-200 bg-white text-[10px] text-gray-400 font-medium">
              ⌘K
            </kbd>
          )}
        </div>
      </div>

      {/* Right side */}
      <div className="flex items-center gap-1 ml-3">
        {/* Notifications */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className={cn(
              'relative p-2 rounded-lg transition-colors',
              dropdownOpen
                ? 'bg-gray-100 text-tp-text'
                : 'text-gray-400 hover:text-gray-600 hover:bg-gray-50',
            )}
          >
            <Bell className="h-[18px] w-[18px]" />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 flex items-center justify-center h-4 min-w-[16px] px-1 rounded-full bg-tp-accent text-white text-[9px] font-bold leading-none shadow-sm">
                {unreadCount > 9 ? '9+' : unreadCount}
              </span>
            )}
          </button>

          {dropdownOpen && (
            <div className="absolute right-0 mt-1.5 w-80 sm:w-[360px] rounded-xl bg-white border border-gray-200 shadow-dropdown z-50 overflow-hidden animate-scale-in origin-top-right">
              <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
                <h3 className="text-[13px] font-semibold text-tp-text">Notifications</h3>
                {unreadCount > 0 && (
                  <button
                    onClick={() => markAllAsReadMutation.mutate()}
                    className="text-[11px] text-tp-accent hover:text-tp-accent-dark font-medium flex items-center gap-1 transition-colors"
                  >
                    <Check className="h-3 w-3" />
                    Mark all read
                  </button>
                )}
              </div>

              <div className="max-h-[320px] overflow-y-auto tp-scrollbar">
                {isLoading ? (
                  <div className="p-6 text-center text-gray-400 text-[13px]">Loading...</div>
                ) : notifications.length === 0 ? (
                  <div className="py-10 text-center">
                    <Bell className="h-7 w-7 mx-auto text-gray-200 mb-2" />
                    <p className="text-[13px] text-gray-400 font-medium">No notifications</p>
                  </div>
                ) : (
                  notifications.map((n) => (
                    <button
                      key={n.id}
                      onClick={() => handleNotificationClick(n)}
                      className={cn(
                        'w-full text-left px-4 py-3 border-b border-gray-50 hover:bg-gray-50/80 transition-colors',
                        !n.is_read && 'bg-orange-50/30',
                      )}
                    >
                      <div className="flex items-start gap-2.5">
                        <div className="mt-0.5 flex-shrink-0 h-7 w-7 rounded-lg bg-gray-50 flex items-center justify-center">
                          <NotifIcon type={n.notification_type} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-2">
                            <p
                              className={cn(
                                'text-[13px] leading-snug',
                                n.is_read
                                  ? 'text-gray-500'
                                  : 'text-tp-text font-medium',
                              )}
                            >
                              {n.title}
                            </p>
                            {!n.is_read && (
                              <span className="w-[6px] h-[6px] rounded-full bg-tp-accent flex-shrink-0 mt-1.5" />
                            )}
                          </div>
                          <p className="text-[11px] text-gray-400 mt-0.5 line-clamp-1">
                            {n.message}
                          </p>
                          <p className="text-[10px] text-gray-300 mt-1 font-medium">
                            {formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}
                          </p>
                        </div>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
