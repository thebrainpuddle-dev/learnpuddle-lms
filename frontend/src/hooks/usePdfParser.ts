// src/hooks/usePdfParser.ts
//
// React hook for PDF parsing with loading, progress, and error state.
// Delegates to the backend via pdf-service; supports teacher and student roles.

import { useState, useCallback } from 'react';
import type { ParsedPdfContent } from '../lib/pdf/types';
import { parsePDF, parsePDFStudent } from '../lib/pdf/pdf-service';

interface UsePdfParserReturn {
  /** Whether a parse operation is in progress */
  parsing: boolean;
  /** Estimated progress (0–100) */
  progress: number;
  /** Error message if parsing failed */
  error: string | null;
  /** Parsed PDF content on success */
  result: ParsedPdfContent | null;
  /** Trigger parsing of a PDF file */
  parsePdf: (file: File) => Promise<void>;
  /** Reset state for a new upload */
  reset: () => void;
}

export function usePdfParser(
  role: 'teacher' | 'student' = 'teacher',
): UsePdfParserReturn {
  const [parsing, setParsing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ParsedPdfContent | null>(null);

  const parsePdf = useCallback(
    async (file: File) => {
      setParsing(true);
      setError(null);
      setProgress(10);

      try {
        setProgress(30);
        const parsed =
          role === 'student'
            ? await parsePDFStudent(file)
            : await parsePDF(file);
        setResult(parsed);
        setProgress(100);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : 'PDF parsing failed';
        setError(message);
      } finally {
        setParsing(false);
      }
    },
    [role],
  );

  const reset = useCallback(() => {
    setResult(null);
    setError(null);
    setProgress(0);
  }, []);

  return { parsing, progress, error, result, parsePdf, reset };
}
