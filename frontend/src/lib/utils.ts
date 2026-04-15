// src/lib/utils.ts
//
// Utility functions for the shadcn/ui component library.
// cn() merges Tailwind classes with proper conflict resolution.

import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

/**
 * Merge Tailwind CSS classes with proper conflict resolution.
 * Combines clsx (conditional classes) with tailwind-merge (deduplication).
 *
 * @example
 * cn('px-4 py-2', isActive && 'bg-blue-500', className)
 * cn('text-red-500', 'text-blue-500') // => 'text-blue-500' (last wins)
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
