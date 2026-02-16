// src/components/common/LazyImage.tsx
/**
 * Optimized lazy-loading image component.
 * 
 * Features:
 * - Native lazy loading with IntersectionObserver fallback
 * - Placeholder/blur effect while loading
 * - Responsive srcset support
 * - Error handling with fallback
 * - Accessibility attributes
 */

import React, { useState, useRef, useEffect } from 'react';
import { clsx } from 'clsx';

interface ImageSize {
  width: number;
  url: string;
}

interface LazyImageProps {
  /** Main image URL */
  src: string;
  /** Alt text (required for accessibility) */
  alt: string;
  /** Responsive image sizes for srcset */
  sizes?: ImageSize[];
  /** Sizes attribute for responsive images */
  sizesAttr?: string;
  /** Placeholder image URL or data URI */
  placeholder?: string;
  /** Custom width */
  width?: number | string;
  /** Custom height */
  height?: number | string;
  /** Object fit style */
  objectFit?: 'cover' | 'contain' | 'fill' | 'none' | 'scale-down';
  /** Aspect ratio (e.g., "16/9", "4/3") */
  aspectRatio?: string;
  /** Custom class names */
  className?: string;
  /** Container class names */
  containerClassName?: string;
  /** Callback when image loads */
  onLoad?: () => void;
  /** Callback on error */
  onError?: () => void;
  /** Fallback image on error */
  fallbackSrc?: string;
  /** Blur placeholder effect */
  blurPlaceholder?: boolean;
  /** Disable lazy loading */
  eager?: boolean;
}

// Generate a simple SVG placeholder
const generatePlaceholder = (width = 100, height = 100, color = '#e5e7eb') => {
  return `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='${width}' height='${height}'%3E%3Crect fill='${encodeURIComponent(color)}' width='100%25' height='100%25'/%3E%3C/svg%3E`;
};

export const LazyImage: React.FC<LazyImageProps> = ({
  src,
  alt,
  sizes,
  sizesAttr,
  placeholder,
  width,
  height,
  objectFit = 'cover',
  aspectRatio,
  className,
  containerClassName,
  onLoad,
  onError,
  fallbackSrc = '/images/placeholder.svg',
  blurPlaceholder = true,
  eager = false,
}) => {
  const [isLoaded, setIsLoaded] = useState(false);
  const [hasError, setHasError] = useState(false);
  const [isInView, setIsInView] = useState(eager);
  const imgRef = useRef<HTMLImageElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Build srcset string
  const srcset = sizes
    ?.map((size) => `${size.url} ${size.width}w`)
    .join(', ');

  // Intersection Observer for lazy loading
  useEffect(() => {
    if (eager || !containerRef.current) return;

    // Check for native lazy loading support
    if ('loading' in HTMLImageElement.prototype) {
      setIsInView(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setIsInView(true);
            observer.disconnect();
          }
        });
      },
      {
        rootMargin: '50px', // Start loading slightly before in view
        threshold: 0.01,
      }
    );

    observer.observe(containerRef.current);

    return () => observer.disconnect();
  }, [eager]);

  const handleLoad = () => {
    setIsLoaded(true);
    onLoad?.();
  };

  const handleError = () => {
    setHasError(true);
    onError?.();
  };

  const currentSrc = hasError ? fallbackSrc : src;
  const showPlaceholder = !isLoaded && !hasError;
  const placeholderSrc = placeholder || generatePlaceholder(
    typeof width === 'number' ? width : 100,
    typeof height === 'number' ? height : 100
  );

  return (
    <div
      ref={containerRef}
      className={clsx(
        'relative overflow-hidden bg-gray-100',
        containerClassName
      )}
      style={{
        width,
        height,
        aspectRatio,
      }}
    >
      {/* Placeholder */}
      {showPlaceholder && (
        <img
          src={placeholderSrc}
          alt=""
          aria-hidden="true"
          className={clsx(
            'absolute inset-0 w-full h-full',
            blurPlaceholder && 'blur-sm scale-110',
            `object-${objectFit}`
          )}
          style={{ objectFit }}
        />
      )}

      {/* Main image */}
      {isInView && (
        <img
          ref={imgRef}
          src={currentSrc}
          srcSet={!hasError ? srcset : undefined}
          sizes={!hasError ? sizesAttr : undefined}
          alt={alt}
          width={width}
          height={height}
          loading={eager ? 'eager' : 'lazy'}
          decoding="async"
          onLoad={handleLoad}
          onError={handleError}
          className={clsx(
            'w-full h-full transition-opacity duration-300',
            isLoaded ? 'opacity-100' : 'opacity-0',
            className
          )}
          style={{ objectFit }}
        />
      )}

      {/* Loading indicator */}
      {!isLoaded && !hasError && isInView && (
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-6 h-6 border-2 border-gray-300 border-t-primary-500 rounded-full animate-spin" />
        </div>
      )}
    </div>
  );
};

/**
 * Responsive image helper for common breakpoints.
 * Generates appropriate sizes attribute.
 */
export const responsiveSizes = {
  thumbnail: '(max-width: 640px) 100vw, 200px',
  card: '(max-width: 640px) 100vw, (max-width: 1024px) 50vw, 33vw',
  hero: '100vw',
  avatar: '48px',
};

export default LazyImage;
