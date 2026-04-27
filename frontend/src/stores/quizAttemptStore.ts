// src/stores/quizAttemptStore.ts
//
// Ephemeral, in-progress quiz attempt state — the teacher's live session.
//
// Contract:
//   • `start()` is called once from QuizPlayerPage after the backend creates
//     the attempt. It captures the attempt id, the shuffled question snapshot,
//     and the server-authoritative end-time expressed as an epoch millisecond
//     value (`endAtMs`). The countdown is derived from `Date.now()` minus that
//     value on every tick, so a refreshed tab resumes with the correct timer.
//   • Answers are persisted to `sessionStorage` on every write so a refresh
//     mid-quiz doesn't lose work (the POST on submit is still single-shot).
//   • Navigation is managed entirely client-side (`setCurrentIndex`).
//   • `clear()` resets everything, e.g. after submit or when leaving the page.

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { AttemptQuestion } from '../services/assessmentService';

/** Everything needed to render + grade a live attempt. */
export interface QuizAttemptState {
  /** Backend attempt id — key for submit. null when not started. */
  attemptId: string | null;
  /** Content (quiz) id — used for the "back to course" link. */
  contentId: string | null;
  /** Questions in the order the teacher should see them (already shuffled). */
  questions: AttemptQuestion[];
  /** Keyed by question id. See `AttemptAnswer` for shapes per type. */
  answers: Record<string, unknown>;
  /** 0-based index of the question currently displayed. */
  currentIndex: number;
  /** Server-authoritative deadline (ms since epoch). `null` = unlimited. */
  endAtMs: number | null;
  /** Wall-clock start used to compute `time_spent_seconds` on submit. */
  startedAtMs: number | null;
  /** Max score from backend — displayed on the result screen. */
  maxScore: number;

  /** Actions */
  start: (payload: {
    attemptId: string;
    contentId: string;
    questions: AttemptQuestion[];
    timeLimitSeconds: number;
    startedAt: string;
    maxScore: number;
  }) => void;

  setAnswer: (questionId: string, answer: unknown) => void;
  setCurrentIndex: (index: number) => void;
  next: () => void;
  prev: () => void;
  /** Seconds remaining until `endAtMs`. Returns null when unlimited. */
  remainingSeconds: () => number | null;
  /** Seconds elapsed since `startedAtMs`. */
  elapsedSeconds: () => number;
  clear: () => void;
}

const INITIAL: Omit<QuizAttemptState,
  'start' | 'setAnswer' | 'setCurrentIndex' | 'next' | 'prev'
  | 'remainingSeconds' | 'elapsedSeconds' | 'clear'
> = {
  attemptId: null,
  contentId: null,
  questions: [],
  answers: {},
  currentIndex: 0,
  endAtMs: null,
  startedAtMs: null,
  maxScore: 0,
};

export const useQuizAttemptStore = create<QuizAttemptState>()(
  persist(
    (set, get) => ({
      ...INITIAL,

      start: ({
        attemptId,
        contentId,
        questions,
        timeLimitSeconds,
        startedAt,
        maxScore,
      }) => {
        // Derive wall-clock start. The backend returns an ISO timestamp, but
        // there's no guaranteed `expires_at` field yet — so we fall back to
        // `startedAt + timeLimitSeconds`. When `timeLimitSeconds === 0` there
        // is no deadline (unlimited).
        const startedAtMs = new Date(startedAt).getTime() || Date.now();
        const endAtMs = timeLimitSeconds > 0
          ? startedAtMs + timeLimitSeconds * 1000
          : null;

        set({
          attemptId,
          contentId,
          questions,
          answers: {},
          currentIndex: 0,
          endAtMs,
          startedAtMs,
          maxScore,
        });
      },

      setAnswer: (questionId, answer) =>
        set((s) => ({ answers: { ...s.answers, [questionId]: answer } })),

      setCurrentIndex: (index) => {
        const total = get().questions.length;
        const clamped = Math.max(0, Math.min(index, Math.max(0, total - 1)));
        set({ currentIndex: clamped });
      },

      next: () => {
        const { currentIndex, questions } = get();
        if (currentIndex < questions.length - 1) {
          set({ currentIndex: currentIndex + 1 });
        }
      },

      prev: () => {
        const { currentIndex } = get();
        if (currentIndex > 0) set({ currentIndex: currentIndex - 1 });
      },

      remainingSeconds: () => {
        const { endAtMs } = get();
        if (endAtMs === null) return null;
        return Math.max(0, Math.floor((endAtMs - Date.now()) / 1000));
      },

      elapsedSeconds: () => {
        const { startedAtMs } = get();
        if (startedAtMs === null) return 0;
        return Math.max(0, Math.floor((Date.now() - startedAtMs) / 1000));
      },

      clear: () => set({ ...INITIAL }),
    }),
    {
      name: 'lp-quiz-attempt',
      storage: createJSONStorage(() => sessionStorage),
      // Only persist data — not actions/computed values.
      partialize: (s) => ({
        attemptId: s.attemptId,
        contentId: s.contentId,
        questions: s.questions,
        answers: s.answers,
        currentIndex: s.currentIndex,
        endAtMs: s.endAtMs,
        startedAtMs: s.startedAtMs,
        maxScore: s.maxScore,
      }),
    },
  ),
);
