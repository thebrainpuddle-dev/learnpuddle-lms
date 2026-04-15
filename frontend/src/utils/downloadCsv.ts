// src/utils/downloadCsv.ts
//
// Trigger an authenticated CSV download via the API.

import api from '../config/api';

export async function downloadCsv(url: string, params?: Record<string, string>) {
  const res = await api.get(url, {
    params,
    responseType: 'blob',
  });

  // Extract filename from Content-Disposition header or use fallback
  const disposition = res.headers['content-disposition'] || '';
  const match = disposition.match(/filename="?([^";\n]+)"?/);
  const filename = match?.[1] || 'attendance.csv';

  const blob = new Blob([res.data], { type: 'text/csv' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
}
