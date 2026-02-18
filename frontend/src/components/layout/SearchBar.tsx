// src/components/layout/SearchBar.tsx

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  MagnifyingGlassIcon,
  XMarkIcon,
  DocumentTextIcon,
  AcademicCapIcon,
  ArrowRightIcon,
} from '@heroicons/react/24/outline';
import api from '../../config/api';

interface SearchResult {
  id: string;
  title: string;
  type: 'course' | 'content';
  description?: string;
  content_type?: string;
  course_id?: string;
  course_title?: string;
  module_title?: string;
  is_published?: boolean;
}

interface SearchResponse {
  query: string;
  courses: SearchResult[];
  content: SearchResult[];
}

const fetchSearchResults = async (query: string): Promise<SearchResponse> => {
  if (query.length < 2) {
    return { query, courses: [], content: [] };
  }
  const response = await api.get('/courses/search/', { params: { q: query } });
  return response.data;
};

// Debounce hook
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);
  useEffect(() => {
    const handler = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(handler);
  }, [value, delay]);
  return debouncedValue;
}

interface SearchBarProps {
  className?: string;
  isAdmin?: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({ className = '', isAdmin = false }) => {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  
  const debouncedQuery = useDebounce(query, 300);
  
  const { data: results, isLoading } = useQuery({
    queryKey: ['globalSearch', debouncedQuery],
    queryFn: () => fetchSearchResults(debouncedQuery),
    enabled: debouncedQuery.length >= 2,
  });
  
  // Combine results for keyboard navigation
  const allResults = [
    ...(results?.courses || []),
    ...(results?.content || []),
  ];
  
  // Handle click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);
  
  // Handle keyboard navigation
  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (!isOpen || allResults.length === 0) return;
    
    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, allResults.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, -1));
        break;
      case 'Enter':
        e.preventDefault();
        if (selectedIndex >= 0 && selectedIndex < allResults.length) {
          handleResultClick(allResults[selectedIndex]);
        }
        break;
      case 'Escape':
        setIsOpen(false);
        inputRef.current?.blur();
        break;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, allResults, selectedIndex]);
  
  const handleResultClick = (result: SearchResult) => {
    setIsOpen(false);
    setQuery('');
    
    if (result.type === 'course') {
      if (isAdmin) {
        navigate(`/admin/courses/${result.id}/edit`);
      } else {
        navigate(`/teacher/courses/${result.id}`);
      }
    } else if (result.type === 'content' && result.course_id) {
      if (isAdmin) {
        navigate(`/admin/courses/${result.course_id}/edit`);
      } else {
        navigate(`/teacher/courses/${result.course_id}`);
      }
    }
  };
  
  const clearSearch = () => {
    setQuery('');
    setSelectedIndex(-1);
    inputRef.current?.focus();
  };
  
  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {/* Search Input */}
      <div className="relative">
        <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
            setSelectedIndex(-1);
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search courses, content..."
          className="w-full pl-10 pr-10 py-2 bg-gray-100 border border-transparent rounded-lg text-sm focus:bg-white focus:border-gray-300 focus:ring-2 focus:ring-emerald-500 transition-all"
        />
        {query && (
          <button
            onClick={clearSearch}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        )}
      </div>
      
      {/* Results Dropdown */}
      {isOpen && query.length >= 2 && (
        <div className="absolute top-full left-0 right-0 mt-2 bg-white rounded-xl shadow-lg border border-gray-200 overflow-hidden z-50 max-h-96 overflow-y-auto">
          {isLoading ? (
            <div className="px-4 py-6 text-center text-gray-500">
              <div className="animate-spin h-6 w-6 border-2 border-emerald-600 border-t-transparent rounded-full mx-auto mb-2" />
              Searching...
            </div>
          ) : allResults.length === 0 ? (
            <div className="px-4 py-6 text-center text-gray-500">
              <MagnifyingGlassIcon className="h-8 w-8 mx-auto mb-2 text-gray-300" />
              No results found for "{query}"
            </div>
          ) : (
            <>
              {/* Courses Section */}
              {results?.courses && results.courses.length > 0 && (
                <div>
                  <div className="px-4 py-2 bg-gray-50 text-xs font-semibold text-gray-500 uppercase tracking-wider">
                    Courses
                  </div>
                  {results.courses.map((result, index) => (
                    <button
                      key={`course-${result.id}`}
                      onClick={() => handleResultClick(result)}
                      className={`w-full px-4 py-3 flex items-start gap-3 text-left hover:bg-gray-50 transition-colors ${
                        selectedIndex === index ? 'bg-emerald-50' : ''
                      }`}
                    >
                      <div className="flex-shrink-0 p-2 bg-emerald-100 rounded-lg">
                        <AcademicCapIcon className="h-5 w-5 text-emerald-600" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-gray-900 truncate">{result.title}</span>
                          {!result.is_published && (
                            <span className="px-1.5 py-0.5 text-xs bg-yellow-100 text-yellow-700 rounded">Draft</span>
                          )}
                        </div>
                        {result.description && (
                          <p className="text-sm text-gray-500 truncate">{result.description}</p>
                        )}
                      </div>
                      <ArrowRightIcon className="h-4 w-4 text-gray-400 flex-shrink-0" />
                    </button>
                  ))}
                </div>
              )}
              
              {/* Content Section */}
              {results?.content && results.content.length > 0 && (
                <div>
                  <div className="px-4 py-2 bg-gray-50 text-xs font-semibold text-gray-500 uppercase tracking-wider border-t border-gray-100">
                    Content
                  </div>
                  {results.content.map((result, index) => {
                    const globalIndex = (results?.courses?.length || 0) + index;
                    return (
                      <button
                        key={`content-${result.id}`}
                        onClick={() => handleResultClick(result)}
                        className={`w-full px-4 py-3 flex items-start gap-3 text-left hover:bg-gray-50 transition-colors ${
                          selectedIndex === globalIndex ? 'bg-emerald-50' : ''
                        }`}
                      >
                        <div className="flex-shrink-0 p-2 bg-blue-100 rounded-lg">
                          <DocumentTextIcon className="h-5 w-5 text-blue-600" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="font-medium text-gray-900 truncate block">{result.title}</span>
                          <p className="text-sm text-gray-500 truncate">
                            {result.course_title} · {result.module_title}
                          </p>
                        </div>
                        <span className="text-xs px-2 py-0.5 bg-gray-100 text-gray-600 rounded flex-shrink-0">
                          {result.content_type}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
};
