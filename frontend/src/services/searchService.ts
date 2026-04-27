// src/services/searchService.ts
// Semantic search service — calls TASK-057 backend endpoint.

import api from '../config/api';

// ─── Types ───────────────────────────────────────────────────────────────────

/** Possible source types returned by the search API. */
export type SearchSourceType = 'content' | 'module' | 'course' | 'transcript';

/** Context object attached to each result for navigation. */
export interface SearchResultContext {
  course_id: string | null;
  course_title: string | null;
  module_id: string | null;
  content_id: string | null;
}

/** A single semantic search hit. */
export interface SearchResult {
  source_type: SearchSourceType;
  source_id: string;
  chunk_index: number;
  score: number; // 0..1 cosine similarity
  snippet: string;
  context: SearchResultContext;
}

/** Response shape from POST /api/v1/search/semantic/ */
export interface SearchResponse {
  results: SearchResult[];
  count: number;
  top_k: number;
  query: string;
}

/** Options for the search() call. */
export interface SearchOptions {
  courseId?: string;
  topK?: number;
}

// ─── Service ─────────────────────────────────────────────────────────────────

/**
 * Calls the semantic search endpoint.
 *
 * Backend contract (TASK-057):
 *   POST /api/v1/search/semantic/
 *   Body: { query: string, top_k?: number, course_id?: string }
 *   Response: { results: SearchResult[], count: number, top_k: number, query: string }
 */
export async function search(
  query: string,
  options: SearchOptions = {},
): Promise<SearchResponse> {
  const body: Record<string, unknown> = { query };
  if (options.topK !== undefined) {
    body.top_k = options.topK;
  }
  if (options.courseId) {
    body.course_id = options.courseId;
  }
  const response = await api.post<SearchResponse>('/v1/search/semantic/', body);
  return response.data;
}

export const searchService = { search };
export default searchService;
