// src/components/maic/InteractiveRenderer.tsx
//
// Renders interactive HTML modules (simulations, widgets, etc.) in a
// sandboxed iframe. Security: allow-scripts is enabled but allow-same-origin
// is explicitly omitted to prevent the sandboxed content from accessing
// the parent page's origin.

import React, { useState, useCallback } from 'react';
import { Loader2, AlertTriangle } from 'lucide-react';
import { cn } from '../../lib/utils';

interface InteractiveRendererProps {
  html: string;
  url?: string;
  sceneId: string;
}

export const InteractiveRenderer = React.memo<InteractiveRendererProps>(
  function InteractiveRenderer({ html, url, sceneId }) {
    const [isLoading, setIsLoading] = useState(true);
    const [hasError, setHasError] = useState(false);

    const handleLoad = useCallback(() => {
      setIsLoading(false);
    }, []);

    const handleError = useCallback(() => {
      setIsLoading(false);
      setHasError(true);
    }, []);

    if (hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-full bg-gray-50 text-gray-500 gap-3">
          <AlertTriangle className="h-8 w-8 text-amber-400" />
          <p className="text-sm font-medium">Failed to load interactive content</p>
          <p className="text-xs text-gray-400">
            The interactive module could not be rendered. Please try reloading.
          </p>
        </div>
      );
    }

    // If a URL is provided and no inline HTML, use the URL directly
    const useUrl = url && !html;

    return (
      <div className="relative w-full h-full rounded-lg border border-gray-200 overflow-hidden bg-white">
        {/* Loading overlay */}
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-white/80 z-10">
            <div className="flex flex-col items-center gap-2">
              <Loader2 className="h-6 w-6 text-primary-500 animate-spin" />
              <p className="text-xs text-gray-400">Loading interactive content...</p>
            </div>
          </div>
        )}

        {/* Sandboxed iframe */}
        <iframe
          key={sceneId}
          className={cn(
            'w-full h-full border-0',
            isLoading && 'invisible',
          )}
          sandbox="allow-scripts"
          title="Interactive content"
          onLoad={handleLoad}
          onError={handleError}
          {...(useUrl
            ? { src: url }
            : { srcDoc: html }
          )}
        />
      </div>
    );
  },
);
