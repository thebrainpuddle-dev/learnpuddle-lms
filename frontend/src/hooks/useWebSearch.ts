// src/hooks/useWebSearch.ts
//
// React hook for web search with loading and error state.
// Delegates to the backend via web-search-service; supports teacher and student roles.

import { useState, useCallback } from 'react';
import type { WebSearchResult } from '../lib/web-search/types';
import { searchWeb, searchWebStudent } from '../lib/web-search/web-search-service';

interface UseWebSearchReturn {
  /** Whether a search is in progress */
  searching: boolean;
  /** Error message if search failed */
  error: string | null;
  /** Search results on success */
  results: WebSearchResult | null;
  /** Execute a web search */
  search: (query: string, maxResults?: number) => Promise<WebSearchResult | null>;
  /** Reset state */
  reset: () => void;
}

export function useWebSearch(
  role: 'teacher' | 'student' = 'teacher',
): UseWebSearchReturn {
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<WebSearchResult | null>(null);

  const search = useCallback(
    async (query: string, maxResults?: number): Promise<WebSearchResult | null> => {
      setSearching(true);
      setError(null);

      try {
        const result =
          role === 'student'
            ? await searchWebStudent(query, maxResults)
            : await searchWeb(query, maxResults);
        setResults(result);
        return result;
      } catch (err) {
        const msg = err instanceof Error ? err.message : 'Search failed';
        setError(msg);
        return null;
      } finally {
        setSearching(false);
      }
    },
    [role],
  );

  const reset = useCallback(() => {
    setResults(null);
    setError(null);
  }, []);

  return { searching, error, results, search, reset };
}
