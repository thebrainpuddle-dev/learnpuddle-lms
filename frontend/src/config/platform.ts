export function getBookDemoUrl(): string {
  const configured = (process.env.REACT_APP_BOOK_DEMO_URL || '').trim();
  if (configured) return configured;
  return 'mailto:support@learnpuddle.com?subject=Book%20a%20LearnPuddle%20Demo';
}

export function isExternalHttpUrl(url: string): boolean {
  return /^https?:\/\//i.test(url);
}
