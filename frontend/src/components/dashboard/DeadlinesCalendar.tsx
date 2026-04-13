// src/components/dashboard/DeadlinesCalendar.tsx
//
// Month-view calendar showing upcoming course deadlines and assignment due dates.
// Replaces the old activity feed on the admin dashboard.

import React, { useState, useMemo } from 'react';
import {
  ChevronLeft,
  ChevronRight,
  BookOpen,
  FileText,
  Calendar as CalendarIcon,
  X,
} from 'lucide-react';
import { Card, Badge, cn } from '../../design-system';

// ─── Types ───────────────────────────────────────────────────────────────────

interface DeadlineEvent {
  id: string;
  title: string;
  type: 'course' | 'assignment';
  date: string; // ISO date string (YYYY-MM-DD)
  courseName?: string;
}

// ─── Mock Data ───────────────────────────────────────────────────────────────
// TODO: Replace with actual API call — e.g. adminService.getUpcomingDeadlines()

function getMockDeadlines(): DeadlineEvent[] {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth();

  return [
    { id: '1', title: 'IB Mathematics HL', type: 'course', date: `${year}-${String(month + 1).padStart(2, '0')}-08`, courseName: 'IB Mathematics HL' },
    { id: '2', title: 'Unit 3 Quiz', type: 'assignment', date: `${year}-${String(month + 1).padStart(2, '0')}-08`, courseName: 'IB Mathematics HL' },
    { id: '3', title: 'Physics Lab Report', type: 'assignment', date: `${year}-${String(month + 1).padStart(2, '0')}-12`, courseName: 'Physics SL' },
    { id: '4', title: 'English Literature Essay', type: 'assignment', date: `${year}-${String(month + 1).padStart(2, '0')}-15`, courseName: 'English Literature' },
    { id: '5', title: 'Chemistry Module 4', type: 'course', date: `${year}-${String(month + 1).padStart(2, '0')}-18`, courseName: 'Chemistry HL' },
    { id: '6', title: 'Biology Final Assessment', type: 'assignment', date: `${year}-${String(month + 1).padStart(2, '0')}-22`, courseName: 'Biology SL' },
    { id: '7', title: 'History Research Paper', type: 'assignment', date: `${year}-${String(month + 1).padStart(2, '0')}-25`, courseName: 'History HL' },
    { id: '8', title: 'Teacher Training Deadline', type: 'course', date: `${year}-${String(month + 1).padStart(2, '0')}-28`, courseName: 'Professional Development' },
  ];
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function getDaysInMonth(year: number, month: number): number {
  return new Date(year, month + 1, 0).getDate();
}

function getFirstDayOfMonth(year: number, month: number): number {
  return new Date(year, month, 1).getDay();
}

function toDateKey(year: number, month: number, day: number): string {
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
}

// ─── Component ───────────────────────────────────────────────────────────────

export const DeadlinesCalendar: React.FC = () => {
  const today = new Date();
  const [currentYear, setCurrentYear] = useState(today.getFullYear());
  const [currentMonth, setCurrentMonth] = useState(today.getMonth());
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const deadlines = useMemo(() => getMockDeadlines(), []);

  // Group deadlines by date key
  const deadlinesByDate = useMemo(() => {
    const map: Record<string, DeadlineEvent[]> = {};
    for (const d of deadlines) {
      if (!map[d.date]) map[d.date] = [];
      map[d.date].push(d);
    }
    return map;
  }, [deadlines]);

  const daysInMonth = getDaysInMonth(currentYear, currentMonth);
  const firstDay = getFirstDayOfMonth(currentYear, currentMonth);
  const todayKey = toDateKey(today.getFullYear(), today.getMonth(), today.getDate());

  const selectedEvents = selectedDate ? (deadlinesByDate[selectedDate] || []) : [];

  function goToPrevMonth() {
    if (currentMonth === 0) {
      setCurrentMonth(11);
      setCurrentYear(currentYear - 1);
    } else {
      setCurrentMonth(currentMonth - 1);
    }
    setSelectedDate(null);
  }

  function goToNextMonth() {
    if (currentMonth === 11) {
      setCurrentMonth(0);
      setCurrentYear(currentYear + 1);
    } else {
      setCurrentMonth(currentMonth + 1);
    }
    setSelectedDate(null);
  }

  return (
    <Card padding="none">
      {/* Header */}
      <div className="px-5 py-3.5 border-b border-surface-border flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CalendarIcon className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-semibold text-content">Deadlines Calendar</h3>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={goToPrevMonth}
            className="p-1.5 rounded-lg hover:bg-surface transition-colors"
            title="Previous month"
          >
            <ChevronLeft className="h-4 w-4 text-content-secondary" />
          </button>
          <span className="text-sm font-medium text-content min-w-[130px] text-center">
            {MONTH_NAMES[currentMonth]} {currentYear}
          </span>
          <button
            onClick={goToNextMonth}
            className="p-1.5 rounded-lg hover:bg-surface transition-colors"
            title="Next month"
          >
            <ChevronRight className="h-4 w-4 text-content-secondary" />
          </button>
        </div>
      </div>

      {/* Calendar Grid */}
      <div className="p-4">
        {/* Weekday Headers */}
        <div className="grid grid-cols-7 mb-2">
          {WEEKDAYS.map((day) => (
            <div key={day} className="text-center text-[10px] font-semibold text-content-muted uppercase tracking-wider py-1">
              {day}
            </div>
          ))}
        </div>

        {/* Day Cells */}
        <div className="grid grid-cols-7 gap-0.5">
          {/* Empty cells before the first day */}
          {Array.from({ length: firstDay }).map((_, i) => (
            <div key={`empty-${i}`} className="h-10" />
          ))}

          {/* Day cells */}
          {Array.from({ length: daysInMonth }).map((_, i) => {
            const day = i + 1;
            const dateKey = toDateKey(currentYear, currentMonth, day);
            const events = deadlinesByDate[dateKey] || [];
            const isToday = dateKey === todayKey;
            const isSelected = dateKey === selectedDate;
            const hasEvents = events.length > 0;

            return (
              <button
                key={day}
                onClick={() => setSelectedDate(isSelected ? null : dateKey)}
                className={cn(
                  'relative h-10 rounded-lg flex flex-col items-center justify-center text-sm transition-colors',
                  isToday && !isSelected && 'bg-accent-50 font-bold text-accent',
                  isSelected && 'bg-accent text-white',
                  !isToday && !isSelected && 'text-content hover:bg-surface',
                  hasEvents && 'cursor-pointer',
                )}
                title={hasEvents ? `${events.length} deadline${events.length > 1 ? 's' : ''}` : undefined}
              >
                <span className="leading-none">{day}</span>
                {hasEvents && (
                  <div className="flex gap-0.5 mt-0.5">
                    {events.length <= 3 ? (
                      events.map((_, idx) => (
                        <span
                          key={idx}
                          className={cn(
                            'h-1 w-1 rounded-full',
                            isSelected ? 'bg-white' : 'bg-accent',
                          )}
                        />
                      ))
                    ) : (
                      <>
                        <span className={cn('h-1 w-1 rounded-full', isSelected ? 'bg-white' : 'bg-accent')} />
                        <span className={cn('h-1 w-1 rounded-full', isSelected ? 'bg-white' : 'bg-accent')} />
                        <span className={cn('text-[8px] leading-none font-bold', isSelected ? 'text-white/80' : 'text-accent')}>
                          +{events.length - 2}
                        </span>
                      </>
                    )}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Day Detail Panel */}
      {selectedDate && (
        <div className="border-t border-surface-border p-4">
          <div className="flex items-center justify-between mb-3">
            <p className="text-xs font-semibold text-content-secondary uppercase tracking-wide">
              {new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-US', {
                weekday: 'long',
                month: 'long',
                day: 'numeric',
              })}
            </p>
            <button
              onClick={() => setSelectedDate(null)}
              className="p-1 rounded-md hover:bg-surface transition-colors"
              title="Close"
            >
              <X className="h-3.5 w-3.5 text-content-muted" />
            </button>
          </div>

          {selectedEvents.length === 0 ? (
            <p className="text-sm text-content-muted py-2">No deadlines on this day</p>
          ) : (
            <div className="space-y-2">
              {selectedEvents.map((event) => (
                <div
                  key={event.id}
                  className="flex items-center gap-3 p-2.5 rounded-xl hover:bg-surface transition-colors"
                >
                  <div className={cn(
                    'h-8 w-8 rounded-lg flex items-center justify-center flex-shrink-0',
                    event.type === 'course' ? 'bg-accent-50' : 'bg-warning-bg',
                  )}>
                    {event.type === 'course' ? (
                      <BookOpen className="h-4 w-4 text-accent" />
                    ) : (
                      <FileText className="h-4 w-4 text-warning" />
                    )}
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-content truncate">{event.title}</p>
                    {event.courseName && (
                      <p className="text-[10px] text-content-muted truncate">{event.courseName}</p>
                    )}
                  </div>
                  <Badge
                    variant={event.type === 'course' ? 'default' : 'warning'}
                    size="sm"
                  >
                    {event.type === 'course' ? 'Course' : 'Assignment'}
                  </Badge>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
};
