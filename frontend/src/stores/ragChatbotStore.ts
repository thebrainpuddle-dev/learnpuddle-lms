// src/stores/ragChatbotStore.ts
//
// Zustand store for the RAG-based chatbot widget (TASK-061).
// Implements the state machine:
//   IDLE → OPEN_IDLE → OPEN_LOADING → OPEN_ANSWERED | OPEN_ERROR → OPEN_IDLE
//
// This store is separate from the existing chatbotStore.ts which manages
// the session-based AI Tutor chatbot builder.

import { create } from 'zustand';
import type { AskResponse, ChatbotHistoryItem } from '../services/chatbotService';

export type RagChatbotStatus =
  | 'IDLE'
  | 'OPEN_IDLE'
  | 'OPEN_LOADING'
  | 'OPEN_ANSWERED'
  | 'OPEN_ERROR';

export type RagChatbotErrorKind =
  | 'SERVICE_UNAVAILABLE' // 503 or network error
  | 'QUESTION_TOO_LONG'  // 400 QUESTION_TOO_LONG
  | 'FORBIDDEN'          // 403
  | 'UNKNOWN';           // other

export interface RagChatbotState {
  status: RagChatbotStatus;

  // Current question text (live textarea value)
  question: string;

  // Last answer received
  lastAnswer: AskResponse | null;

  // Error state
  errorKind: RagChatbotErrorKind | null;
  errorMessage: string | null;

  // History panel
  history: ChatbotHistoryItem[];
  historyLoaded: boolean;
  showHistory: boolean;

  // Actions
  open: () => void;
  close: () => void;
  setQuestion: (q: string) => void;
  setLoading: () => void;
  setAnswer: (answer: AskResponse) => void;
  setError: (kind: RagChatbotErrorKind, message: string) => void;
  reset: () => void;

  // History actions
  setHistory: (items: ChatbotHistoryItem[]) => void;
  setHistoryLoaded: (loaded: boolean) => void;
  toggleHistory: () => void;
  removeHistoryItem: (id: string) => void;
  // Optimistic delete: returns the item for rollback
  optimisticRemoveHistoryItem: (id: string) => ChatbotHistoryItem | undefined;
  rollbackHistoryItem: (item: ChatbotHistoryItem) => void;
}

export const useRagChatbotStore = create<RagChatbotState>((set, get) => ({
  status: 'IDLE',
  question: '',
  lastAnswer: null,
  errorKind: null,
  errorMessage: null,
  history: [],
  historyLoaded: false,
  showHistory: false,

  open: () =>
    set((state) => ({
      status: state.status === 'IDLE' ? 'OPEN_IDLE' : state.status,
    })),

  close: () =>
    set({
      status: 'IDLE',
      showHistory: false,
    }),

  setQuestion: (q) => set({ question: q }),

  setLoading: () => set({ status: 'OPEN_LOADING' }),

  setAnswer: (answer) =>
    set({
      status: 'OPEN_ANSWERED',
      lastAnswer: answer,
      errorKind: null,
      errorMessage: null,
    }),

  setError: (kind, message) =>
    set({
      status: 'OPEN_ERROR',
      errorKind: kind,
      errorMessage: message,
    }),

  reset: () =>
    set({
      status: 'OPEN_IDLE',
      question: '',
      lastAnswer: null,
      errorKind: null,
      errorMessage: null,
    }),

  setHistory: (items) => set({ history: items }),

  setHistoryLoaded: (loaded) => set({ historyLoaded: loaded }),

  toggleHistory: () => set((state) => ({ showHistory: !state.showHistory })),

  removeHistoryItem: (id) =>
    set((state) => ({
      history: state.history.filter((item) => item.id !== id),
    })),

  optimisticRemoveHistoryItem: (id) => {
    const state = get();
    const item = state.history.find((h) => h.id === id);
    if (item) {
      set({ history: state.history.filter((h) => h.id !== id) });
    }
    return item;
  },

  rollbackHistoryItem: (item) =>
    set((state) => ({
      // Re-insert in sorted order (newest first)
      history: [item, ...state.history.filter((h) => h.id !== item.id)].sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
      ),
    })),
}));
