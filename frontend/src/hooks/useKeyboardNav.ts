// src/hooks/useKeyboardNav.ts
/**
 * Hook for managing keyboard navigation in lists/menus.
 * 
 * Supports:
 * - Arrow key navigation (up/down)
 * - Home/End keys
 * - Type-ahead search
 * - Focus management
 */

import { useState, useCallback, useRef, useEffect } from 'react';

interface UseKeyboardNavOptions {
  /** Total number of items */
  itemCount: number;
  /** Initial focused index */
  initialIndex?: number;
  /** Callback when index changes */
  onIndexChange?: (index: number) => void;
  /** Enable wrapping from last to first */
  wrap?: boolean;
  /** Enable type-ahead search */
  typeAhead?: boolean;
  /** Get label for type-ahead matching */
  getItemLabel?: (index: number) => string;
}

interface UseKeyboardNavReturn {
  /** Currently focused index */
  focusedIndex: number;
  /** Set focused index */
  setFocusedIndex: (index: number) => void;
  /** Handle keyboard events */
  handleKeyDown: (e: React.KeyboardEvent) => void;
  /** Props to spread on container */
  containerProps: {
    role: string;
    tabIndex: number;
    onKeyDown: (e: React.KeyboardEvent) => void;
  };
  /** Get props for each item */
  getItemProps: (index: number) => {
    role: string;
    tabIndex: number;
    'aria-selected': boolean;
  };
}

export function useKeyboardNav({
  itemCount,
  initialIndex = 0,
  onIndexChange,
  wrap = true,
  typeAhead = false,
  getItemLabel,
}: UseKeyboardNavOptions): UseKeyboardNavReturn {
  const [focusedIndex, setFocusedIndex] = useState(initialIndex);
  const searchBufferRef = useRef('');
  const searchTimeoutRef = useRef<NodeJS.Timeout | undefined>(undefined);

  // Reset search buffer after delay
  const resetSearchBuffer = useCallback(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    searchTimeoutRef.current = setTimeout(() => {
      searchBufferRef.current = '';
    }, 500);
  }, []);

  const updateIndex = useCallback((newIndex: number) => {
    setFocusedIndex(newIndex);
    onIndexChange?.(newIndex);
  }, [onIndexChange]);

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (itemCount === 0) return;

    switch (e.key) {
      case 'ArrowDown':
      case 'ArrowRight':
        e.preventDefault();
        if (wrap) {
          updateIndex((focusedIndex + 1) % itemCount);
        } else {
          updateIndex(Math.min(focusedIndex + 1, itemCount - 1));
        }
        break;

      case 'ArrowUp':
      case 'ArrowLeft':
        e.preventDefault();
        if (wrap) {
          updateIndex((focusedIndex - 1 + itemCount) % itemCount);
        } else {
          updateIndex(Math.max(focusedIndex - 1, 0));
        }
        break;

      case 'Home':
        e.preventDefault();
        updateIndex(0);
        break;

      case 'End':
        e.preventDefault();
        updateIndex(itemCount - 1);
        break;

      case 'Enter':
      case ' ':
        // Don't prevent default - let click handlers work
        break;

      default:
        // Type-ahead search
        if (typeAhead && getItemLabel && e.key.length === 1) {
          searchBufferRef.current += e.key.toLowerCase();
          resetSearchBuffer();

          // Find matching item
          for (let i = 0; i < itemCount; i++) {
            const label = getItemLabel(i).toLowerCase();
            if (label.startsWith(searchBufferRef.current)) {
              updateIndex(i);
              break;
            }
          }
        }
    }
  }, [focusedIndex, itemCount, wrap, typeAhead, getItemLabel, updateIndex, resetSearchBuffer]);

  // Cleanup
  useEffect(() => {
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, []);

  const containerProps = {
    role: 'listbox' as const,
    tabIndex: 0,
    onKeyDown: handleKeyDown,
  };

  const getItemProps = (index: number) => ({
    role: 'option' as const,
    tabIndex: index === focusedIndex ? 0 : -1,
    'aria-selected': index === focusedIndex,
  });

  return {
    focusedIndex,
    setFocusedIndex: updateIndex,
    handleKeyDown,
    containerProps,
    getItemProps,
  };
}

export default useKeyboardNav;
