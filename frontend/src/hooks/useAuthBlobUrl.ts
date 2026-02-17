// src/hooks/useAuthBlobUrl.ts
// Fetches a protected media URL with JWT auth and returns a blob: URL
// for embedding in <iframe>, <img>, etc. where Authorization headers
// cannot be attached natively.

import { useEffect, useState } from 'react';

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
        const token = sessionStorage.getItem('access_token');
        const headers: HeadersInit = {};
        if (token) headers['Authorization'] = `Bearer ${token}`;

        const res = await fetch(protectedUrl, { headers });
        if (!res.ok) {
          console.warn(`useAuthBlobUrl: fetch failed ${res.status} for ${protectedUrl}`);
          return;
        }
        const blob = await res.blob();
        if (revoked) return;
        objectUrl = URL.createObjectURL(blob);
        setBlobUrl(objectUrl);
      } catch (err) {
        console.warn('useAuthBlobUrl: fetch error', err);
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
