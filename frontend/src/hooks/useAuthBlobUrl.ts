// src/hooks/useAuthBlobUrl.ts
// Fetches a protected media URL with JWT auth and returns a blob: URL
// for embedding in <iframe>, <img>, etc. where Authorization headers
// cannot be attached natively.

import { useEffect, useState } from 'react';
import { getAccessToken } from '../utils/authSession';

function resolveTenantSubdomain(): string | null {
  if (typeof window === 'undefined') return null;
  const hostname = window.location.hostname;
  if (
    hostname !== 'localhost' &&
    hostname !== '127.0.0.1' &&
    !hostname.endsWith('.localhost')
  ) {
    return null;
  }
  return (
    (hostname.endsWith('.localhost') ? hostname.replace('.localhost', '') : null) ||
    sessionStorage.getItem('tenant_subdomain') ||
    localStorage.getItem('tenant_subdomain')
  );
}

export function useAuthBlobUrl(protectedUrl: string | null | undefined): string | null {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!protectedUrl) {
      setBlobUrl(null);
      return;
    }

    let revoked = false;
    let objectUrl: string | null = null;

    const fetchBlob = async () => {
      try {
        const token = getAccessToken();
        const headers: HeadersInit = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;
        const tenantSubdomain = resolveTenantSubdomain();
        if (tenantSubdomain) headers['X-Tenant-Subdomain'] = tenantSubdomain;

        const res = await fetch(protectedUrl, { headers });
        if (!res.ok || res.status === 204) {
          return;
        }
        const blob = await res.blob();
        if (revoked || blob.size === 0) return;
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      } catch {
        // Fetch failed silently; blob URL remains null
      }
    };

    fetchBlob();

    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      setBlobUrl(null);
    };
  }, [protectedUrl]);

  return blobUrl;
}
