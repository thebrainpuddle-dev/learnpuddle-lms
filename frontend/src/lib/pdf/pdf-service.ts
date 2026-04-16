// src/lib/pdf/pdf-service.ts
//
// Client-side PDF service that delegates heavy parsing to the Django backend.
// The frontend only handles file upload via FormData — no server-side imports.

import api from '../../config/api';
import type { ParsedPdfContent, PDFParserConfig } from './types';

interface BackendPdfResponse {
  text: string;
  images: string[];
  metadata: Record<string, unknown>;
  tables?: Array<{ page: number; data: string[][]; caption?: string }>;
  formulas?: Array<{ page: number; latex: string }>;
}

/**
 * Parse a PDF by uploading it to the Django backend (teacher endpoint).
 * Supports optional provider selection for advanced parsing features.
 */
export async function parsePDF(
  file: File,
  config?: PDFParserConfig,
): Promise<ParsedPdfContent> {
  const formData = new FormData();
  formData.append('file', file);
  if (config?.providerId) {
    formData.append('provider', config.providerId);
  }

  const response = await api.post<BackendPdfResponse>(
    '/v1/teacher/maic/parse-pdf/',
    formData,
  );

  return {
    text: response.data.text,
    images: response.data.images || [],
    tables: response.data.tables,
    formulas: response.data.formulas,
    metadata: response.data.metadata as ParsedPdfContent['metadata'],
  };
}

/**
 * Parse a PDF for students (with content guardrails applied server-side).
 */
export async function parsePDFStudent(file: File): Promise<ParsedPdfContent> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post<BackendPdfResponse>(
    '/v1/student/maic/parse-pdf/',
    formData,
  );

  return {
    text: response.data.text,
    images: response.data.images || [],
    tables: response.data.tables,
    formulas: response.data.formulas,
    metadata: response.data.metadata as ParsedPdfContent['metadata'],
  };
}

/**
 * Lightweight client-side fallback — attempts to read a PDF file
 * but cannot actually parse PDF binary format without heavy libraries.
 * Returns an empty string; real parsing should always go through the backend.
 */
export async function extractPdfTextClient(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      // Cannot parse PDF binary client-side without pdfjs-dist or similar.
      // Return empty string and let the backend handle actual extraction.
      resolve('');
    };
    reader.onerror = () => reject(new Error('Failed to read PDF file'));
    reader.readAsArrayBuffer(file);
  });
}
