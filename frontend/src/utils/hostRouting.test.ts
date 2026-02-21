describe('hostRouting', () => {
  const originalDomain = process.env.REACT_APP_PLATFORM_DOMAIN;

  afterEach(() => {
    process.env.REACT_APP_PLATFORM_DOMAIN = originalDomain;
    jest.resetModules();
  });

  function loadModule() {
    return require('./hostRouting') as typeof import('./hostRouting');
  }

  it('matches exact platform domain', () => {
    process.env.REACT_APP_PLATFORM_DOMAIN = 'learnpuddle.com';
    const { isPlatformHost } = loadModule();

    expect(isPlatformHost('learnpuddle.com')).toBe(true);
  });

  it('matches www platform domain', () => {
    process.env.REACT_APP_PLATFORM_DOMAIN = 'learnpuddle.com';
    const { isPlatformHost } = loadModule();

    expect(isPlatformHost('www.learnpuddle.com')).toBe(true);
  });

  it('does not match tenant subdomains', () => {
    process.env.REACT_APP_PLATFORM_DOMAIN = 'learnpuddle.com';
    const { isPlatformHost } = loadModule();

    expect(isPlatformHost('school.learnpuddle.com')).toBe(false);
  });

  it('normalizes platform domain from URL format', () => {
    process.env.REACT_APP_PLATFORM_DOMAIN = 'https://learnpuddle.com/';
    const { isPlatformHost } = loadModule();

    expect(isPlatformHost('learnpuddle.com')).toBe(true);
  });
});
