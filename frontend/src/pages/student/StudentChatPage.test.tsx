// src/pages/student/StudentChatPage.test.tsx
//
// Vitest + React Testing Library suite for StudentChatPage.
//
// Covers: header elements, chatbot loading / loaded / not-found states,
// conversation sidebar (empty / list / active selection), new conversation
// button, sidebar open/close toggle, back navigation, and ChatbotChat mounting.
//
// Mocking strategy:
//   - chatbotStudentApi (detail + conversations) controlled per-test.
//   - ChatbotChat is stubbed with a sentinel that exposes its props so we can
//     verify chatbotId, conversationId, and welcomeMessage are passed correctly.
//   - usePageTitle is stubbed to avoid document.title side-effects.
//   - useNavigate is hoisted for navigation assertions.
//   - useParams is hoisted to inject a chatbotId via MemoryRouter initialEntries.

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { StudentChatPage } from './StudentChatPage';

// ─── Hoist navigate mock ──────────────────────────────────────────────────────

const mockedUseNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockedUseNavigate };
});

// ─── Module mocks ─────────────────────────────────────────────────────────────

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

vi.mock('../../services/openmaicService', () => ({
  chatbotStudentApi: {
    list: vi.fn(),
    detail: vi.fn(),
    conversations: vi.fn(),
    createConversation: vi.fn(),
    getConversation: vi.fn(),
  },
}));

// Stub ChatbotChat: renders its key props as data attributes so tests can assert them.
vi.mock('../../components/maic/ChatbotChat', () => ({
  ChatbotChat: ({
    chatbotId,
    conversationId,
    welcomeMessage,
    onConversationCreated,
  }: {
    chatbotId: string;
    conversationId: string | null;
    welcomeMessage: string;
    onConversationCreated: (id: string) => void;
  }) => (
    <div
      data-testid="chatbot-chat"
      data-chatbot-id={chatbotId}
      data-conversation-id={conversationId ?? 'null'}
      data-welcome-message={welcomeMessage}
    >
      <button
        type="button"
        data-testid="chat-conv-created"
        onClick={() => onConversationCreated('new-conv-99')}
      >
        Simulate conv created
      </button>
    </div>
  ),
}));

// ─── Import mock handles after vi.mock ────────────────────────────────────────

import { chatbotStudentApi } from '../../services/openmaicService';
import type { AIChatbot } from '../../types/chatbot';
import type { ConversationListItem } from '../../types/chatbot';

const mockedDetail = chatbotStudentApi.detail as ReturnType<typeof vi.fn>;
const mockedConversations = chatbotStudentApi.conversations as ReturnType<typeof vi.fn>;

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const CHATBOT_ID = 'bot-42';

const makeChatbot = (overrides: Partial<AIChatbot> = {}): AIChatbot => ({
  id: CHATBOT_ID,
  name: 'Physics Tutor',
  avatar_url: '',
  persona_preset: 'concept_explainer',
  persona_description: 'Explains physics concepts',
  custom_rules: '',
  block_off_topic: false,
  welcome_message: 'Hello from Physics Tutor!',
  is_active: true,
  knowledge_count: 2,
  conversation_count: 5,
  sections: [],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  ...overrides,
});

const makeConversation = (overrides: Partial<ConversationListItem> = {}): ConversationListItem => ({
  id: 'conv-1',
  title: 'Wave mechanics discussion',
  message_count: 4,
  is_flagged: false,
  started_at: '2026-04-25T10:00:00Z',
  last_message_at: '2026-04-25T10:05:00Z',
  ...overrides,
});

const MOCK_CONVERSATIONS: ConversationListItem[] = [
  makeConversation({ id: 'conv-1', title: 'Wave mechanics discussion', message_count: 4 }),
  makeConversation({ id: 'conv-2', title: 'Newton laws review', message_count: 7 }),
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });

/**
 * Renders StudentChatPage with the chatbotId injected via MemoryRouter params.
 */
const renderPage = (chatbotId = CHATBOT_ID) =>
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter initialEntries={[`/student/chatbots/${chatbotId}`]}>
        <Routes>
          <Route path="/student/chatbots/:id" element={<StudentChatPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );

// ─── Suite ────────────────────────────────────────────────────────────────────

describe('StudentChatPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedDetail.mockResolvedValue({ data: makeChatbot() });
    mockedConversations.mockResolvedValue({ data: MOCK_CONVERSATIONS });
  });

  // ── 1. Loading state — chatbot ─────────────────────────────────────────────

  it('shows a loading indicator in the header while the chatbot is being fetched', () => {
    mockedDetail.mockReturnValue(new Promise(() => {}));
    mockedConversations.mockResolvedValue({ data: [] });
    renderPage();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  // ── 2. "All Tutors" back link ──────────────────────────────────────────────

  it('renders the "All Tutors" back button', async () => {
    renderPage();
    expect(await screen.findByText(/all tutors/i)).toBeInTheDocument();
  });

  it('navigates to /student/chatbots when "All Tutors" is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    const backBtn = await screen.findByText(/all tutors/i);
    await user.click(backBtn);

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/chatbots');
  });

  // ── 3. Chatbot name in header ──────────────────────────────────────────────

  it('renders the chatbot name in the header after data loads', async () => {
    renderPage();
    expect(await screen.findByText('Physics Tutor')).toBeInTheDocument();
  });

  // ── 4. Chatbot not found ───────────────────────────────────────────────────

  it('shows "Tutor not found" when the chatbot query resolves to null/undefined', async () => {
    mockedDetail.mockResolvedValue({ data: null });
    renderPage();
    // The component renders the "Tutor not found" message in two places (header
    // status label + empty-state body), so use findAllByText to avoid the
    // "multiple elements" error and assert at least one is present.
    const matches = await screen.findAllByText(/tutor not found/i);
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  // ── 5. Conversations sidebar heading ──────────────────────────────────────

  it('renders the "Conversations" sidebar heading', async () => {
    renderPage();
    expect(await screen.findByText(/conversations/i)).toBeInTheDocument();
  });

  // ── 6. Conversation list items ─────────────────────────────────────────────

  it('renders each conversation title in the sidebar', async () => {
    renderPage();
    expect(await screen.findByText('Wave mechanics discussion')).toBeInTheDocument();
    expect(await screen.findByText('Newton laws review')).toBeInTheDocument();
  });

  it('shows message counts for each conversation', async () => {
    renderPage();
    expect(await screen.findByText(/4 msgs/i)).toBeInTheDocument();
    expect(await screen.findByText(/7 msgs/i)).toBeInTheDocument();
  });

  // ── 7. Conversations empty state ──────────────────────────────────────────

  it('shows the empty-conversations message when there are no conversations', async () => {
    mockedConversations.mockResolvedValue({ data: [] });
    renderPage();
    expect(
      await screen.findByText(/no conversations yet\. start chatting below!/i),
    ).toBeInTheDocument();
  });

  // ── 8. Selecting a conversation ───────────────────────────────────────────

  it('marks a conversation as active when clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    const convButton = await screen.findByText('Wave mechanics discussion');
    await user.click(convButton);

    // After clicking, the ChatbotChat stub should receive the conversation id
    await waitFor(() => {
      const chat = screen.getByTestId('chatbot-chat');
      expect(chat).toHaveAttribute('data-conversation-id', 'conv-1');
    });
  });

  // ── 9. New conversation button ─────────────────────────────────────────────

  it('renders the new-conversation button in the sidebar header', async () => {
    renderPage();
    // button title="New conversation"
    await waitFor(() => {
      expect(
        screen.getByTitle('New conversation'),
      ).toBeInTheDocument();
    });
  });

  it('clears the active conversation when the new-conversation button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    // First select a conversation
    const convButton = await screen.findByText('Wave mechanics discussion');
    await user.click(convButton);

    await waitFor(() => {
      expect(screen.getByTestId('chatbot-chat')).toHaveAttribute('data-conversation-id', 'conv-1');
    });

    // Then click new conversation
    await user.click(screen.getByTitle('New conversation'));

    await waitFor(() => {
      expect(screen.getByTestId('chatbot-chat')).toHaveAttribute('data-conversation-id', 'null');
    });
  });

  // ── 10. Sidebar toggle ────────────────────────────────────────────────────

  it('hides the sidebar when the close-sidebar button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    // Wait for sidebar to be visible
    await screen.findByText(/conversations/i);

    await user.click(screen.getByTitle('Close sidebar'));

    expect(screen.queryByText(/conversations/i)).not.toBeInTheDocument();
  });

  it('shows the open-sidebar button when the sidebar is closed', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByTitle('Close sidebar');
    await user.click(screen.getByTitle('Close sidebar'));

    expect(await screen.findByTitle('Show conversations')).toBeInTheDocument();
  });

  it('re-opens the sidebar when the show-conversations button is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByTitle('Close sidebar');
    await user.click(screen.getByTitle('Close sidebar'));

    // sidebar heading gone
    expect(screen.queryByText(/conversations/i)).not.toBeInTheDocument();

    await user.click(screen.getByTitle('Show conversations'));

    expect(await screen.findByText(/conversations/i)).toBeInTheDocument();
  });

  // ── 11. ChatbotChat receives correct props ────────────────────────────────

  it('mounts ChatbotChat with the correct chatbotId and welcomeMessage', async () => {
    renderPage();

    await waitFor(() => {
      const chat = screen.getByTestId('chatbot-chat');
      expect(chat).toHaveAttribute('data-chatbot-id', CHATBOT_ID);
      expect(chat).toHaveAttribute('data-welcome-message', 'Hello from Physics Tutor!');
    });
  });

  it('uses a fallback welcome message when chatbot.welcome_message is empty', async () => {
    mockedDetail.mockResolvedValue({
      data: makeChatbot({ welcome_message: '', name: 'Physics Tutor' }),
    });
    renderPage();

    await waitFor(() => {
      const chat = screen.getByTestId('chatbot-chat');
      expect(chat).toHaveAttribute(
        'data-welcome-message',
        "Hi! I'm Physics Tutor. How can I help you?",
      );
    });
  });

  // ── 12. onConversationCreated updates active conversation ─────────────────

  it('updates the active conversation when ChatbotChat fires onConversationCreated', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByTestId('chatbot-chat');
    await user.click(screen.getByTestId('chat-conv-created'));

    await waitFor(() => {
      expect(screen.getByTestId('chatbot-chat')).toHaveAttribute(
        'data-conversation-id',
        'new-conv-99',
      );
    });
  });
});
