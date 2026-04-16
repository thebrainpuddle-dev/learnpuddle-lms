// src/components/maic/WebSearchPanel.tsx
//
// UI panel for web search integration in the MAIC classroom creation flow.
// Displays search input, results with source cards, and an "insert as context"
// action so search findings can be fed into the LLM generation pipeline.

import React, { useState, useCallback } from 'react';
import { Search, ExternalLink, RefreshCw, Globe, AlertCircle, Loader2, ChevronDown, ChevronUp } from 'lucide-react';
import { useWebSearch } from '../../hooks/useWebSearch';
import { formatSearchResultsAsContext } from '../../lib/web-search/web-search-service';
import { cn } from '../../lib/utils';

interface WebSearchPanelProps {
  onInsertContext: (context: string) => void;
  role: 'teacher' | 'student';
}

export const WebSearchPanel: React.FC<WebSearchPanelProps> = ({ onInsertContext, role }) => {
  const [query, setQuery] = useState('');
  const [expandedSource, setExpandedSource] = useState<number | null>(null);
  const { searching, error, results, search, reset } = useWebSearch(role);

  const handleSearch = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (!query.trim() || searching) return;
      await search(query.trim());
    },
    [query, searching, search],
  );

  const handleInsertContext = useCallback(() => {
    if (!results) return;
    const context = formatSearchResultsAsContext(results);
    if (context) {
      onInsertContext(context);
    }
  }, [results, onInsertContext]);

  const handleRetry = useCallback(() => {
    if (query.trim()) {
      search(query.trim());
    }
  }, [query, search]);

  const handleClear = useCallback(() => {
    setQuery('');
    reset();
    setExpandedSource(null);
  }, [reset]);

  const toggleSource = useCallback((index: number) => {
    setExpandedSource((prev) => (prev === index ? null : index));
  }, []);

  return (
    <div className="rounded-lg border border-gray-200 bg-white">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
        <Globe className="h-4 w-4 text-indigo-500" aria-hidden="true" />
        <h3 className="text-sm font-medium text-gray-800">Web Research</h3>
      </div>

      {/* Search form */}
      <form onSubmit={handleSearch} className="p-4 pb-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" aria-hidden="true" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search the web for context..."
              className="w-full rounded-lg border border-gray-300 pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              disabled={searching}
            />
          </div>
          <button
            type="submit"
            disabled={!query.trim() || searching}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-sm font-medium transition-colors',
              'bg-indigo-600 text-white hover:bg-indigo-700',
              'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2',
              'disabled:opacity-50 disabled:cursor-not-allowed',
            )}
          >
            {searching ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            Search
          </button>
        </div>
      </form>

      {/* Loading state */}
      {searching && (
        <div className="px-4 pb-4">
          <div className="flex items-center gap-3 rounded-lg bg-indigo-50 p-3">
            <Loader2 className="h-4 w-4 text-indigo-500 animate-spin shrink-0" />
            <p className="text-sm text-indigo-700">Searching the web...</p>
          </div>
        </div>
      )}

      {/* Error state */}
      {error && !searching && (
        <div className="px-4 pb-4">
          <div className="rounded-lg bg-red-50 border border-red-200 p-3 flex items-start gap-2">
            <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-red-700">{error}</p>
              <button
                type="button"
                onClick={handleRetry}
                className="inline-flex items-center gap-1 mt-1.5 text-xs text-red-500 hover:text-red-700 transition-colors"
              >
                <RefreshCw className="h-3 w-3" />
                Retry
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Results */}
      {results && !searching && (
        <div className="px-4 pb-4 space-y-3">
          {/* Answer summary */}
          {results.answer && (
            <div className="rounded-lg bg-gray-50 p-3">
              <p className="text-sm text-gray-700 leading-relaxed">{results.answer}</p>
            </div>
          )}

          {/* Source cards */}
          {results.sources.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                Sources ({results.sources.length})
              </p>
              {results.sources.map((source, idx) => (
                <div
                  key={`${source.url}-${idx}`}
                  className="rounded-lg border border-gray-100 bg-gray-50/50 overflow-hidden"
                >
                  <button
                    type="button"
                    onClick={() => toggleSource(idx)}
                    className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-gray-100 transition-colors"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-gray-800 truncate">
                        {source.title}
                      </p>
                      <p className="text-xs text-gray-400 truncate">{source.url}</p>
                    </div>
                    <span
                      className={cn(
                        'shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium',
                        source.score >= 0.8 && 'bg-green-100 text-green-700',
                        source.score >= 0.5 && source.score < 0.8 && 'bg-yellow-100 text-yellow-700',
                        source.score < 0.5 && 'bg-gray-100 text-gray-600',
                      )}
                    >
                      {Math.round(source.score * 100)}%
                    </span>
                    {expandedSource === idx ? (
                      <ChevronUp className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                    ) : (
                      <ChevronDown className="h-3.5 w-3.5 text-gray-400 shrink-0" />
                    )}
                  </button>

                  {expandedSource === idx && (
                    <div className="px-3 pb-3 border-t border-gray-100">
                      <p className="text-xs text-gray-600 mt-2 leading-relaxed">
                        {source.content.slice(0, 300)}
                        {source.content.length > 300 && '...'}
                      </p>
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 mt-2 text-xs text-indigo-600 hover:text-indigo-800 transition-colors"
                      >
                        <ExternalLink className="h-3 w-3" />
                        Open source
                      </a>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Response time */}
          {results.responseTime > 0 && (
            <p className="text-[10px] text-gray-400">
              Search completed in {(results.responseTime / 1000).toFixed(1)}s
            </p>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              onClick={handleInsertContext}
              disabled={!results.answer && results.sources.length === 0}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors',
                'bg-indigo-600 text-white hover:bg-indigo-700',
                'focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1',
                'disabled:opacity-50 disabled:cursor-not-allowed',
              )}
            >
              Insert as context
            </button>
            <button
              type="button"
              onClick={handleClear}
              className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {/* Empty state — no results yet */}
      {!results && !searching && !error && (
        <div className="px-4 pb-4">
          <p className="text-xs text-gray-400 text-center">
            Search the web for additional context to enrich your classroom content.
          </p>
        </div>
      )}
    </div>
  );
};
