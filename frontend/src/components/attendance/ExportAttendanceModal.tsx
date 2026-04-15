// src/components/attendance/ExportAttendanceModal.tsx
//
// Date range picker modal for attendance CSV export.
// Supports: single day, preset ranges, custom range, specific month.

import React, { useState, Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import {
  X,
  Download,
  Calendar,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Check,
} from 'lucide-react';
import { cn } from '../../design-system/theme/cn';
import { downloadCsv } from '../../utils/downloadCsv';

type Portal = 'student' | 'teacher' | 'admin';

interface ExportAttendanceModalProps {
  open: boolean;
  onClose: () => void;
  portal: Portal;
  sectionId?: string; // required for teacher portal
}

type RangeMode = 'preset' | 'custom' | 'month';

interface PresetOption {
  label: string;
  key: string;
  getRange: () => { from: string; to: string };
}

const fmt = (d: Date) => d.toISOString().split('T')[0];

const PRESETS: PresetOption[] = [
  {
    label: 'Today',
    key: 'today',
    getRange: () => {
      const d = fmt(new Date());
      return { from: d, to: d };
    },
  },
  {
    label: 'Yesterday',
    key: 'yesterday',
    getRange: () => {
      const d = new Date();
      d.setDate(d.getDate() - 1);
      const s = fmt(d);
      return { from: s, to: s };
    },
  },
  {
    label: 'Last 7 days',
    key: '7d',
    getRange: () => {
      const to = new Date();
      const from = new Date();
      from.setDate(from.getDate() - 6);
      return { from: fmt(from), to: fmt(to) };
    },
  },
  {
    label: 'Last 30 days',
    key: '30d',
    getRange: () => {
      const to = new Date();
      const from = new Date();
      from.setDate(from.getDate() - 29);
      return { from: fmt(from), to: fmt(to) };
    },
  },
  {
    label: 'This month',
    key: 'this_month',
    getRange: () => {
      const now = new Date();
      const from = new Date(now.getFullYear(), now.getMonth(), 1);
      return { from: fmt(from), to: fmt(now) };
    },
  },
  {
    label: 'Last month',
    key: 'last_month',
    getRange: () => {
      const now = new Date();
      const from = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const to = new Date(now.getFullYear(), now.getMonth(), 0);
      return { from: fmt(from), to: fmt(to) };
    },
  },
  {
    label: 'Last 3 months',
    key: '3m',
    getRange: () => {
      const to = new Date();
      const from = new Date(to.getFullYear(), to.getMonth() - 2, 1);
      return { from: fmt(from), to: fmt(to) };
    },
  },
  {
    label: 'Last 6 months',
    key: '6m',
    getRange: () => {
      const to = new Date();
      const from = new Date(to.getFullYear(), to.getMonth() - 5, 1);
      return { from: fmt(from), to: fmt(to) };
    },
  },
  {
    label: 'This academic year',
    key: 'year',
    getRange: () => {
      const now = new Date();
      // Academic year typically starts in June/July — use June 1
      const startYear = now.getMonth() >= 5 ? now.getFullYear() : now.getFullYear() - 1;
      const from = new Date(startYear, 5, 1); // June 1
      return { from: fmt(from), to: fmt(now) };
    },
  },
];

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function buildExportUrl(portal: Portal, sectionId?: string): string {
  switch (portal) {
    case 'admin':
      return '/v1/admin/attendance/export/';
    case 'teacher':
      return `/v1/teacher/academics/sections/${sectionId}/attendance/export/`;
    case 'student':
      return '/v1/student/attendance/export/';
  }
}

export const ExportAttendanceModal: React.FC<ExportAttendanceModalProps> = ({
  open,
  onClose,
  portal,
  sectionId,
}) => {
  const [mode, setMode] = useState<RangeMode>('preset');
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [customFrom, setCustomFrom] = useState('');
  const [customTo, setCustomTo] = useState('');
  const [monthYear, setMonthYear] = useState(new Date().getFullYear());
  const [monthMonth, setMonthMonth] = useState(new Date().getMonth());
  const [exporting, setExporting] = useState(false);

  const todayStr = fmt(new Date());

  const handleExport = async () => {
    let params: Record<string, string> = {};

    if (mode === 'preset' && selectedPreset) {
      const preset = PRESETS.find((p) => p.key === selectedPreset);
      if (!preset) return;
      const range = preset.getRange();
      if (range.from === range.to) {
        params = { date: range.from };
      } else {
        params = { from_date: range.from, to_date: range.to };
      }
    } else if (mode === 'custom') {
      if (!customFrom || !customTo) return;
      if (customFrom === customTo) {
        params = { date: customFrom };
      } else {
        params = { from_date: customFrom, to_date: customTo };
      }
    } else if (mode === 'month') {
      if (portal === 'student') {
        // Student export uses month param
        params = { month: `${monthYear}-${String(monthMonth + 1).padStart(2, '0')}` };
      } else {
        const from = new Date(monthYear, monthMonth, 1);
        const to = new Date(monthYear, monthMonth + 1, 0);
        params = { from_date: fmt(from), to_date: fmt(to) };
      }
    }

    setExporting(true);
    try {
      await downloadCsv(buildExportUrl(portal, sectionId), params);
      onClose();
    } catch {
      // silently fail — user sees no file
    } finally {
      setExporting(false);
    }
  };

  const canExport =
    (mode === 'preset' && selectedPreset !== null) ||
    (mode === 'custom' && customFrom && customTo && customFrom <= customTo) ||
    mode === 'month';

  return (
    <Transition.Root show={open} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/20 backdrop-blur-[2px]" />
        </Transition.Child>

        <div className="fixed inset-0 z-10 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-150"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-md rounded-2xl bg-white shadow-xl">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
                  <div className="flex items-center gap-2.5">
                    <div className="h-9 w-9 rounded-xl bg-indigo-50 flex items-center justify-center">
                      <Download className="h-4.5 w-4.5 text-indigo-600" />
                    </div>
                    <div>
                      <Dialog.Title className="text-[15px] font-semibold text-slate-900">
                        Export Attendance
                      </Dialog.Title>
                      <p className="text-[11px] text-slate-400">
                        Download as CSV
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={onClose}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-50 transition-colors"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>

                {/* Mode tabs */}
                <div className="flex items-center gap-1 px-6 pt-4">
                  {([
                    { key: 'preset' as RangeMode, label: 'Quick Select', icon: CalendarDays },
                    { key: 'custom' as RangeMode, label: 'Date Range', icon: Calendar },
                    { key: 'month' as RangeMode, label: 'By Month', icon: CalendarDays },
                  ]).map((tab) => (
                    <button
                      key={tab.key}
                      onClick={() => setMode(tab.key)}
                      className={cn(
                        'flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12px] font-medium transition-colors',
                        mode === tab.key
                          ? 'bg-indigo-50 text-indigo-600'
                          : 'text-slate-400 hover:text-slate-600 hover:bg-slate-50',
                      )}
                    >
                      <tab.icon className="h-3.5 w-3.5" />
                      {tab.label}
                    </button>
                  ))}
                </div>

                {/* Content */}
                <div className="px-6 py-4 min-h-[200px]">
                  {/* Preset mode */}
                  {mode === 'preset' && (
                    <div className="grid grid-cols-2 gap-2">
                      {PRESETS.map((preset) => {
                        const active = selectedPreset === preset.key;
                        return (
                          <button
                            key={preset.key}
                            onClick={() => setSelectedPreset(preset.key)}
                            className={cn(
                              'relative flex items-center gap-2 rounded-xl px-3.5 py-2.5 text-[13px] font-medium text-left transition-all border',
                              active
                                ? 'bg-indigo-50 border-indigo-200 text-indigo-700'
                                : 'bg-white border-slate-150 text-slate-600 hover:bg-slate-50 hover:border-slate-200',
                            )}
                          >
                            {active && (
                              <Check className="h-3.5 w-3.5 text-indigo-600 flex-shrink-0" />
                            )}
                            {preset.label}
                          </button>
                        );
                      })}
                    </div>
                  )}

                  {/* Custom range mode */}
                  {mode === 'custom' && (
                    <div className="space-y-4">
                      <div>
                        <label className="block text-[12px] font-medium text-slate-500 mb-1.5">
                          From
                        </label>
                        <input
                          type="date"
                          value={customFrom}
                          max={todayStr}
                          onChange={(e) => setCustomFrom(e.target.value)}
                          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-[13px] text-slate-900 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 focus:outline-none transition-all"
                        />
                      </div>
                      <div>
                        <label className="block text-[12px] font-medium text-slate-500 mb-1.5">
                          To
                        </label>
                        <input
                          type="date"
                          value={customTo}
                          min={customFrom || undefined}
                          max={todayStr}
                          onChange={(e) => setCustomTo(e.target.value)}
                          className="w-full rounded-lg border border-slate-200 px-3 py-2 text-[13px] text-slate-900 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 focus:outline-none transition-all"
                        />
                      </div>
                      {customFrom && customTo && customFrom <= customTo && (
                        <p className="text-[11px] text-slate-400">
                          {Math.ceil(
                            (new Date(customTo).getTime() - new Date(customFrom).getTime()) /
                              (1000 * 60 * 60 * 24),
                          ) + 1}{' '}
                          day(s) selected
                        </p>
                      )}
                      {customFrom && customTo && customFrom > customTo && (
                        <p className="text-[11px] text-red-500">
                          Start date must be before end date
                        </p>
                      )}
                    </div>
                  )}

                  {/* Month picker mode */}
                  {mode === 'month' && (
                    <div className="space-y-4">
                      {/* Year nav */}
                      <div className="flex items-center justify-between">
                        <button
                          onClick={() => setMonthYear((y) => y - 1)}
                          className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors"
                        >
                          <ChevronLeft className="h-4 w-4 text-slate-500" />
                        </button>
                        <span className="text-sm font-semibold text-slate-900">
                          {monthYear}
                        </span>
                        <button
                          onClick={() => setMonthYear((y) => y + 1)}
                          disabled={monthYear >= new Date().getFullYear()}
                          className="p-1.5 rounded-lg hover:bg-slate-100 transition-colors disabled:opacity-30"
                        >
                          <ChevronRight className="h-4 w-4 text-slate-500" />
                        </button>
                      </div>

                      {/* Month grid */}
                      <div className="grid grid-cols-3 gap-2">
                        {MONTH_NAMES.map((name, i) => {
                          const active = monthMonth === i;
                          const now = new Date();
                          const isFuture =
                            monthYear > now.getFullYear() ||
                            (monthYear === now.getFullYear() && i > now.getMonth());

                          return (
                            <button
                              key={name}
                              disabled={isFuture}
                              onClick={() => setMonthMonth(i)}
                              className={cn(
                                'rounded-xl px-3 py-2.5 text-[13px] font-medium transition-all border',
                                active
                                  ? 'bg-indigo-50 border-indigo-200 text-indigo-700'
                                  : isFuture
                                    ? 'bg-slate-50 border-slate-100 text-slate-300 cursor-not-allowed'
                                    : 'bg-white border-slate-150 text-slate-600 hover:bg-slate-50 hover:border-slate-200',
                              )}
                            >
                              {name.substring(0, 3)}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}
                </div>

                {/* Footer */}
                <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-100">
                  <button
                    onClick={onClose}
                    className="rounded-lg px-4 py-2 text-[13px] font-medium text-slate-500 hover:bg-slate-50 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleExport}
                    disabled={!canExport || exporting}
                    className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-[13px] font-semibold text-white hover:bg-indigo-700 transition-colors disabled:opacity-40 shadow-sm"
                  >
                    <Download className="h-3.5 w-3.5" />
                    {exporting ? 'Exporting...' : 'Export CSV'}
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition.Root>
  );
};
