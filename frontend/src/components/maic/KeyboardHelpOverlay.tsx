// src/components/maic/KeyboardHelpOverlay.tsx
//
// Modal listing all keyboard shortcuts. Opens when the user presses
// `?` inside the stage (Sprint 4 · B.13). Keeps the shortcut list as a
// single source of truth imported from `useKeyboardShortcuts.ts` so
// the overlay can't drift out of sync with the actual handlers.

import React, { useEffect } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { X } from 'lucide-react';
import { KEYBOARD_SHORTCUTS } from '../../hooks/useKeyboardShortcuts';

export interface KeyboardHelpOverlayProps {
  open: boolean;
  onClose: () => void;
}

export const KeyboardHelpOverlay: React.FC<KeyboardHelpOverlayProps> = ({
  open,
  onClose,
}) => {
  // Close on Escape so the modal doesn't need a focus trap to be dismissible.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          role="dialog"
          aria-modal="true"
          aria-label="Keyboard shortcuts"
        >
          <motion.div
            className="relative w-full max-w-md rounded-2xl bg-white shadow-2xl p-5"
            initial={{ scale: 0.95, y: 8, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.95, y: 8, opacity: 0 }}
            transition={{ duration: 0.18, ease: [0.21, 1, 0.36, 1] }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={onClose}
              className="absolute top-3 right-3 p-1 rounded-full text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
              aria-label="Close shortcuts help"
            >
              <X className="h-4 w-4" />
            </button>
            <h2 className="text-base font-semibold text-gray-900 mb-1">
              Keyboard shortcuts
            </h2>
            <p className="text-xs text-gray-500 mb-4">
              Press <kbd className="px-1.5 py-0.5 rounded bg-gray-100 border border-gray-200 text-[10px] font-mono">?</kbd> anywhere on the stage to reopen this list.
            </p>
            <ul className="divide-y divide-gray-100">
              {KEYBOARD_SHORTCUTS.map((shortcut) => (
                <li
                  key={shortcut.keys}
                  className="flex items-center justify-between py-1.5"
                >
                  <span className="text-sm text-gray-700">{shortcut.label}</span>
                  <kbd className="px-2 py-0.5 rounded bg-gray-100 border border-gray-200 text-[11px] font-mono text-gray-700">
                    {shortcut.keys}
                  </kbd>
                </li>
              ))}
            </ul>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
};
