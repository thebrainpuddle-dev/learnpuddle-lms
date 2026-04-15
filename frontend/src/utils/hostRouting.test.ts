import { vi, describe, it, expect, afterEach } from 'vitest';

describe('hostRouting', () => {
  const originalDomain = process.env.REACT_APP_PLATFORM_DOMAIN;

  afterEach(() => {
    process.env.REACT_APP_PLATFORM_DOMAIN = originalDomain;
    vi.resetModules();
  });

  async function loadModule() {
    return await import('./hostRouting');
  }

  it('matches exact platform domain', async () => {
    process.env.REACT_APP_PLATFORM_DOMAIN = 'learnpuddle.com';
    const { isPlatformHost } = await loadModule();

    expect(isPlatformHost('learnpuddle.com')).toBe(true);
  });

  it('matches www platform domain', async () => {
    process.env.REACT_APP_PLATFORM_DOMAIN = 'learnpuddle.com';
    const { isPlatformHost } = await loadModule();

    expect(isPlatformHost('www.learnpuddle.com')).toBe(true);
  });

  it('does not match tenant subdomains', async () => {
    process.env.REACT_APP_PLATFORM_DOMAIN = 'learnpuddle.com';
    const { isPlatformHost } = await loadModule();

    expect(isPlatformHost('school.learnpuddle.com')).toBe(false);
  });

  it('normalizes platform domain from URL format', async () => {
    process.env.REACT_APP_PLATFORM_DOMAIN = 'https://learnpuddle.com/';
    const { isPlatformHost } = await loadModule();

    expect(isPlatformHost('learnpuddle.com')).toBe(true);
  });
});
