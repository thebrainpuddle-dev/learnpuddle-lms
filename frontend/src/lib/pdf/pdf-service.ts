// src/lib/pdf/pdf-service.ts
//
// Client-side PDF service that delegates heavy parsing to the Django backend.
// The frontend only handles file upload via FormData — no server-side imports.

import api from '../../config/api';
import type { ParsedPdfContent, PDFParserConfig } from './types';

interface BackendPdfFigure {
  figure_id: string;
  caption: string;
  image_url: string | null;
  page: number;
}

interface BackendPdfPage {
  page_number: number;
  text: string;
}

interface BackendPdfSection {
  section_id: string;
  title: string;
  level: number;
  text: string;
  page_start: number;
  page_end: number;
}

interface BackendPdfDocument {
  document_id: string;
  title: string;
  total_pages: number;
  sections: BackendPdfSection[];
  figures: BackendPdfFigure[];
  pages: BackendPdfPage[];
  provider: string;
  latency_ms: number;
  cost_usd_estimate: number | null;
}

interface BackendPdfResponse {
  document_id: string;
  document: BackendPdfDocument;
  state: string;
  latency_ms: number;
}

function documentToText(document: BackendPdfDocument): string {
  const sectionText = document.sections
    .map((section) => [section.title, section.text].filter(Boolean).join('\n'))
    .filter(Boolean)
    .join('\n\n');

  if (sectionText.trim()) return sectionText.trim();

  return document.pages
    .map((page) => page.text)
    .filter(Boolean)
    .join('\n\n')
    .trim();
}

function mapBackendPdfResponse(response: BackendPdfResponse): ParsedPdfContent {
  const document = response.document;
  const images = document.figures
    .map((figure) => figure.image_url)
    .filter((url): url is string => Boolean(url));

  return {
    text: documentToText(document),
    images,
    metadata: {
      fileName: document.title || response.document_id,
      pageCount: document.total_pages,
      parser: document.provider,
      processingTime: response.latency_ms,
      documentId: response.document_id,
      state: response.state,
      pdfImages: document.figures.map((figure) => ({
        id: figure.figure_id,
        src: figure.image_url || '',
        pageNumber: figure.page,
        description: figure.caption,
      })),
    },
  };
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
    '/maic/v2/pdf/parse/',
    formData,
  );

  return mapBackendPdfResponse(response.data);
}

/**
 * Parse a PDF for students (with content guardrails applied server-side).
 */
export async function parsePDFStudent(file: File): Promise<ParsedPdfContent> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await api.post<BackendPdfResponse>(
    '/maic/v2/pdf/parse/',
    formData,
  );

  return mapBackendPdfResponse(response.data);
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
