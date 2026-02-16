// src/components/common/SkipLink.tsx
/**
 * Skip to main content link for keyboard accessibility.
 * Visually hidden until focused, allows keyboard users to bypass navigation.
 */

import React from 'react';
import { clsx } from 'clsx';

interface SkipLinkProps {
  /** Target element ID to skip to */
  targetId?: string;
  /** Custom text for the skip link */
  children?: React.ReactNode;
  /** Additional class names */
  className?: string;
}

export const SkipLink: React.FC<SkipLinkProps> = ({
  targetId = 'main-content',
  children = 'Skip to main content',
  className,
}) => {
  const handleClick = (e: React.MouseEvent) => {
    e.preventDefault();
    const target = document.getElementById(targetId);
    if (target) {
      target.focus();
      target.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <a
      href={`#${targetId}`}
      onClick={handleClick}
      className={clsx(
        // Visually hidden but accessible
        'sr-only focus:not-sr-only',
        // Styling when focused
        'focus:fixed focus:top-4 focus:left-4 focus:z-50',
        'focus:block focus:px-4 focus:py-2',
        'focus:bg-primary-600 focus:text-white focus:rounded-md',
        'focus:shadow-lg focus:outline-none focus:ring-2 focus:ring-primary-400',
        'focus:text-sm focus:font-medium',
        className
      )}
    >
      {children}
    </a>
  );
};

export default SkipLink;
