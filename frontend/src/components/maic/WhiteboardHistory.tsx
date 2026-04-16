// src/components/maic/WhiteboardHistory.tsx
//
// Floating panel showing whiteboard undo/redo history and clear-all action.
// Positioned at the bottom-right of the whiteboard area with slide-in
// animation via the motion library.

import React, { useState, useCallback } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { Undo2, Redo2, Trash2 } from 'lucide-react';
import { useMAICCanvasStore } from '../../stores/maicCanvasStore';
import { cn } from '../../lib/utils';

interface WhiteboardHistoryProps {
  visible: boolean;
}

const CASCADE_DELETE_DELAY_MS = 55;

export const WhiteboardHistory = React.memo<WhiteboardHistoryProps>(
  function WhiteboardHistory({ visible }) {
    const undoStack = useMAICCanvasStore((s) => s.undoStack);
    const redoStack = useMAICCanvasStore((s) => s.redoStack);
    const annotations = useMAICCanvasStore((s) => s.annotations);
    const canUndo = useMAICCanvasStore((s) => s.canUndo);
    const canRedo = useMAICCanvasStore((s) => s.canRedo);
    const undo = useMAICCanvasStore((s) => s.undo);
    const redo = useMAICCanvasStore((s) => s.redo);
    const removeAnnotation = useMAICCanvasStore((s) => s.removeAnnotation);
    const clearAnnotations = useMAICCanvasStore((s) => s.clearAnnotations);

    const [confirmClear, setConfirmClear] = useState(false);
    const [isClearing, setIsClearing] = useState(false);

    const handleClear = useCallback(async () => {
      if (!confirmClear) {
        setConfirmClear(true);
        return;
      }

      // Cascade clear: remove annotations one by one with stagger delay
      const currentAnnotations = useMAICCanvasStore.getState().annotations;
      if (currentAnnotations.length === 0) {
        setConfirmClear(false);
        return;
      }

      setIsClearing(true);

      // Remove from last to first for a natural cascade effect
      for (let i = currentAnnotations.length - 1; i >= 0; i--) {
        removeAnnotation(currentAnnotations[i].id);
        if (i > 0) {
          await new Promise<void>((resolve) =>
            setTimeout(resolve, CASCADE_DELETE_DELAY_MS),
          );
        }
      }

      setIsClearing(false);
      setConfirmClear(false);
    }, [confirmClear, removeAnnotation]);

    // Dismiss confirmation when clicking away or after a timeout
    const handleCancelClear = useCallback(() => {
      setConfirmClear(false);
    }, []);

    const undoDepth = undoStack.length;
    const redoDepth = redoStack.length;
    const totalAnnotations = annotations.length;

    return (
      <AnimatePresence>
        {visible && (
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.95 }}
            transition={{ type: 'spring', stiffness: 300, damping: 24 }}
            className="absolute bottom-3 right-3 z-20 flex items-center gap-1.5 rounded-lg bg-white/95 dark:bg-gray-800/95 backdrop-blur-sm shadow-lg border border-gray-200 dark:border-gray-700 px-2 py-1.5"
            onMouseLeave={handleCancelClear}
          >
            {/* Undo */}
            <button
              type="button"
              onClick={undo}
              disabled={!canUndo() || isClearing}
              className={cn(
                'p-1.5 rounded-md transition-colors',
                'focus:outline-none focus:ring-2 focus:ring-primary-500',
                canUndo() && !isClearing
                  ? 'text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-gray-100 dark:hover:bg-gray-700'
                  : 'text-gray-300 dark:text-gray-600 cursor-not-allowed',
              )}
              title={`Undo (${undoDepth} steps)`}
              aria-label="Undo"
            >
              <Undo2 className="h-3.5 w-3.5" />
            </button>

            {/* Redo */}
            <button
              type="button"
              onClick={redo}
              disabled={!canRedo() || isClearing}
              className={cn(
                'p-1.5 rounded-md transition-colors',
                'focus:outline-none focus:ring-2 focus:ring-primary-500',
                canRedo() && !isClearing
                  ? 'text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-300 dark:hover:text-gray-100 dark:hover:bg-gray-700'
                  : 'text-gray-300 dark:text-gray-600 cursor-not-allowed',
              )}
              title={`Redo (${redoDepth} steps)`}
              aria-label="Redo"
            >
              <Redo2 className="h-3.5 w-3.5" />
            </button>

            {/* Divider */}
            <div className="w-px h-4 bg-gray-200 dark:bg-gray-700 mx-0.5" aria-hidden="true" />

            {/* History count badge */}
            <span
              className="text-[10px] tabular-nums text-gray-400 dark:text-gray-500 min-w-[1.5rem] text-center select-none"
              title={`${totalAnnotations} annotation${totalAnnotations !== 1 ? 's' : ''}`}
            >
              {totalAnnotations}
            </span>

            {/* Divider */}
            <div className="w-px h-4 bg-gray-200 dark:bg-gray-700 mx-0.5" aria-hidden="true" />

            {/* Clear all */}
            <button
              type="button"
              onClick={handleClear}
              disabled={totalAnnotations === 0 || isClearing}
              className={cn(
                'p-1.5 rounded-md transition-colors text-[10px] font-medium',
                'focus:outline-none focus:ring-2 focus:ring-primary-500',
                totalAnnotations === 0 || isClearing
                  ? 'text-gray-300 dark:text-gray-600 cursor-not-allowed'
                  : confirmClear
                    ? 'text-red-600 bg-red-50 hover:bg-red-100 dark:text-red-400 dark:bg-red-900/30 dark:hover:bg-red-900/50'
                    : 'text-gray-500 hover:text-red-600 hover:bg-red-50 dark:text-gray-400 dark:hover:text-red-400 dark:hover:bg-red-900/30',
              )}
              title={confirmClear ? 'Click again to confirm' : 'Clear all annotations'}
              aria-label={confirmClear ? 'Confirm clear all' : 'Clear all annotations'}
            >
              {isClearing ? (
                <span className="flex items-center gap-1">
                  <span className="h-3 w-3 rounded-full border-2 border-red-300 border-t-transparent animate-spin" />
                </span>
              ) : confirmClear ? (
                <span className="flex items-center gap-0.5">
                  <Trash2 className="h-3 w-3" />
                  <span>Sure?</span>
                </span>
              ) : (
                <Trash2 className="h-3.5 w-3.5" />
              )}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    );
  },
);
