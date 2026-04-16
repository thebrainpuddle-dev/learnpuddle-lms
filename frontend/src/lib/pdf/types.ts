// src/lib/pdf/types.ts
//
// PDF parsing type definitions adapted from upstream OpenMAIC patterns.

export type PDFProviderId = 'default' | 'advanced';

export interface PDFProviderConfig {
  id: PDFProviderId;
  name: string;
  description: string;
  features: string[];
}

export interface PDFParserConfig {
  providerId: PDFProviderId;
}

export interface ParsedPdfContent {
  text: string;
  images: string[]; // base64 data URLs
  tables?: Array<{ page: number; data: string[][]; caption?: string }>;
  formulas?: Array<{ page: number; latex: string }>;
  metadata?: {
    fileName?: string;
    fileSize?: number;
    pageCount: number;
    parser?: string;
    processingTime?: number;
    imageMapping?: Record<string, string>;
    pdfImages?: Array<{
      id: string;
      src: string;
      pageNumber: number;
      description?: string;
      width?: number;
      height?: number;
    }>;
    [key: string]: unknown;
  };
}

export interface ParsePdfRequest {
  pdf: File;
}

export interface ParsePdfResponse {
  success: boolean;
  data?: ParsedPdfContent;
  error?: string;
}
