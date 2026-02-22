export function getBookDemoUrl(): string {
  const configured = (process.env.REACT_APP_BOOK_DEMO_URL || '').trim();
  if (configured) return configured;
  // Cal.com is an open-source scheduling platform (Calendly-style).
  return 'https://cal.com/';
}

export function isExternalHttpUrl(url: string): boolean {
  return /^https?:\/\//i.test(url);
}
