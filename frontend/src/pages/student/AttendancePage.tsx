// src/pages/student/AttendancePage.tsx
//
// Student's own attendance — monthly calendar view + summary stats.

import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  CalendarDays,
  Download,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';
import { usePageTitle } from '../../hooks/usePageTitle';
import { AttendanceCard } from '../../components/attendance/AttendanceCard';
import { AttendanceLoader } from '../../components/attendance/AttendanceLoader';
import api from '../../config/api';
import { ExportAttendanceModal } from '../../components/attendance/ExportAttendanceModal';

interface AttendanceDay {
  date: string;
  status: string;
  remarks: string;
}

interface AttendanceSummary {
  total_days: number;
  present: number;
  late: number;
  absent: number;
  excused: number;
  attendance_rate: number;
  on_time_pct: number;
  late_pct: number;
  absent_pct: number;
}

interface AttendanceResponse {
  month: string;
  summary: AttendanceSummary;
  days: AttendanceDay[];
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const STATUS_COLORS: Record<string, string> = {
  PRESENT: 'bg-blue-500',
  LATE: 'bg-amber-400',
  ABSENT: 'bg-red-400',
  EXCUSED: 'bg-slate-300',
};

const STATUS_LABELS: Record<string, string> = {
  PRESENT: 'Present',
  LATE: 'Late',
  ABSENT: 'Absent',
  EXCUSED: 'Excused',
};

export const StudentAttendancePage: React.FC = () => {
  usePageTitle('My Attendance');

  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState(now.getMonth() + 1);
  const [exportOpen, setExportOpen] = useState(false);

  const monthStr = `${year}-${String(month).padStart(2, '0')}`;

  const { data, isLoading, error } = useQuery<AttendanceResponse>({
    queryKey: ['studentAttendance', monthStr],
    queryFn: async () => {
      const res = await api.get('/v1/student/attendance/', { params: { month: monthStr } });
      return res.data;
    },
  });

  const goToPrev = () => {
    if (month === 1) { setMonth(12); setYear(year - 1); }
    else setMonth(month - 1);
  };

  const goToNext = () => {
    if (month === 12) { setMonth(1); setYear(year + 1); }
    else setMonth(month + 1);
  };

  const isCurrentMonth = year === now.getFullYear() && month === now.getMonth() + 1;

  // Build calendar grid
  const firstDay = new Date(year, month - 1, 1);
  const lastDay = new Date(year, month, 0);
  const startDow = (firstDay.getDay() + 6) % 7; // Monday = 0
  const daysInMonth = lastDay.getDate();

  const dayMap = new Map<string, AttendanceDay>();
  if (data?.days) {
    for (const d of data.days) {
      dayMap.set(d.date, d);
    }
  }

  // Build card-compatible data
  const cardSummary = data ? {
    total: data.summary.total_days,
    present: data.summary.present,
    late: data.summary.late,
    absent: data.summary.absent,
    excused: data.summary.excused,
    attendance_rate: data.summary.attendance_rate,
    on_time_pct: data.summary.on_time_pct,
    late_pct: data.summary.late_pct,
    absent_pct: data.summary.absent_pct,
  } : null;

  const bars = data?.days.map((d) => ({ status: d.status })) || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">My Attendance</h1>
          <p className="mt-1 text-sm text-slate-500">Your attendance record for the current academic year</p>
        </div>
        <button
          onClick={() => setExportOpen(true)}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-sm"
        >
          <Download className="h-4 w-4" />
          Export CSV
        </button>
      </div>

      {/* Loading */}
      {isLoading && <AttendanceLoader />}

      {/* Error */}
      {error && !isLoading && (
        <div className="text-center py-16">
          <AlertTriangle className="h-8 w-8 text-red-400 mx-auto mb-3" />
          <p className="text-sm font-medium text-slate-900">Unable to load attendance</p>
          <p className="text-xs text-slate-500 mt-1">Please try again later.</p>
        </div>
      )}

      {/* Content */}
      {data && cardSummary && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-fade-in">
          {/* Attendance Card (matching screenshot design) */}
          <AttendanceCard
            title={`${MONTH_NAMES[month - 1]} Attendance`}
            summary={cardSummary}
            bars={bars}
          />

          {/* Calendar */}
          <div className="rounded-2xl border border-slate-200/80 bg-white p-6 shadow-sm">
            {/* Month navigation */}
            <div className="flex items-center justify-between mb-5">
              <button
                onClick={goToPrev}
                className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors"
              >
                <ChevronLeft className="h-4 w-4 text-slate-500" />
              </button>
              <h3 className="text-sm font-semibold text-slate-900">
                {MONTH_NAMES[month - 1]} {year}
              </h3>
              <button
                onClick={goToNext}
                disabled={isCurrentMonth}
                className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors disabled:opacity-30"
              >
                <ChevronRight className="h-4 w-4 text-slate-500" />
              </button>
            </div>

            {/* Day headers */}
            <div className="grid grid-cols-7 gap-1 mb-1">
              {DAY_NAMES.map((d) => (
                <div key={d} className="text-center text-[10px] font-medium text-slate-400 py-1">
                  {d}
                </div>
              ))}
            </div>

            {/* Calendar grid */}
            <div className="grid grid-cols-7 gap-1">
              {/* Empty cells before month starts */}
              {Array.from({ length: startDow }).map((_, i) => (
                <div key={`empty-${i}`} className="h-9" />
              ))}

              {/* Day cells */}
              {Array.from({ length: daysInMonth }).map((_, i) => {
                const dayNum = i + 1;
                const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(dayNum).padStart(2, '0')}`;
                const record = dayMap.get(dateStr);
                const dow = (startDow + i) % 7;
                const isWeekend = dow >= 5;
                const isToday = year === now.getFullYear() && month === now.getMonth() + 1 && dayNum === now.getDate();

                return (
                  <div
                    key={dayNum}
                    className={cn(
                      'group relative flex h-9 items-center justify-center rounded-lg text-xs font-medium transition-colors',
                      isWeekend && 'text-slate-300',
                      !isWeekend && !record && 'text-slate-400',
                      isToday && 'ring-1 ring-indigo-300',
                    )}
                  >
                    <span>{dayNum}</span>
                    {/* Status dot */}
                    {record && (
                      <div className={cn(
                        'absolute bottom-0.5 left-1/2 -translate-x-1/2 h-1.5 w-1.5 rounded-full',
                        STATUS_COLORS[record.status] || 'bg-slate-300',
                      )} />
                    )}
                    {/* Tooltip */}
                    {record && (
                      <div className="absolute -top-10 left-1/2 -translate-x-1/2 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10">
                        <div className="bg-slate-900 text-white text-[10px] rounded-lg px-2.5 py-1.5 whitespace-nowrap shadow-lg">
                          {STATUS_LABELS[record.status] || record.status}
                          {record.remarks && ` — ${record.remarks}`}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Calendar legend */}
            <div className="flex items-center justify-center gap-4 mt-4 pt-3 border-t border-slate-100">
              {Object.entries(STATUS_COLORS).map(([key, color]) => (
                <div key={key} className="flex items-center gap-1.5">
                  <div className={cn('h-2 w-2 rounded-full', color)} />
                  <span className="text-[10px] text-slate-400">{STATUS_LABELS[key]}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Empty state */}
      {data && data.summary.total_days === 0 && (
        <div className="text-center py-16">
          <div className="mx-auto h-14 w-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
            <CalendarDays className="h-7 w-7 text-slate-300" />
          </div>
          <p className="text-sm font-medium text-slate-900">No attendance records for this month</p>
          <p className="text-xs text-slate-500 mt-1">Attendance data will appear once imported by your school.</p>
        </div>
      )}

      <ExportAttendanceModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        portal="student"
      />
    </div>
  );
};
