// src/components/maic/ExportMenu.tsx
//
// Dropdown menu for exporting MAIC classrooms to PowerPoint, HTML, ZIP, or JSON.
// Includes both server-side (proxy) and client-side (local) export options.

import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  Download,
  FileText,
  Presentation,
  Loader2,
  Archive,
  FileJson,
} from 'lucide-react';
import { maicApi } from '../../services/openmaicService';
import { useExportPptx } from '../../lib/export/useExportPptx';
import { useExportClassroom } from '../../lib/export/useExportClassroom';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { cn } from '../../lib/utils';

interface ExportMenuProps {
  classroomId: string;
}

type ExportFormat = 'pptx' | 'html' | 'pptx-client' | 'zip' | 'json';

export const ExportMenu = React.memo<ExportMenuProps>(function ExportMenu({ classroomId }) {
  const [isOpen, setIsOpen] = useState(false);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Client-side export hooks
  const {
    exportPptx,
    isExporting: isPptxExporting,
    progress: pptxProgress,
    error: pptxError,
  } = useExportPptx();

  const {
    exportZip,
    isExporting: isZipExporting,
    progress: zipProgress,
    error: zipError,
  } = useExportClassroom();

  // Determine if any client-side export is running
  const isClientExporting = isPptxExporting || isZipExporting;
  const clientProgress = isPptxExporting ? pptxProgress : isZipExporting ? zipProgress : 0;
  const clientError = pptxError || zipError;

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;

    function handleClickOutside(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  const handleExport = useCallback(
    async (format: ExportFormat) => {
      if (exporting || isClientExporting) return;

      // ── Client-side exports ──────────────────────────────────────────────
      if (format === 'pptx-client') {
        setExporting(format);
        try {
          await exportPptx();
        } finally {
          setExporting(null);
        }
        return;
      }

      if (format === 'zip') {
        setExporting(format);
        try {
          await exportZip();
        } finally {
          setExporting(null);
        }
        return;
      }

      if (format === 'json') {
        setExporting(format);
        try {
          const { slides, scenes, agents } = useMAICStageStore.getState();
          const payload = JSON.stringify({ slides, scenes, agents }, null, 2);
          const blob = new Blob([payload], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = 'classroom-export.json';
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(url);
          setIsOpen(false);
        } catch (err) {
          console.error('JSON export failed:', err);
        } finally {
          setExporting(null);
        }
        return;
      }

      // ── Server-side exports (pptx, html) ────────────────────────────────
      setExporting(format);

      try {
        const response =
          format === 'pptx'
            ? await maicApi.exportPptx(classroomId)
            : await maicApi.exportHtml(classroomId);

        const blob =
          response.data instanceof Blob
            ? response.data
            : new Blob([response.data], {
                type:
                  format === 'pptx'
                    ? 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
                    : 'text/html',
              });

        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `classroom-export.${format}`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        setIsOpen(false);
      } catch (err) {
        console.error(`Export ${format} failed:`, err);
      } finally {
        setExporting(null);
      }
    },
    [classroomId, exporting, isClientExporting, exportPptx, exportZip],
  );

  // ── Export option definitions ────────────────────────────────────────────

  const serverOptions: {
    format: ExportFormat;
    label: string;
    icon: typeof Presentation;
  }[] = [
    { format: 'pptx', label: 'Export as PowerPoint', icon: Presentation },
    { format: 'html', label: 'Export as HTML', icon: FileText },
  ];

  const localOptions: {
    format: ExportFormat;
    label: string;
    icon: typeof Presentation;
  }[] = [
    { format: 'pptx-client', label: 'Export as PowerPoint (Client)', icon: Presentation },
    { format: 'zip', label: 'Export as Classroom ZIP', icon: Archive },
    { format: 'json', label: 'Export as JSON', icon: FileJson },
  ];

  const isAnyExporting = exporting !== null || isClientExporting;

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setIsOpen((v) => !v)}
        className={cn(
          'p-1.5 rounded-md transition-colors',
          'focus:outline-none focus:ring-2 focus:ring-primary-500',
          isOpen
            ? 'bg-gray-200 text-gray-900'
            : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100',
        )}
        title="Export"
        aria-label="Export classroom"
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        <Download className="h-4 w-4" />
      </button>

      {isOpen && (
        <div className="absolute top-full right-0 mt-1 w-60 bg-white rounded-lg shadow-lg border border-gray-200 z-20 py-1">
          {/* ── Server Export Section ──────────────────────────────────── */}
          <div className="px-3 py-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
              Server Export
            </span>
          </div>

          {serverOptions.map(({ format, label, icon: Icon }) => (
            <button
              key={format}
              type="button"
              onClick={() => handleExport(format)}
              disabled={isAnyExporting}
              className={cn(
                'w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors',
                'hover:bg-gray-50',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              {exporting === format ? (
                <Loader2 className="h-4 w-4 text-primary-500 animate-spin shrink-0" />
              ) : (
                <Icon className="h-4 w-4 text-gray-400 shrink-0" />
              )}
              <span className="text-gray-700">{label}</span>
            </button>
          ))}

          {/* ── Divider ────────────────────────────────────────────────── */}
          <div className="my-1 border-t border-gray-200" />

          {/* ── Local Export Section ───────────────────────────────────── */}
          <div className="px-3 py-1.5">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-400">
              Local Export
            </span>
          </div>

          {localOptions.map(({ format, label, icon: Icon }) => (
            <button
              key={format}
              type="button"
              onClick={() => handleExport(format)}
              disabled={isAnyExporting}
              className={cn(
                'w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left transition-colors',
                'hover:bg-gray-50',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              {exporting === format ? (
                <Loader2 className="h-4 w-4 text-primary-500 animate-spin shrink-0" />
              ) : (
                <Icon className="h-4 w-4 text-gray-400 shrink-0" />
              )}
              <span className="text-gray-700">{label}</span>
            </button>
          ))}

          {/* ── Progress bar (shown during client-side export) ─────── */}
          {isClientExporting && (
            <div className="px-3 py-2 border-t border-gray-100">
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-gray-500">
                  Exporting... {clientProgress}%
                </span>
              </div>
              <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary-500 rounded-full transition-all duration-200"
                  style={{ width: `${clientProgress}%` }}
                />
              </div>
            </div>
          )}

          {/* ── Error display ──────────────────────────────────────── */}
          {clientError && !isClientExporting && (
            <div className="px-3 py-2 border-t border-gray-100">
              <span className="text-xs text-red-500">{clientError}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
