// src/utils/samlUrls.test.ts
//
// Tests for buildSpUrls — verifies that SP URLs adapt to REACT_APP_PLATFORM_DOMAIN
// so staging / dev admins see environment-correct ACS / SLS / Metadata URLs.

import { vi, describe, it, expect, afterEach } from 'vitest';

describe('buildSpUrls', () => {
  const originalDomain = process.env.REACT_APP_PLATFORM_DOMAIN;

  afterEach(() => {
    process.env.REACT_APP_PLATFORM_DOMAIN = originalDomain;
    vi.resetModules();
  });

  async function load() {
    return await import('./samlUrls');
  }

  it('uses https and learnpuddle.com when no env var is set', async () => {
    delete process.env.REACT_APP_PLATFORM_DOMAIN;
    const { buildSpUrls } = await load();
    const urls = buildSpUrls('acme', '');
    expect(urls.acsUrl).toBe('https://acme.learnpuddle.com/api/v1/auth/saml/acme/acs/');
    expect(urls.slsUrl).toBe('https://acme.learnpuddle.com/api/v1/auth/saml/acme/sls/');
    expect(urls.metadataUrl).toBe('https://acme.learnpuddle.com/api/v1/auth/saml/acme/metadata/');
  });

  it('uses https for a custom production domain', async () => {
    process.env.REACT_APP_PLATFORM_DOMAIN = 'myedtech.io';
    const { buildSpUrls } = await load();
    const urls = buildSpUrls('demo', '');
    expect(urls.acsUrl).toContain('https://demo.myedtech.io');
  });

  it('uses http for localhost (port is stripped by normalizeDomain)', async () => {
    // normalizeDomain strips ports, so localhost:3000 → localhost
    process.env.REACT_APP_PLATFORM_DOMAIN = 'localhost:3000';
    const { buildSpUrls } = await load();
    const urls = buildSpUrls('demo', '');
    expect(urls.acsUrl).toContain('http://demo.localhost');
    expect(urls.acsUrl).not.toContain('https://');
  });

  it('uses the saved spEntityId when provided', async () => {
    process.env.REACT_APP_PLATFORM_DOMAIN = 'learnpuddle.com';
    const { buildSpUrls } = await load();
    const urls = buildSpUrls('acme', 'urn:existing-sp-entity');
    expect(urls.entityId).toBe('urn:existing-sp-entity');
  });

  it('falls back to saml-sp:<subdomain> when spEntityId is empty', async () => {
    process.env.REACT_APP_PLATFORM_DOMAIN = 'learnpuddle.com';
    const { buildSpUrls } = await load();
    const urls = buildSpUrls('acme', '');
    expect(urls.entityId).toBe('saml-sp:acme');
  });

  it('changes all URL bases when domain env var is flipped', async () => {
    process.env.REACT_APP_PLATFORM_DOMAIN = 'staging.learnpuddle.com';
    const { buildSpUrls } = await load();
    const urls = buildSpUrls('school', '');
    expect(urls.acsUrl).toContain('school.staging.learnpuddle.com');
    expect(urls.slsUrl).toContain('school.staging.learnpuddle.com');
    expect(urls.metadataUrl).toContain('school.staging.learnpuddle.com');
  });
});
