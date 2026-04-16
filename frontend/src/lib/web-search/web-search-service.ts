// src/lib/web-search/web-search-service.ts
//
// Client-side web search service. All actual search API calls are proxied
// through the Django backend — the frontend only sends queries and receives
// formatted results.

import api from '../../config/api';
import type { WebSearchResult } from './types';

const MAX_QUERY_LENGTH = 400;

interface BackendSearchResponse {
  answer?: string;
  sources: Array<{ title: string; url: string; content: string; score: number }>;
  query: string;
  response_time: number;
}

/**
 * Search the web via the backend proxy (teacher endpoint).
 */
export async function searchWeb(
  query: string,
  maxResults: number = 5,
): Promise<WebSearchResult> {
  const truncatedQuery = query.slice(0, MAX_QUERY_LENGTH);

  const response = await api.post<BackendSearchResponse>(
    '/v1/teacher/maic/web-search/',
    { query: truncatedQuery, max_results: maxResults },
  );

  return {
    answer: response.data.answer || '',
    sources: response.data.sources || [],
    query: response.data.query,
    responseTime: response.data.response_time,
  };
}

/**
 * Search the web via the student endpoint (may have guardrails).
 */
export async function searchWebStudent(
  query: string,
  maxResults: number = 5,
): Promise<WebSearchResult> {
  const truncatedQuery = query.slice(0, MAX_QUERY_LENGTH);

  const response = await api.post<BackendSearchResponse>(
    '/v1/student/maic/web-search/',
    { query: truncatedQuery, max_results: maxResults },
  );

  return {
    answer: response.data.answer || '',
    sources: response.data.sources || [],
    query: response.data.query,
    responseTime: response.data.response_time,
  };
}

/**
 * Format search results as markdown context for LLM prompts.
 */
export function formatSearchResultsAsContext(result: WebSearchResult): string {
  if (!result.answer && result.sources.length === 0) return '';

  const lines: string[] = [];

  if (result.answer) {
    lines.push(result.answer);
    lines.push('');
  }

  if (result.sources.length > 0) {
    lines.push('Sources:');
    for (const src of result.sources) {
      lines.push(`- [${src.title}](${src.url}): ${src.content.slice(0, 200)}`);
    }
  }

  return lines.join('\n');
}
