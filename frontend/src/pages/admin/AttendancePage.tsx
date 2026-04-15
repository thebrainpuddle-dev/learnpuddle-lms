// src/pages/admin/AttendancePage.tsx
//
// Admin attendance overview — school-wide stats, section breakdown, CSV import.

import React, { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Upload,
  Download,
  AlertTriangle,
  CheckCircle,
  X,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';
import { usePageTitle } from '../../hooks/usePageTitle';
import { AttendanceCard } from '../../components/attendance/AttendanceCard';
import { AttendanceLoader } from '../../components/attendance/AttendanceLoader';
import { ExportAttendanceModal } from '../../components/attendance/ExportAttendanceModal';
import api from '../../config/api';

interface SectionStat {
  section_id: string;
  section_name: string;
  grade_name: string;
  grade_short_code: string;
  total: number;
  present: number;
  late: number;
  absent: number;
  rate: number;
}

interface OverviewResponse {
  date: string;
  summary: {
    total: number;
    present: number;
    late: number;
    absent: number;
    excused: number;
    attendance_rate: number;
    on_time_pct: number;
    late_pct: number;
    absent_pct: number;
    trend: number;
  };
  bars: { status: string }[];
  sections: SectionStat[];
}

interface ImportResult {
  created: number;
  updated: number;
  errors: string[];
  total_errors: number;
}

export const AdminAttendancePage: React.FC = () => {
  usePageTitle('Attendance');

  const queryClient = useQueryClient();
  const today = new Date();
  const [selectedDate, setSelectedDate] = useState(
    today.toISOString().split('T')[0],
  );
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [exportOpen, setExportOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data, isLoading, error } = useQuery<OverviewResponse>({
    queryKey: ['adminAttendance', selectedDate],
    queryFn: async () => {
      const res = await api.get('/v1/admin/attendance/overview/', {
        params: { date: selectedDate },
      });
      return res.data;
    },
  });

  const importMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post('/v1/admin/attendance/import/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return res.data as ImportResult;
    },
    onSuccess: (result) => {
      setImportResult(result);
      queryClient.invalidateQueries({ queryKey: ['adminAttendance'] });
    },
  });

  const goToPrev = () => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() - 1);
    setSelectedDate(d.toISOString().split('T')[0]);
  };

  const goToNext = () => {
    const d = new Date(selectedDate);
    d.setDate(d.getDate() + 1);
    const todayStr = today.toISOString().split('T')[0];
    if (d.toISOString().split('T')[0] <= todayStr) {
      setSelectedDate(d.toISOString().split('T')[0]);
    }
  };

  const isToday = selectedDate === today.toISOString().split('T')[0];

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      importMutation.mutate(file);
      e.target.value = '';
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Attendance
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            School-wide attendance overview
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setExportOpen(true)}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors shadow-sm"
          >
            <Download className="h-4 w-4" />
            Export CSV
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={handleFileChange}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={importMutation.isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-tp-accent px-4 py-2.5 text-sm font-semibold text-white hover:bg-tp-accent-dark transition-colors shadow-sm disabled:opacity-50"
          >
            <Upload className="h-4 w-4" />
            {importMutation.isPending ? 'Importing...' : 'Import CSV'}
          </button>
        </div>
      </div>

      {/* Import result banner */}
      {importResult && (
        <div
          className={cn(
            'rounded-xl border px-5 py-4 flex items-start gap-3',
            importResult.total_errors > 0
              ? 'bg-amber-50 border-amber-200'
              : 'bg-emerald-50 border-emerald-200',
          )}
        >
          {importResult.total_errors > 0 ? (
            <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0 mt-0.5" />
          ) : (
            <CheckCircle className="h-5 w-5 text-emerald-500 flex-shrink-0 mt-0.5" />
          )}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-900">
              Import complete: {importResult.created} created, {importResult.updated} updated
              {importResult.total_errors > 0 && `, ${importResult.total_errors} errors`}
            </p>
            {importResult.errors.length > 0 && (
              <ul className="mt-2 space-y-0.5 text-xs text-amber-700">
                {importResult.errors.slice(0, 5).map((err, i) => (
                  <li key={i}>{err}</li>
                ))}
                {importResult.total_errors > 5 && (
                  <li>...and {importResult.total_errors - 5} more</li>
                )}
              </ul>
            )}
          </div>
          <button
            onClick={() => setImportResult(null)}
            className="p-1 rounded-md text-slate-400 hover:text-slate-600"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Date navigation */}
      <div className="flex items-center gap-3">
        <button
          onClick={goToPrev}
          className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors"
        >
          <ChevronLeft className="h-4 w-4 text-slate-500" />
        </button>
        <span className="text-sm font-semibold text-slate-900">
          {new Date(selectedDate + 'T12:00:00').toLocaleDateString('en-US', {
            weekday: 'long',
            month: 'long',
            day: 'numeric',
            year: 'numeric',
          })}
        </span>
        <button
          onClick={goToNext}
          disabled={isToday}
          className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors disabled:opacity-30"
        >
          <ChevronRight className="h-4 w-4 text-slate-500" />
        </button>
      </div>

      {/* Loading */}
      {isLoading && <AttendanceLoader />}

      {/* Error */}
      {error && !isLoading && (
        <div className="text-center py-16">
          <AlertTriangle className="h-8 w-8 text-red-400 mx-auto mb-3" />
          <p className="text-sm font-medium text-slate-900">
            Unable to load attendance data
          </p>
          <p className="text-xs text-slate-500 mt-1">Please try again later.</p>
        </div>
      )}

      {/* Content */}
      {data && (
        <div className="space-y-6 animate-fade-in">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Attendance Card */}
            <AttendanceCard
              title="School Attendance"
              summary={data.summary}
              bars={data.bars}
              trend={data.summary.trend}
            />

            {/* Section breakdown */}
            <div className="lg:col-span-2 rounded-2xl border border-slate-200/80 bg-white overflow-hidden shadow-sm">
              <div className="px-6 py-4 border-b border-slate-100">
                <h3 className="text-sm font-semibold text-slate-900">
                  By Section
                </h3>
              </div>

              {data.sections.length === 0 ? (
                <div className="px-6 py-12 text-center">
                  <CalendarDays className="h-8 w-8 text-slate-200 mx-auto mb-3" />
                  <p className="text-sm text-slate-500">
                    No attendance data for this date
                  </p>
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b border-slate-100 bg-slate-50/60">
                        <th className="px-5 py-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                          Section
                        </th>
                        <th className="px-5 py-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider text-right">
                          Total
                        </th>
                        <th className="px-5 py-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider text-right">
                          Present
                        </th>
                        <th className="px-5 py-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider text-right">
                          Late
                        </th>
                        <th className="px-5 py-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider text-right">
                          Absent
                        </th>
                        <th className="px-5 py-3 text-[11px] font-semibold text-slate-500 uppercase tracking-wider text-right">
                          Rate
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-50">
                      {data.sections.map((section) => (
                        <tr
                          key={section.section_id}
                          className="hover:bg-orange-50/30 transition-colors"
                        >
                          <td className="px-5 py-3.5">
                            <div>
                              <span className="text-[13px] font-medium text-slate-900">
                                {section.section_name}
                              </span>
                              <span className="ml-2 text-[11px] text-slate-400">
                                {section.grade_name}
                              </span>
                            </div>
                          </td>
                          <td className="px-5 py-3.5 text-right text-[13px] text-slate-600 tabular-nums">
                            {section.total}
                          </td>
                          <td className="px-5 py-3.5 text-right text-[13px] text-blue-600 tabular-nums font-medium">
                            {section.present}
                          </td>
                          <td className="px-5 py-3.5 text-right text-[13px] text-amber-600 tabular-nums font-medium">
                            {section.late}
                          </td>
                          <td className="px-5 py-3.5 text-right text-[13px] text-red-500 tabular-nums font-medium">
                            {section.absent}
                          </td>
                          <td className="px-5 py-3.5 text-right">
                            <span
                              className={cn(
                                'inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold',
                                section.rate >= 90
                                  ? 'bg-emerald-50 text-emerald-700'
                                  : section.rate >= 75
                                    ? 'bg-amber-50 text-amber-700'
                                    : 'bg-red-50 text-red-600',
                              )}
                            >
                              {section.rate}%
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Empty state when data loads but no records */}
      {data && data.summary.total === 0 && (
        <div className="text-center py-16">
          <div className="mx-auto h-14 w-14 rounded-2xl bg-slate-100 flex items-center justify-center mb-4">
            <CalendarDays className="h-7 w-7 text-slate-300" />
          </div>
          <p className="text-sm font-medium text-slate-900">
            No attendance data for this date
          </p>
          <p className="text-xs text-slate-500 mt-1">
            Import attendance records using the CSV import button above.
          </p>
        </div>
      )}

      <ExportAttendanceModal
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        portal="admin"
      />
    </div>
  );
};
