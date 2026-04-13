// src/components/layout/StudentHeader.tsx
//
// Polished header for student portal — search, notifications.

import React, { useState, useRef, useEffect, useCallback } from 'react';
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
  BookOpen,
  FileText,
  Loader2,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';
import { notificationService, Notification } from '../../services/notificationService';
import { studentService } from '../../services/studentService';
import { formatDistanceToNow } from 'date-fns';

interface StudentHeaderProps {
  onMenuClick: () => void;
}

const NotifIcon: React.FC<{ type: Notification['notification_type'] }> = ({ type }) => {
  const base = 'h-4 w-4';
  switch (type) {
    case 'COURSE_ASSIGNED':
      return <GraduationCap className={cn(base, 'text-indigo-500')} />;
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

export const StudentHeader: React.FC<StudentHeaderProps> = ({ onMenuClick }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [showSearchDropdown, setShowSearchDropdown] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Submit search — navigate to courses page with search param
  const handleSearchSubmit = useCallback(() => {
    const q = searchQuery.trim();
    if (!q) return;
    setShowSearchDropdown(false);
    navigate(`/student/courses?search=${encodeURIComponent(q)}`);
  }, [searchQuery, navigate]);

  // Debounced live search
  useEffect(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);

    if (searchQuery.trim().length < 3) {
      setSearchResults([]);
      setShowSearchDropdown(false);
      return;
    }

    setSearchLoading(true);
    debounceTimerRef.current = setTimeout(async () => {
      try {
        const results = await studentService.searchStudentContent(searchQuery.trim());
        setSearchResults(Array.isArray(results) ? results.slice(0, 6) : []);
        setShowSearchDropdown(true);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 300);

    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [searchQuery]);

  // Close search dropdown on click outside
  useEffect(() => {
    const handleClickOutsideSearch = (event: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setShowSearchDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutsideSearch);
    return () => document.removeEventListener('mousedown', handleClickOutsideSearch);
  }, []);

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
      navigate(`/student/courses/${notification.course}`);
    } else if (notification.assignment) {
      navigate('/student/assignments');
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
      <div className="flex-1 max-w-sm" ref={searchRef}>
        <div className="relative">
          <button
            type="button"
            onClick={handleSearchSubmit}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 transition-colors"
            tabIndex={-1}
          >
            {searchLoading ? (
              <Loader2 className="h-[14px] w-[14px] animate-spin" />
            ) : (
              <Search className="h-[14px] w-[14px]" />
            )}
          </button>
          <input
            type="text"
            placeholder="Search courses, assignments..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => {
              setSearchFocused(true);
              if (searchQuery.trim().length >= 3 && searchResults.length > 0) {
                setShowSearchDropdown(true);
              }
            }}
            onBlur={() => setSearchFocused(false)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                handleSearchSubmit();
              }
              if (e.key === 'Escape') {
                setShowSearchDropdown(false);
              }
            }}
            className={cn(
              'w-full pl-9 pr-4 py-[7px] rounded-lg text-[13px] border transition-all duration-200',
              'text-tp-text placeholder:text-gray-400',
              searchFocused
                ? 'border-indigo-400/40 ring-2 ring-indigo-400/10 bg-white shadow-sm'
                : 'border-gray-200 bg-gray-50/80 hover:bg-gray-50',
            )}
          />
          {!searchFocused && !searchQuery && (
            <kbd className="absolute right-3 top-1/2 -translate-y-1/2 hidden sm:inline-flex items-center px-1.5 py-0.5 rounded border border-gray-200 bg-white text-[10px] text-gray-400 font-medium">
              /
            </kbd>
          )}

          {/* Search results dropdown */}
          {showSearchDropdown && searchResults.length > 0 && (
            <div className="absolute top-full left-0 right-0 mt-1.5 rounded-xl bg-white border border-gray-200 shadow-dropdown z-50 overflow-hidden animate-scale-in origin-top">
              <div className="px-3 py-2 border-b border-gray-100">
                <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-400">
                  Results
                </p>
              </div>
              <div className="max-h-[280px] overflow-y-auto tp-scrollbar">
                {searchResults.map((result: any, idx: number) => (
                  <button
                    key={result.id || idx}
                    type="button"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      setShowSearchDropdown(false);
                      if (result.course_id) {
                        navigate(`/student/courses/${result.course_id}`);
                      } else if (result.id) {
                        navigate(`/student/courses/${result.id}`);
                      }
                    }}
                    className="w-full text-left px-3 py-2.5 hover:bg-gray-50/80 transition-colors flex items-center gap-2.5 border-b border-gray-50 last:border-b-0"
                  >
                    <div className="flex-shrink-0 h-7 w-7 rounded-lg bg-indigo-50 flex items-center justify-center">
                      {result.content_type === 'DOCUMENT' ? (
                        <FileText className="h-3.5 w-3.5 text-indigo-500" />
                      ) : (
                        <BookOpen className="h-3.5 w-3.5 text-indigo-500" />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-medium text-tp-text truncate">
                        {result.title}
                      </p>
                      {result.course_title && (
                        <p className="text-[11px] text-gray-400 truncate">
                          {result.course_title}
                        </p>
                      )}
                    </div>
                  </button>
                ))}
              </div>
              <button
                type="button"
                onMouseDown={(e) => {
                  e.preventDefault();
                  handleSearchSubmit();
                }}
                className="w-full px-3 py-2.5 text-[12px] font-medium text-indigo-600 hover:bg-indigo-50/50 transition-colors border-t border-gray-100 text-center"
              >
                View all results
              </button>
            </div>
          )}

          {/* No results message */}
          {showSearchDropdown && searchResults.length === 0 && !searchLoading && searchQuery.trim().length >= 3 && (
            <div className="absolute top-full left-0 right-0 mt-1.5 rounded-xl bg-white border border-gray-200 shadow-dropdown z-50 overflow-hidden animate-scale-in origin-top">
              <div className="py-6 text-center">
                <Search className="h-5 w-5 mx-auto text-gray-200 mb-1.5" />
                <p className="text-[13px] text-gray-400">No results found</p>
                <button
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    handleSearchSubmit();
                  }}
                  className="mt-2 text-[12px] text-indigo-600 hover:text-indigo-700 font-medium"
                >
                  Search all courses
                </button>
              </div>
            </div>
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
              <span className="absolute top-1 right-1 flex items-center justify-center h-4 min-w-[16px] px-1 rounded-full bg-indigo-600 text-white text-[9px] font-bold leading-none shadow-sm">
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
                    className="text-[11px] text-indigo-600 hover:text-indigo-700 font-medium flex items-center gap-1 transition-colors"
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
                        !n.is_read && 'bg-indigo-50/30',
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
                              <span className="w-[6px] h-[6px] rounded-full bg-indigo-600 flex-shrink-0 mt-1.5" />
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
