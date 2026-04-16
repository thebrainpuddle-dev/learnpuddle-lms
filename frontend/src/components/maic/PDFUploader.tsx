// src/components/maic/PDFUploader.tsx
//
// Drag-and-drop zone for PDF files. Uploads the file to the Django backend
// for parsing, then displays a rich preview of the results. Falls back to
// client-side pdfjs-dist text extraction if the backend is unreachable.

import React, { useState, useRef, useCallback } from 'react';
import { Upload, FileText, X, AlertCircle } from 'lucide-react';
import * as pdfjsLib from 'pdfjs-dist';
import { cn } from '../../lib/utils';
import { parsePDF } from '../../lib/pdf/pdf-service';
import type { ParsedPdfContent } from '../../lib/pdf/types';
import { PDFContentPreview } from './PDFContentPreview';

// Configure worker — use the bundled worker from pdfjs-dist
pdfjsLib.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString();

interface PDFUploaderProps {
  onExtract: (text: string) => void;
  /** When provided, receives the full parsed PDF content from the backend */
  onParsedContent?: (content: ParsedPdfContent) => void;
}

interface UploadState {
  status: 'idle' | 'loading' | 'done' | 'error';
  fileName: string | null;
  pageCount: number;
  progress: number;
  error: string | null;
}

/**
 * Extract text from a PDF using pdfjs-dist.
 * Handles compressed streams, CIDFonts, embedded fonts, and Unicode —
 * all cases where the previous regex-based parser silently failed.
 */
async function extractTextFromPDF(buffer: ArrayBuffer): Promise<{ text: string; pageCount: number }> {
  const pdf = await pdfjsLib.getDocument({ data: buffer }).promise;
  const pageCount = pdf.numPages;
  const pageTexts: string[] = [];

  for (let i = 1; i <= pageCount; i++) {
    const page = await pdf.getPage(i);
    const content = await page.getTextContent();
    const pageText = content.items
      .filter((item) => 'str' in item)
      .map((item) => (item as { str: string }).str)
      .join(' ');
    if (pageText.trim()) {
      pageTexts.push(pageText.trim());
    }
  }

  const text = pageTexts.join('\n\n').trim();
  return { text: text || '(No extractable text found in PDF)', pageCount };
}

export const PDFUploader = React.memo<PDFUploaderProps>(function PDFUploader({ onExtract, onParsedContent }) {
  const [state, setState] = useState<UploadState>({
    status: 'idle',
    fileName: null,
    pageCount: 0,
    progress: 0,
    error: null,
  });
  const [isDragOver, setIsDragOver] = useState(false);
  const [parsedContent, setParsedContent] = useState<ParsedPdfContent | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const processFile = useCallback(
    async (file: File) => {
      if (file.type !== 'application/pdf') {
        setState({
          status: 'error',
          fileName: file.name,
          pageCount: 0,
          progress: 0,
          error: 'Only PDF files are supported.',
        });
        return;
      }

      setState({
        status: 'loading',
        fileName: file.name,
        pageCount: 0,
        progress: 10,
        error: null,
      });

      // Try backend-powered parsing first, fall back to client-side pdfjs
      try {
        setState((prev) => ({ ...prev, progress: 30 }));
        const parsed = await parsePDF(file);
        setState((prev) => ({ ...prev, progress: 90 }));

        const pageCount = parsed.metadata?.pageCount ?? 0;

        setState({
          status: 'done',
          fileName: file.name,
          pageCount,
          progress: 100,
          error: null,
        });

        setParsedContent(parsed);
        setShowPreview(true);
        onParsedContent?.(parsed);
        onExtract(parsed.text);
      } catch {
        // Backend unreachable — fall back to client-side extraction
        try {
          setState((prev) => ({ ...prev, progress: 50 }));
          const buffer = await file.arrayBuffer();
          setState((prev) => ({ ...prev, progress: 70 }));

          const { text, pageCount } = await extractTextFromPDF(buffer);
          setState((prev) => ({ ...prev, progress: 90 }));

          setState({
            status: 'done',
            fileName: file.name,
            pageCount,
            progress: 100,
            error: null,
          });

          onExtract(text);
        } catch (err) {
          setState({
            status: 'error',
            fileName: file.name,
            pageCount: 0,
            progress: 0,
            error: err instanceof Error ? err.message : 'Failed to process PDF.',
          });
        }
      }
    },
    [onExtract, onParsedContent],
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) processFile(file);
    },
    [processFile],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setIsDragOver(false);
  }, []);

  const handleInputChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) processFile(file);
    },
    [processFile],
  );

  const handleClear = useCallback(() => {
    setState({
      status: 'idle',
      fileName: null,
      pageCount: 0,
      progress: 0,
      error: null,
    });
    setParsedContent(null);
    setShowPreview(false);
    if (inputRef.current) {
      inputRef.current.value = '';
    }
  }, []);

  const handleUseContent = useCallback(
    (text: string, images: string[]) => {
      onExtract(text);
      if (onParsedContent && parsedContent) {
        onParsedContent({ ...parsedContent, text, images });
      }
      setShowPreview(false);
    },
    [onExtract, onParsedContent, parsedContent],
  );

  const handleClosePreview = useCallback(() => {
    setShowPreview(false);
  }, []);

  return (
    <div className="w-full">
      {state.status === 'idle' && (
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => inputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              inputRef.current?.click();
            }
          }}
          role="button"
          tabIndex={0}
          aria-label="Upload PDF file"
          className={cn(
            'flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-6 cursor-pointer transition-colors',
            isDragOver
              ? 'border-primary-500 bg-primary-50'
              : 'border-gray-300 bg-gray-50 hover:border-gray-400 hover:bg-gray-100',
          )}
        >
          <Upload className="h-8 w-8 text-gray-400" aria-hidden="true" />
          <p className="text-sm text-gray-600 text-center">
            <span className="font-medium text-primary-600">Click to upload</span>{' '}
            or drag and drop a PDF
          </p>
          <p className="text-xs text-gray-400">PDF files only</p>
        </div>
      )}

      {state.status === 'loading' && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
          <div className="flex items-center gap-3 mb-2">
            <FileText className="h-5 w-5 text-primary-500 shrink-0" aria-hidden="true" />
            <span className="text-sm text-gray-700 truncate">{state.fileName}</span>
          </div>
          <div className="w-full bg-gray-200 rounded-full h-1.5">
            <div
              className="bg-primary-500 h-1.5 rounded-full transition-all duration-300"
              style={{ width: `${state.progress}%` }}
              role="progressbar"
              aria-valuenow={state.progress}
              aria-valuemin={0}
              aria-valuemax={100}
            />
          </div>
          <p className="text-xs text-gray-400 mt-1">Extracting text...</p>
        </div>
      )}

      {state.status === 'done' && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <FileText className="h-5 w-5 text-green-600 shrink-0" aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-sm font-medium text-gray-800 truncate">{state.fileName}</p>
                <p className="text-xs text-gray-500">
                  {state.pageCount} page{state.pageCount !== 1 ? 's' : ''} extracted
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleClear}
              className="shrink-0 p-1 rounded hover:bg-green-100 transition-colors text-gray-400 hover:text-gray-600"
              aria-label="Remove uploaded file"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {state.status === 'error' && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3 min-w-0">
              <AlertCircle className="h-5 w-5 text-red-500 shrink-0" aria-hidden="true" />
              <div className="min-w-0">
                <p className="text-sm font-medium text-red-700 truncate">{state.fileName}</p>
                <p className="text-xs text-red-500">{state.error}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={handleClear}
              className="shrink-0 p-1 rounded hover:bg-red-100 transition-colors text-gray-400 hover:text-gray-600"
              aria-label="Dismiss error"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* PDF Content Preview (shown after backend parsing) */}
      {showPreview && parsedContent && (
        <div className="mt-3">
          <PDFContentPreview
            content={parsedContent}
            onUseContent={handleUseContent}
            onClose={handleClosePreview}
          />
        </div>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        onChange={handleInputChange}
        className="hidden"
        aria-hidden="true"
      />
    </div>
  );
});
