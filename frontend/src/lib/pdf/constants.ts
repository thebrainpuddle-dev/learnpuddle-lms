// src/lib/pdf/constants.ts
//
// PDF provider registry — defines available parsing backends.

import type { PDFProviderConfig } from './types';

export const PDF_PROVIDERS: Record<string, PDFProviderConfig> = {
  default: {
    id: 'default',
    name: 'Standard Parser',
    description: 'Built-in PDF text and image extraction',
    features: ['text', 'images'],
  },
  advanced: {
    id: 'advanced',
    name: 'Advanced Parser',
    description: 'OCR, formula, and table extraction',
    features: ['text', 'images', 'tables', 'formulas', 'layout-analysis'],
  },
};

export function getAllPDFProviders(): PDFProviderConfig[] {
  return Object.values(PDF_PROVIDERS);
}

export function getPDFProvider(id: string): PDFProviderConfig | undefined {
  return PDF_PROVIDERS[id];
}
