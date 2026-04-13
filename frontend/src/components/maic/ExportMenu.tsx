// src/components/maic/ExportMenu.tsx
//
// Dropdown menu for exporting MAIC classrooms to PowerPoint or HTML.
// Uses blob downloads via the proxy export endpoints.

import React, { useState, useCallback, useRef, useEffect } from 'react';
import { Download, FileText, Presentation, Loader2 } from 'lucide-react';
import { maicApi } from '../../services/openmaicService';
import { cn } from '../../lib/utils';

interface ExportMenuProps {
  classroomId: string;
}

type ExportFormat = 'pptx' | 'html';

export const ExportMenu = React.memo<ExportMenuProps>(function ExportMenu({ classroomId }) {
  const [isOpen, setIsOpen] = useState(false);
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);

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
      if (exporting) return;
      setExporting(format);

      try {
        const response = format === 'pptx'
          ? await maicApi.exportPptx(classroomId)
          : await maicApi.exportHtml(classroomId);

        const blob = response.data instanceof Blob
          ? response.data
          : new Blob([response.data], {
              type: format === 'pptx'
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
    [classroomId, exporting],
  );

  const exportOptions: { format: ExportFormat; label: string; icon: typeof Presentation }[] = [
    { format: 'pptx', label: 'Export as PowerPoint', icon: Presentation },
    { format: 'html', label: 'Export as HTML', icon: FileText },
  ];

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
        <div className="absolute top-full right-0 mt-1 w-52 bg-white rounded-lg shadow-lg border border-gray-200 z-20 py-1">
          {exportOptions.map(({ format, label, icon: Icon }) => (
            <button
              key={format}
              type="button"
              onClick={() => handleExport(format)}
              disabled={exporting !== null}
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
        </div>
      )}
    </div>
  );
});
