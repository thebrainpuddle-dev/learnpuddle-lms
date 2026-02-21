function normalizeDomain(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/\/.*$/, '')
    .replace(/\.$/, '');
}

function normalizeHost(value: string): string {
  return value.trim().toLowerCase().replace(/\.$/, '');
}

export function getPlatformDomain(): string {
  return normalizeDomain(process.env.REACT_APP_PLATFORM_DOMAIN || '');
}

export function isPlatformHost(hostname: string): boolean {
  const platformDomain = getPlatformDomain();
  if (!platformDomain) return false;

  const host = normalizeHost(hostname);
  return host === platformDomain || host === `www.${platformDomain}`;
}

export function isPlatformRequest(): boolean {
  if (typeof window === 'undefined') return false;
  return isPlatformHost(window.location.hostname);
}
