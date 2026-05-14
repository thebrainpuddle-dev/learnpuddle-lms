import { describe, expect, test, vi, afterEach } from 'vitest';

import api from '../../config/api';
import { parsePDF, parsePDFStudent } from './pdf-service';

afterEach(() => {
  vi.restoreAllMocks();
});

function makePdfResponse() {
  return {
    document_id: 'doc-1',
    state: 'done',
    latency_ms: 1234,
    document: {
      document_id: 'doc-1',
      title: 'Fractions',
      total_pages: 2,
      provider: 'mineru',
      latency_ms: 1234,
      cost_usd_estimate: null,
      sections: [
        {
          section_id: 's-1',
          title: 'Numerators',
          level: 1,
          text: 'A numerator counts selected parts.',
          page_start: 1,
          page_end: 1,
        },
      ],
      pages: [
        { page_number: 1, text: 'page fallback' },
      ],
      figures: [
        {
          figure_id: 'fig-1',
          caption: 'Fraction bar',
          image_url: 'https://cdn.example/fig-1.png',
          page: 2,
        },
      ],
    },
  };
}

describe('pdf-service v2 parser', () => {
  test('parsePDF posts the file to the MAIC v2 PDF route and maps structured output', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: makePdfResponse(),
    } as never);

    const file = new File(['%PDF-1.4'], 'fractions.pdf', { type: 'application/pdf' });
    const parsed = await parsePDF(file);

    expect(post).toHaveBeenCalledWith('/maic/v2/pdf/parse/', expect.any(FormData));
    expect(parsed.text).toContain('Numerators');
    expect(parsed.text).toContain('A numerator counts selected parts.');
    expect(parsed.images).toEqual(['https://cdn.example/fig-1.png']);
    expect(parsed.metadata?.pageCount).toBe(2);
    expect(parsed.metadata?.parser).toBe('mineru');
    expect(parsed.metadata?.documentId).toBe('doc-1');
    expect(parsed.metadata?.pdfImages?.[0]).toMatchObject({
      id: 'fig-1',
      pageNumber: 2,
      description: 'Fraction bar',
    });
  });

  test('parsePDFStudent uses the same tenant-gated v2 route', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValueOnce({
      data: makePdfResponse(),
    } as never);

    const file = new File(['%PDF-1.4'], 'student.pdf', { type: 'application/pdf' });
    await parsePDFStudent(file);

    expect(post).toHaveBeenCalledWith('/maic/v2/pdf/parse/', expect.any(FormData));
  });
});
