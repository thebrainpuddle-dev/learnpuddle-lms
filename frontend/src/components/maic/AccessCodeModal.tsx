// src/components/maic/AccessCodeModal.tsx
//
// Modal dialog for entering a 6-digit classroom access code. Features individual
// digit input boxes with auto-advance, paste support, keyboard navigation,
// error shake animation, and loading state.

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Lock, Loader2 } from 'lucide-react';
import { cn } from '../../lib/utils';

interface AccessCodeModalProps {
  /** Whether the modal is open */
  isOpen: boolean;
  /** Classroom title for display */
  classroomTitle?: string;
  /** Callback when code is submitted — returns true if valid */
  onSubmit: (code: string) => Promise<boolean>;
  /** Callback when modal is closed/cancelled */
  onClose: () => void;
}

const CODE_LENGTH = 6;

export const AccessCodeModal = React.memo<AccessCodeModalProps>(
  function AccessCodeModal({ isOpen, classroomTitle, onSubmit, onClose }) {
    const [digits, setDigits] = useState<string[]>(Array(CODE_LENGTH).fill(''));
    const [error, setError] = useState(false);
    const [isValidating, setIsValidating] = useState(false);
    const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

    // Auto-focus first input on open
    useEffect(() => {
      if (isOpen) {
        setDigits(Array(CODE_LENGTH).fill(''));
        setError(false);
        setIsValidating(false);
        // Small delay to let animation start before focusing
        const timer = setTimeout(() => {
          inputRefs.current[0]?.focus();
        }, 100);
        return () => clearTimeout(timer);
      }
    }, [isOpen]);

    const handleSubmit = useCallback(async () => {
      const code = digits.join('');
      if (code.length !== CODE_LENGTH) return;

      setError(false);
      setIsValidating(true);
      try {
        const valid = await onSubmit(code);
        setIsValidating(false);
        if (!valid) {
          setError(true);
          // Reset error after shake animation
          setTimeout(() => setError(false), 600);
        }
      } catch {
        setError(true);
        setIsValidating(false);
        setTimeout(() => setError(false), 600);
      }
    }, [digits, onSubmit]);

    const updateDigit = useCallback(
      (index: number, value: string) => {
        setDigits((prev) => {
          const next = [...prev];
          next[index] = value;
          return next;
        });
      },
      [],
    );

    const handleChange = useCallback(
      (index: number, e: React.ChangeEvent<HTMLInputElement>) => {
        const val = e.target.value;
        // Only accept digits
        const digit = val.replace(/\D/g, '').slice(-1);
        updateDigit(index, digit);
        if (digit && index < CODE_LENGTH - 1) {
          inputRefs.current[index + 1]?.focus();
        }
      },
      [updateDigit],
    );

    const handleKeyDown = useCallback(
      (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Backspace') {
          if (!digits[index] && index > 0) {
            // If current box is empty, move to previous and clear it
            updateDigit(index - 1, '');
            inputRefs.current[index - 1]?.focus();
            e.preventDefault();
          } else {
            updateDigit(index, '');
          }
        } else if (e.key === 'ArrowLeft' && index > 0) {
          inputRefs.current[index - 1]?.focus();
          e.preventDefault();
        } else if (e.key === 'ArrowRight' && index < CODE_LENGTH - 1) {
          inputRefs.current[index + 1]?.focus();
          e.preventDefault();
        } else if (e.key === 'Enter') {
          handleSubmit();
        } else if (e.key === 'Escape') {
          onClose();
        }
      },
      [digits, updateDigit, handleSubmit, onClose],
    );

    const handlePaste = useCallback(
      (e: React.ClipboardEvent<HTMLInputElement>) => {
        e.preventDefault();
        const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, CODE_LENGTH);
        if (!pasted) return;

        setDigits((prev) => {
          const next = [...prev];
          for (let i = 0; i < pasted.length; i++) {
            next[i] = pasted[i];
          }
          return next;
        });

        // Focus the next empty box or the last filled one
        const focusIdx = Math.min(pasted.length, CODE_LENGTH - 1);
        setTimeout(() => inputRefs.current[focusIdx]?.focus(), 0);
      },
      [],
    );

    const isComplete = digits.every((d) => d !== '');

    return (
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
            onClick={(e) => {
              if (e.target === e.currentTarget) onClose();
            }}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0, y: 20 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.95, opacity: 0, y: 10 }}
              transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              className="relative w-full max-w-sm mx-4 bg-white rounded-2xl shadow-2xl p-8"
            >
              {/* Lock icon */}
              <div className="flex justify-center mb-5">
                <div className="flex items-center justify-center h-14 w-14 rounded-full bg-indigo-100">
                  <Lock className="h-7 w-7 text-indigo-600" />
                </div>
              </div>

              {/* Title */}
              <h2 className="text-xl font-bold text-gray-900 text-center mb-1">
                Access Code Required
              </h2>

              {/* Subtitle */}
              {classroomTitle && (
                <p className="text-sm text-gray-500 text-center mb-6 truncate px-2">
                  {classroomTitle}
                </p>
              )}
              {!classroomTitle && <div className="mb-6" />}

              {/* 6-digit code input */}
              <motion.div
                animate={error ? { x: [0, -8, 8, -6, 6, -3, 3, 0] } : { x: 0 }}
                transition={{ duration: 0.4 }}
                className="flex items-center justify-center gap-2 mb-6"
              >
                {Array.from({ length: CODE_LENGTH }, (_, i) => (
                  <input
                    key={i}
                    ref={(el) => {
                      inputRefs.current[i] = el;
                    }}
                    type="text"
                    inputMode="numeric"
                    maxLength={1}
                    value={digits[i]}
                    onChange={(e) => handleChange(i, e)}
                    onKeyDown={(e) => handleKeyDown(i, e)}
                    onPaste={i === 0 ? handlePaste : undefined}
                    disabled={isValidating}
                    className={cn(
                      'w-12 h-14 text-center text-2xl font-mono rounded-lg border-2 outline-none transition-colors duration-150',
                      'focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200',
                      error
                        ? 'border-red-400 bg-red-50'
                        : digits[i]
                          ? 'border-indigo-300 bg-indigo-50/30'
                          : 'border-gray-200 bg-gray-50',
                      isValidating && 'opacity-60 cursor-not-allowed',
                    )}
                    aria-label={`Digit ${i + 1}`}
                  />
                ))}
              </motion.div>

              {/* Error message */}
              <AnimatePresence>
                {error && (
                  <motion.p
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="text-sm text-red-500 text-center mb-4"
                  >
                    Invalid access code. Please try again.
                  </motion.p>
                )}
              </AnimatePresence>

              {/* Submit button */}
              <button
                onClick={handleSubmit}
                disabled={!isComplete || isValidating}
                className={cn(
                  'w-full py-3 rounded-xl text-sm font-semibold transition-all duration-200',
                  isComplete && !isValidating
                    ? 'bg-indigo-600 text-white hover:bg-indigo-700 active:scale-[0.98] shadow-md hover:shadow-lg'
                    : 'bg-gray-100 text-gray-400 cursor-not-allowed',
                )}
              >
                {isValidating ? (
                  <span className="flex items-center justify-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Verifying...
                  </span>
                ) : (
                  'Enter Classroom'
                )}
              </button>

              {/* Cancel link */}
              <button
                onClick={onClose}
                className="w-full mt-3 py-2 text-sm text-gray-400 hover:text-gray-600 transition-colors"
              >
                Cancel
              </button>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    );
  },
);
