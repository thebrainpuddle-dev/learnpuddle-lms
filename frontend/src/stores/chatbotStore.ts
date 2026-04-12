// stores/chatbotStore.ts — Zustand store for AI Chatbot Builder + Student Chat

import { create } from 'zustand';
import type {
  AIChatbot,
  AIChatbotKnowledge,
  ChatMessage,
  Conversation,
  ConversationListItem,
  ChatSSEEvent,
} from '../types/chatbot';

interface ChatbotState {
  // Teacher: chatbot CRUD
  chatbots: AIChatbot[];
  selectedChatbot: AIChatbot | null;
  isLoading: boolean;
  error: string | null;

  // Teacher: knowledge
  knowledge: AIChatbotKnowledge[];
  isUploadingKnowledge: boolean;

  // Student: available chatbots
  availableChatbots: AIChatbot[];

  // Chat state (shared between teacher preview and student)
  activeConversation: Conversation | null;
  conversations: ConversationListItem[];
  isStreaming: boolean;
  streamingContent: string;

  // Actions: Teacher
  setChatbots: (chatbots: AIChatbot[]) => void;
  setSelectedChatbot: (chatbot: AIChatbot | null) => void;
  addChatbot: (chatbot: AIChatbot) => void;
  updateChatbot: (chatbot: AIChatbot) => void;
  removeChatbot: (id: string) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;

  // Actions: Knowledge
  setKnowledge: (knowledge: AIChatbotKnowledge[]) => void;
  addKnowledge: (item: AIChatbotKnowledge) => void;
  removeKnowledge: (id: string) => void;
  updateKnowledgeStatus: (id: string, status: AIChatbotKnowledge['embedding_status']) => void;
  setUploadingKnowledge: (uploading: boolean) => void;

  // Actions: Student
  setAvailableChatbots: (chatbots: AIChatbot[]) => void;

  // Actions: Chat
  setConversations: (conversations: ConversationListItem[]) => void;
  setActiveConversation: (conversation: Conversation | null) => void;
  appendMessage: (message: ChatMessage) => void;
  updateLastAssistantMessage: (content: string) => void;
  setStreaming: (streaming: boolean) => void;
  setStreamingContent: (content: string) => void;
  clearChat: () => void;
}

export const useChatbotStore = create<ChatbotState>((set, get) => ({
  // Initial state
  chatbots: [],
  selectedChatbot: null,
  isLoading: false,
  error: null,
  knowledge: [],
  isUploadingKnowledge: false,
  availableChatbots: [],
  activeConversation: null,
  conversations: [],
  isStreaming: false,
  streamingContent: '',

  // Teacher CRUD
  setChatbots: (chatbots) => set({ chatbots }),
  setSelectedChatbot: (chatbot) => set({ selectedChatbot: chatbot }),
  addChatbot: (chatbot) =>
    set((state) => ({ chatbots: [chatbot, ...state.chatbots] })),
  updateChatbot: (chatbot) =>
    set((state) => ({
      chatbots: state.chatbots.map((c) => (c.id === chatbot.id ? chatbot : c)),
      selectedChatbot:
        state.selectedChatbot?.id === chatbot.id ? chatbot : state.selectedChatbot,
    })),
  removeChatbot: (id) =>
    set((state) => ({
      chatbots: state.chatbots.filter((c) => c.id !== id),
      selectedChatbot: state.selectedChatbot?.id === id ? null : state.selectedChatbot,
    })),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error }),

  // Knowledge
  setKnowledge: (knowledge) => set({ knowledge }),
  addKnowledge: (item) =>
    set((state) => ({ knowledge: [item, ...state.knowledge] })),
  removeKnowledge: (id) =>
    set((state) => ({
      knowledge: state.knowledge.filter((k) => k.id !== id),
    })),
  updateKnowledgeStatus: (id, status) =>
    set((state) => ({
      knowledge: state.knowledge.map((k) =>
        k.id === id ? { ...k, embedding_status: status } : k
      ),
    })),
  setUploadingKnowledge: (isUploadingKnowledge) => set({ isUploadingKnowledge }),

  // Student
  setAvailableChatbots: (availableChatbots) => set({ availableChatbots }),

  // Chat
  setConversations: (conversations) => set({ conversations }),
  setActiveConversation: (activeConversation) => set({ activeConversation }),
  appendMessage: (message) =>
    set((state) => {
      if (!state.activeConversation) return state;
      return {
        activeConversation: {
          ...state.activeConversation,
          messages: [...state.activeConversation.messages, message],
          message_count: state.activeConversation.message_count + 1,
        },
      };
    }),
  updateLastAssistantMessage: (content) =>
    set((state) => {
      if (!state.activeConversation) return state;
      const msgs = [...state.activeConversation.messages];
      const lastIdx = msgs.length - 1;
      if (lastIdx >= 0 && msgs[lastIdx].role === 'assistant') {
        msgs[lastIdx] = { ...msgs[lastIdx], content };
      }
      return {
        activeConversation: { ...state.activeConversation, messages: msgs },
        streamingContent: content,
      };
    }),
  setStreaming: (isStreaming) => set({ isStreaming }),
  setStreamingContent: (streamingContent) => set({ streamingContent }),
  clearChat: () =>
    set({
      activeConversation: null,
      streamingContent: '',
      isStreaming: false,
    }),
}));
