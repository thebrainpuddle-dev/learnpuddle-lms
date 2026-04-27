// src/components/search/SearchResultList.tsx
// Shared list container for search results.

import React from 'react';
import type { SearchResult } from '../../services/searchService';
import { SearchResultItem } from './SearchResultItem';

interface SearchResultListProps {
  results: SearchResult[];
  onResultClick: (result: SearchResult) => void;
  focusedIndex?: number;
  listId?: string;
  /** Prefix for result item IDs to support aria-activedescendant */
  itemIdPrefix?: string;
}

export const SearchResultList: React.FC<SearchResultListProps> = ({
  results,
  onResultClick,
  focusedIndex = -1,
  listId,
  itemIdPrefix = 'search-result',
}) => {
  if (results.length === 0) {
    return null;
  }

  return (
    <ul
      id={listId}
      role="listbox"
      aria-label="Search results"
      className="divide-y divide-slate-100"
    >
      {results.map((result, idx) => (
        <li key={`${result.source_type}-${result.source_id}-${result.chunk_index}`} role="presentation">
          <SearchResultItem
            id={`${itemIdPrefix}-${idx}`}
            result={result}
            onClick={onResultClick}
            isFocused={idx === focusedIndex}
          />
        </li>
      ))}
    </ul>
  );
};

export default SearchResultList;
