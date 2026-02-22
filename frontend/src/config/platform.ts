const DEFAULT_CAL_LINK = 'learnpuddle-rj4uat/30min';

export function getBookDemoUrl(): string {
  const configured = (process.env.REACT_APP_BOOK_DEMO_URL || '').trim();
  if (configured) return configured;
  return `https://cal.com/${getBookDemoCalLink()}`;
}

export function getBookDemoCalLink(): string {
  const configured = (process.env.REACT_APP_BOOK_DEMO_CAL_LINK || '').trim();
  return configured || DEFAULT_CAL_LINK;
}

export function useInlineBookDemo(): boolean {
  const mode = (process.env.REACT_APP_BOOK_DEMO_MODE || 'cal_inline').trim().toLowerCase();
  return mode !== 'external';
}

export function isExternalHttpUrl(url: string): boolean {
  return /^https?:\/\//i.test(url);
}
