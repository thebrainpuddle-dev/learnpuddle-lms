// src/utils/samlUrls.ts
//
// Builds the SP (Service Provider) URL set that an IdP admin needs in order to
// configure LearnPuddle as an SP in their identity provider.
//
// The base domain is resolved from REACT_APP_PLATFORM_DOMAIN so that admins on
// staging / dev environments see environment-correct URLs rather than always
// seeing URLs that point at production.

import { getPlatformDomain } from './hostRouting';

export interface SpUrls {
  entityId: string;
  acsUrl: string;
  slsUrl: string;
  metadataUrl: string;
}

/**
 * Build the SP URLs the IdP admin needs to configure LearnPuddle as an SP.
 *
 * @param subdomain   - Tenant subdomain (e.g. "acme")
 * @param spEntityId  - Existing SP Entity ID from the saved config, if any.
 */
export function buildSpUrls(subdomain: string, spEntityId: string): SpUrls {
  const platformDomain = getPlatformDomain() || 'learnpuddle.com';
  const scheme = platformDomain.includes('localhost') ? 'http' : 'https';
  const base = `${scheme}://${subdomain}.${platformDomain}`;
  return {
    entityId: spEntityId || `saml-sp:${subdomain}`,
    acsUrl: `${base}/api/v1/auth/saml/${subdomain}/acs/`,
    slsUrl: `${base}/api/v1/auth/saml/${subdomain}/sls/`,
    metadataUrl: `${base}/api/v1/auth/saml/${subdomain}/metadata/`,
  };
}
