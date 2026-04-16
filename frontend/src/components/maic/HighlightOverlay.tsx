// src/components/maic/HighlightOverlay.tsx
//
// Element highlighting overlay for presentations. Renders a semi-transparent
// full-viewport overlay with an SVG mask cutout around the highlighted element.
// Includes a pulsing border and auto-dismiss timer.

import React, { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { cn } from '../../lib/utils';

// ─── Props ───────────────────────────────────────────────────────────────────

export interface HighlightOverlayProps {
  elementId: string | null;
  color?: string;
  active: boolean;
  onDismiss?: () => void;
  duration?: number; // auto-dismiss in ms, default 5000
}

// ─── Component ───────────────────────────────────────────────────────────────

export const HighlightOverlay = React.memo<HighlightOverlayProps>(
  function HighlightOverlay({
    elementId,
    color = '#6366f1',
    active,
    onDismiss,
    duration = 5000,
  }) {
    const [rect, setRect] = useState<DOMRect | null>(null);

    // ─── Locate the element and track its position ───────────────────────
    useEffect(() => {
      if (!active || !elementId) {
        setRect(null);
        return;
      }

      const updateRect = () => {
        const el = document.getElementById(elementId);
        if (el) {
          setRect(el.getBoundingClientRect());
        } else {
          setRect(null);
        }
      };

      updateRect();

      // Re-measure on resize or scroll
      window.addEventListener('resize', updateRect);
      window.addEventListener('scroll', updateRect, true);

      return () => {
        window.removeEventListener('resize', updateRect);
        window.removeEventListener('scroll', updateRect, true);
      };
    }, [active, elementId]);

    // ─── Auto-dismiss ────────────────────────────────────────────────────
    useEffect(() => {
      if (!active || duration <= 0) return;
      const timer = setTimeout(() => {
        onDismiss?.();
      }, duration);
      return () => clearTimeout(timer);
    }, [active, duration, onDismiss]);

    // ─── Click outside to dismiss ────────────────────────────────────────
    const handleOverlayClick = useCallback(() => {
      onDismiss?.();
    }, [onDismiss]);

    const padding = 8; // padding around the highlighted element

    return (
      <AnimatePresence>
        {active && rect && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50"
            onClick={handleOverlayClick}
            role="presentation"
            aria-hidden="true"
          >
            {/* SVG mask overlay */}
            <svg
              className="absolute inset-0 w-full h-full"
              xmlns="http://www.w3.org/2000/svg"
            >
              <defs>
                <mask id="highlight-mask">
                  {/* White = visible overlay */}
                  <rect x="0" y="0" width="100%" height="100%" fill="white" />
                  {/* Black = transparent cutout */}
                  <rect
                    x={rect.left - padding}
                    y={rect.top - padding}
                    width={rect.width + padding * 2}
                    height={rect.height + padding * 2}
                    rx="8"
                    fill="black"
                  />
                </mask>
              </defs>
              <rect
                x="0"
                y="0"
                width="100%"
                height="100%"
                fill="rgba(0, 0, 0, 0.5)"
                mask="url(#highlight-mask)"
              />
            </svg>

            {/* Pulsing border around the element */}
            <div
              className="absolute rounded-lg pointer-events-none"
              style={{
                left: rect.left - padding,
                top: rect.top - padding,
                width: rect.width + padding * 2,
                height: rect.height + padding * 2,
                boxShadow: `0 0 0 2px ${color}, 0 0 12px 2px ${color}60`,
                animation: 'highlight-pulse 1.5s ease-in-out infinite',
              }}
            />

            {/* Keyframes injected via style tag */}
            <style>{`
              @keyframes highlight-pulse {
                0%, 100% { box-shadow: 0 0 0 2px ${color}, 0 0 12px 2px ${color}60; }
                50% { box-shadow: 0 0 0 4px ${color}, 0 0 20px 4px ${color}40; }
              }
            `}</style>
          </motion.div>
        )}
      </AnimatePresence>
    );
  },
);
