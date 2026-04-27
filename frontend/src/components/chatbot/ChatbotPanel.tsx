// src/components/chatbot/ChatbotPanel.tsx
//
// Slide-in panel for the RAG-backed chatbot Q&A widget.
// Single-turn Q&A: each question is independent — no multi-turn memory.
//
// Accessibility:
//   - Focus trap (Tab cycles within panel, Shift-Tab reverses)
//   - Esc closes
//   - Enter submits (without Shift)
//   - aria-live="polite" on answer region
//
// Error handling:
//   - 503 / network → retry button
//   - 400 QUESTION_TOO_LONG → inline validation message
//   - 403 → "No access to this course's assistant"
//
// (TASK-061)

import React, { useRef, useEffect, useCallback } from 'react';
import {
  XMarkIcon,
  PaperAirplaneIcon,
  ClockIcon,
  SparklesIcon,
  ArrowPathIcon,
  TrashIcon,
} from '@heroicons/react/24/outline';
import { chatbotService } from '../../services/chatbotService';
import type { RagChatbotErrorKind } from '../../stores/ragChatbotStore';
import { useRagChatbotStore } from '../../stores/ragChatbotStore';
import { ChatbotMessage } from './ChatbotMessage';
import { ChatbotHistory } from './ChatbotHistory';
import { cn } from '../../lib/utils';
import { useToast } from '../common';

// TODO(analytics): wire chatbot open/close + message counts to useAnalytics — tracked in queue.md batch cleanup cycle 2
const trackEvent = (_name: string, _props?: Record<string, unknown>): void => undefined;

const MAX_CHARS = 2000;

function mapErrorKindToMessage(kind: RagChatbotErrorKind | null, message: string | null): string {
  if (!kind) return message || 'Something went wrong. Please try again.';
  if (kind === 'SERVICE_UNAVAILABLE') return 'Chatbot temporarily unavailable. Please try again.';
  if (kind === 'QUESTION_TOO_LONG') return 'Your question exceeds 2000 characters. Please shorten it.';
  if (kind === 'FORBIDDEN') return 'No access to this course\'s assistant.';
  return message || 'Something went wrong. Please try again.';
}

interface ChatbotPanelProps {
  courseId: string;
}

export const ChatbotPanel: React.FC<ChatbotPanelProps> = ({ courseId }) => {
  const toast = useToast();
  const {
    status,
    question,
    lastAnswer,
    errorKind,
    errorMessage,
    history,
    historyLoaded,
    showHistory,
    close,
    setQuestion,
    setLoading,
    setAnswer,
    setError,
    reset,
    setHistory,
    setHistoryLoaded,
    toggleHistory,
    optimisticRemoveHistoryItem,
    rollbackHistoryItem,
  } = useRagChatbotStore();

  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // Captures the element that had focus when the panel was opened so focus can
  // be restored to it (typically the launcher button) when the panel closes.
  const priorFocusRef = useRef<HTMLElement | null>(null);
  const answerRegionRef = useRef<HTMLDivElement>(null);

  const isLoading = status === 'OPEN_LOADING';
  const isOpen = status !== 'IDLE';
  const charCount = question.length;
  const isOverLimit = charCount > MAX_CHARS;
  const canSubmit = question.trim().length > 0 && !isLoading && !isOverLimit;

  // ─── Focus trap ─────────────────────────────────────────────────────────────
  const handlePanelKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        trackEvent('chatbot_panel_closed', { method: 'escape' });
        close();
        return;
      }

      if (e.key !== 'Tab' || !panelRef.current) return;

      const focusable = Array.from(
        panelRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => !el.hasAttribute('disabled'));

      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    },
    [close],
  );

  // ─── Auto-focus input when panel opens; restore focus to launcher on close ──
  useEffect(() => {
    if (isOpen) {
      // Capture whatever had focus before the panel opened (usually the launcher button)
      priorFocusRef.current = document.activeElement as HTMLElement | null;
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      // Panel closed — return focus to the element that triggered the open
      priorFocusRef.current?.focus();
      priorFocusRef.current = null;
    }
  }, [isOpen]);

  // ─── Load history when panel opens ──────────────────────────────────────────
  useEffect(() => {
    if (!isOpen || historyLoaded) return;

    chatbotService
      .getHistory(20)
      .then((data) => {
        setHistory(data.results);
        setHistoryLoaded(true);
      })
      .catch(() => {
        // History load failure is non-critical — show empty state
        setHistoryLoaded(true);
      });
  }, [isOpen, historyLoaded, setHistory, setHistoryLoaded]);

  // ─── Submit handler ──────────────────────────────────────────────────────────
  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return;

    const q = question.trim();

    // Pre-submit client-side length validation
    if (q.length > MAX_CHARS) {
      setError('QUESTION_TOO_LONG', 'Your question exceeds 2000 characters. Please shorten it.');
      return;
    }

    trackEvent('chatbot_question_submitted', { course_id: courseId });
    setLoading();

    try {
      const response = await chatbotService.askQuestion({
        question: q,
        course_id: courseId,
        top_k: 5,
      });
      setAnswer(response);
      trackEvent('chatbot_answer_received', {
        course_id: courseId,
        grounded: response.grounded,
        citation_count: response.citations.length,
      });
    } catch (err: any) {
      const status = err?.response?.status;
      const errorCode = err?.response?.data?.error;

      let kind: RagChatbotErrorKind = 'UNKNOWN';
      let msg = 'Something went wrong. Please try again.';

      if (status === 503 || !status) {
        kind = 'SERVICE_UNAVAILABLE';
        msg = 'Chatbot temporarily unavailable. Please try again.';
      } else if (status === 400 && errorCode === 'QUESTION_TOO_LONG') {
        kind = 'QUESTION_TOO_LONG';
        msg = 'Your question exceeds 2000 characters. Please shorten it.';
      } else if (status === 403) {
        kind = 'FORBIDDEN';
        msg = 'No access to this course\'s assistant.';
      } else if (status === 429) {
        kind = 'SERVICE_UNAVAILABLE';
        msg = 'Rate limit reached. Please wait before asking another question.';
      }

      trackEvent('chatbot_error', { course_id: courseId, kind, status });
      setError(kind, msg);
    }
  }, [canSubmit, question, courseId, setLoading, setAnswer, setError]);

  const handleTextareaKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  // ─── Delete history item (optimistic) ───────────────────────────────────────
  const handleDeleteHistoryItem = useCallback(
    async (id: string) => {
      const removed = optimisticRemoveHistoryItem(id);
      try {
        await chatbotService.deleteHistoryItem(id);
        trackEvent('chatbot_history_deleted', { id });
      } catch {
        // Rollback optimistic remove and notify user
        if (removed) rollbackHistoryItem(removed);
        toast.error("Couldn't delete — please retry");
      }
    },
    [optimisticRemoveHistoryItem, rollbackHistoryItem, toast],
  );

  const handleRetry = () => {
    // Retry submits the same question again
    handleSubmit();
  };

  const canRetry =
    status === 'OPEN_ERROR' &&
    (errorKind === 'SERVICE_UNAVAILABLE' || errorKind === 'UNKNOWN') &&
    question.trim().length > 0;

  return (
    <div
      ref={panelRef}
      role="dialog"
      aria-modal="true"
      aria-label="Course Q&A Assistant"
      onKeyDown={handlePanelKeyDown}
      className={cn(
        'fixed bottom-0 right-0 z-50 flex flex-col',
        'w-full sm:w-[400px] h-[580px] sm:h-[600px]',
        'sm:bottom-24 sm:right-6',
        'bg-white sm:rounded-2xl shadow-2xl border border-slate-200',
        'overflow-hidden',
      )}
      data-testid="chatbot-panel"
    >
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-primary-600 text-white sm:rounded-t-2xl shrink-0">
        <div className="flex items-center gap-2">
          <SparklesIcon className="h-5 w-5 shrink-0" />
          <div className="min-w-0">
            <h2 className="text-sm font-semibold leading-tight">Course Q&A Assistant</h2>
            <p className="text-[10px] text-white/70">Powered by course materials</p>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={toggleHistory}
            className="p-1.5 rounded hover:bg-primary-500 transition-colors"
            title={showHistory ? 'Hide history' : 'Show question history'}
            aria-label={showHistory ? 'Hide question history' : 'Show question history'}
            aria-pressed={showHistory}
          >
            <ClockIcon className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => {
              trackEvent('chatbot_panel_closed', { method: 'button' });
              close();
            }}
            className="p-1.5 rounded hover:bg-primary-500 transition-colors"
            title="Close"
            aria-label="Close Q&A assistant"
          >
            <XMarkIcon className="h-5 w-5" />
          </button>
        </div>
      </div>

      {/* ── Body ───────────────────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {/* History sidebar */}
        {showHistory && (
          <div className="w-56 border-r border-slate-200 bg-slate-50 shrink-0 overflow-y-auto">
            <div className="px-4 py-2.5 border-b border-slate-200">
              <p className="text-xs font-semibold text-slate-600 uppercase tracking-wide">Recent Questions</p>
            </div>
            <ChatbotHistory
              items={history}
              isLoading={!historyLoaded}
              onDelete={handleDeleteHistoryItem}
            />
          </div>
        )}

        {/* Main Q&A area */}
        <div className="flex flex-col flex-1 min-w-0">
          {/* Answer / idle region */}
          <div
            ref={answerRegionRef}
            className="flex-1 overflow-y-auto p-4"
            aria-live="polite"
            aria-atomic="true"
          >
            {status === 'OPEN_IDLE' && (
              <div className="flex flex-col items-center justify-center h-full text-center px-4">
                <div className="w-14 h-14 rounded-full bg-primary-50 flex items-center justify-center mb-3">
                  <SparklesIcon className="h-7 w-7 text-primary-500" />
                </div>
                <h3 className="text-sm font-semibold text-slate-800 mb-1">Ask about this course</h3>
                <p className="text-xs text-slate-500 max-w-[220px]">
                  Questions are answered using the course materials. Each question is independent.
                </p>
              </div>
            )}

            {status === 'OPEN_LOADING' && (
              <div className="flex flex-col items-center justify-center h-full gap-3">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600" aria-label="Generating answer…" />
                <p className="text-xs text-slate-500">Searching course materials…</p>
              </div>
            )}

            {status === 'OPEN_ANSWERED' && lastAnswer && (
              <div className="space-y-3">
                <ChatbotMessage answer={lastAnswer} courseId={courseId} />
                <button
                  type="button"
                  onClick={reset}
                  className={cn(
                    'text-xs text-slate-500 hover:text-slate-700 underline underline-offset-2',
                    'focus:outline-none focus:ring-2 focus:ring-primary-500 rounded',
                  )}
                  aria-label="Ask another question"
                >
                  Ask another question
                </button>
              </div>
            )}

            {status === 'OPEN_ERROR' && (
              <div className="rounded-xl border border-red-200 bg-red-50 p-4">
                <p className="text-sm font-medium text-red-700 mb-1">
                  {mapErrorKindToMessage(errorKind, errorMessage)}
                </p>
                <div className="flex gap-2 mt-3">
                  {canRetry && (
                    <button
                      type="button"
                      onClick={handleRetry}
                      className={cn(
                        'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg',
                        'bg-red-600 text-white hover:bg-red-700 transition-colors',
                        'focus:outline-none focus:ring-2 focus:ring-red-500',
                      )}
                      aria-label="Retry the same question"
                    >
                      <ArrowPathIcon className="h-3.5 w-3.5" />
                      Retry
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={reset}
                    className={cn(
                      'inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg',
                      'bg-white border border-red-200 text-red-700 hover:bg-red-50 transition-colors',
                      'focus:outline-none focus:ring-2 focus:ring-red-400',
                    )}
                  >
                    <TrashIcon className="h-3.5 w-3.5" />
                    Clear
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Input area */}
          <div className="border-t border-slate-200 px-4 py-3 shrink-0">
            <div className="flex items-end gap-2">
              <div className="flex-1 relative">
                <textarea
                  ref={inputRef}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={handleTextareaKeyDown}
                  placeholder="Ask a question about this course…"
                  rows={2}
                  maxLength={MAX_CHARS + 100} // allow slight over-typing so counter turns red
                  disabled={isLoading}
                  className={cn(
                    'w-full resize-none rounded-lg border px-3 py-2 text-sm',
                    'placeholder:text-slate-400 leading-relaxed',
                    'focus:outline-none focus:ring-2 focus:border-transparent',
                    'disabled:opacity-50 disabled:cursor-not-allowed',
                    'max-h-28 overflow-y-auto',
                    isOverLimit
                      ? 'border-red-400 focus:ring-red-400'
                      : 'border-slate-300 focus:ring-primary-500',
                  )}
                  aria-label="Question input"
                  aria-describedby="char-counter chatbot-hint"
                />
              </div>
              <button
                type="button"
                onClick={handleSubmit}
                disabled={!canSubmit}
                className={cn(
                  'shrink-0 h-[38px] w-[38px] rounded-lg flex items-center justify-center',
                  'bg-primary-600 text-white hover:bg-primary-700 transition-colors',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                  'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-1',
                )}
                aria-label="Submit question"
                title="Submit (Enter)"
              >
                {isLoading ? (
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                ) : (
                  <PaperAirplaneIcon className="h-4 w-4" />
                )}
              </button>
            </div>

            <div className="flex items-center justify-between mt-1.5">
              <p
                id="chatbot-hint"
                className="text-[10px] text-slate-400"
              >
                Enter to submit · Shift+Enter for newline · Esc to close
              </p>
              <p
                id="char-counter"
                className={cn(
                  'text-[10px] tabular-nums',
                  isOverLimit ? 'text-red-500 font-semibold' : 'text-slate-400',
                )}
                aria-live="polite"
                aria-label={`${charCount} of ${MAX_CHARS} characters used`}
              >
                {charCount}/{MAX_CHARS}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
