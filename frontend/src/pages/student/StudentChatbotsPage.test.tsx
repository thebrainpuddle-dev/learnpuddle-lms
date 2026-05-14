// src/pages/student/StudentChatbotsPage.test.tsx
//
// Comprehensive Vitest + React Testing Library test suite for StudentChatbotsPage.
//
// Covers: page heading, subtitle, loading spinner, error state, chatbot grid,
// search filter (match / no-match), navigation on card click / keyboard, and
// empty state variants (no chatbots at all vs. no search results).
//
// Mocking strategy:
//   - chatbotStudentApi is mocked at the module level so queryFn can be
//     controlled per-test via mockResolvedValue / mockRejectedValue.
//   - usePageTitle is stubbed to avoid document.title side-effects.
//   - useNavigate is hoisted so click-navigation assertions can be made.

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { StudentChatbotsPage } from './StudentChatbotsPage';

// ─── Hoist navigate mock ──────────────────────────────────────────────────────

const mockedUseNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockedUseNavigate };
});

// ─── Module mocks ─────────────────────────────────────────────────────────────

vi.mock('../../services/openmaicService', () => ({
  chatbotStudentApi: {
    list: vi.fn(),
    detail: vi.fn(),
    conversations: vi.fn(),
    createConversation: vi.fn(),
    getConversation: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ─── Import mock handle after vi.mock ─────────────────────────────────────────

import { chatbotStudentApi } from '../../services/openmaicService';

const mockedList = (chatbotStudentApi.list as ReturnType<typeof vi.fn>);

// ─── Fixtures ─────────────────────────────────────────────────────────────────

const makeChatbot = (overrides: Partial<{
  id: string;
  name: string;
  is_active: boolean;
  knowledge_count: number;
  conversation_count: number;
}> = {}) => ({
  id: 'bot-1',
  name: 'Math Tutor',
  avatar_url: '',
  persona_preset: 'study_buddy' as const,
  persona_description: 'Helps with math',
  custom_rules: '',
  block_off_topic: false,
  welcome_message: 'Hello!',
  is_active: true,
  knowledge_count: 3,
  conversation_count: 12,
  sections: [{ id: 's-1', name: 'A', grade_name: 'Grade 10', grade_short_code: 'G10' }],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  ...overrides,
});

const MOCK_CHATBOTS = [
  makeChatbot({ id: 'bot-1', name: 'Math Tutor' }),
  makeChatbot({ id: 'bot-2', name: 'Science Helper', knowledge_count: 1, conversation_count: 5 }),
  makeChatbot({ id: 'bot-3', name: 'History Guide', is_active: false, knowledge_count: 0, conversation_count: 2 }),
];

// ─── Test helpers ─────────────────────────────────────────────────────────────

const makeQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        staleTime: Infinity,
        refetchOnWindowFocus: false,
      },
    },
  });

const renderPage = () =>
  render(
    <QueryClientProvider client={makeQueryClient()}>
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <StudentChatbotsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

// ─── Suite ────────────────────────────────────────────────────────────────────

describe('StudentChatbotsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockedList.mockResolvedValue({ data: MOCK_CHATBOTS });
  });

  // ── 1. Page heading ──────────────────────────────────────────────────────────

  it('renders the "AI Tutors" page heading', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /ai tutors/i }),
    ).toBeInTheDocument();
  });

  // ── 2. Subtitle ───────────────────────────────────────────────────────────────

  it('renders the subtitle about chatting with AI tutors', async () => {
    renderPage();
    expect(
      await screen.findByText(/chat with ai tutors created by your teachers/i),
    ).toBeInTheDocument();
  });

  // ── 3. Loading state ──────────────────────────────────────────────────────────

  it('shows the loading spinner while the query is in-flight', () => {
    mockedList.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument();
  });

  it('renders the "Loading..." sr-only text inside the spinner', () => {
    mockedList.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  // ── 4. Error state ────────────────────────────────────────────────────────────

  it('shows a red error banner when the API call fails', async () => {
    mockedList.mockRejectedValue(new Error('Network error'));
    renderPage();
    expect(await screen.findByText('Network error')).toBeInTheDocument();
  });

  it('shows the fallback "Failed to load tutors" message for non-Error rejections', async () => {
    mockedList.mockRejectedValue('oops');
    renderPage();
    expect(await screen.findByText('Failed to load tutors')).toBeInTheDocument();
  });

  // ── 5. Chatbot grid ───────────────────────────────────────────────────────────

  it('renders all chatbot names in the grid', async () => {
    renderPage();
    expect(await screen.findByText('Math Tutor')).toBeInTheDocument();
    expect(await screen.findByText('Science Helper')).toBeInTheDocument();
    expect(await screen.findByText('History Guide')).toBeInTheDocument();
  });

  it('renders a card for each chatbot (correct count)', async () => {
    renderPage();
    // Each card has a role="button" wrapper div
    const cards = await screen.findAllByRole('button');
    // There should be at least 3 card-wrapper buttons (one per chatbot)
    expect(cards.length).toBeGreaterThanOrEqual(3);
  });

  // ── 6. Search filter ─────────────────────────────────────────────────────────

  it('renders the search input when chatbots are loaded', async () => {
    renderPage();
    expect(
      await screen.findByPlaceholderText(/search tutors/i),
    ).toBeInTheDocument();
  });

  it('filters the list when the user types a matching search term', async () => {
    const user = userEvent.setup();
    renderPage();

    const input = await screen.findByPlaceholderText(/search tutors/i);
    await user.type(input, 'Math');

    expect(screen.getByText('Math Tutor')).toBeInTheDocument();
    expect(screen.queryByText('Science Helper')).not.toBeInTheDocument();
    expect(screen.queryByText('History Guide')).not.toBeInTheDocument();
  });

  it('is case-insensitive when filtering', async () => {
    const user = userEvent.setup();
    renderPage();

    const input = await screen.findByPlaceholderText(/search tutors/i);
    await user.type(input, 'science');

    expect(screen.getByText('Science Helper')).toBeInTheDocument();
    expect(screen.queryByText('Math Tutor')).not.toBeInTheDocument();
  });

  it('shows "No matching tutors" when the search term has no matches', async () => {
    const user = userEvent.setup();
    renderPage();

    const input = await screen.findByPlaceholderText(/search tutors/i);
    await user.type(input, 'zzznomatch');

    expect(await screen.findByText('No matching tutors')).toBeInTheDocument();
  });

  it('shows "Try a different search term." hint when no results match', async () => {
    const user = userEvent.setup();
    renderPage();

    const input = await screen.findByPlaceholderText(/search tutors/i);
    await user.type(input, 'zzznomatch');

    expect(await screen.findByText('Try a different search term.')).toBeInTheDocument();
  });

  it('restores the full list when the search input is cleared', async () => {
    const user = userEvent.setup();
    renderPage();

    const input = await screen.findByPlaceholderText(/search tutors/i);
    await user.type(input, 'Math');
    expect(screen.queryByText('Science Helper')).not.toBeInTheDocument();

    await user.clear(input);
    expect(await screen.findByText('Science Helper')).toBeInTheDocument();
    expect(await screen.findByText('History Guide')).toBeInTheDocument();
  });

  // ── 7. Navigation on card click ───────────────────────────────────────────────

  it('navigates to the chatbot detail route when a card is clicked', async () => {
    const user = userEvent.setup();
    renderPage();

    // Find the wrapper div[role="button"] for the first chatbot
    const mathTutorTitle = await screen.findByText('Math Tutor');
    const cardWrapper = mathTutorTitle.closest('[role="button"]') as HTMLElement;
    expect(cardWrapper).not.toBeNull();

    await user.click(cardWrapper);

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/chatbots/bot-1');
  });

  it('navigates when Enter is pressed on a card', async () => {
    const user = userEvent.setup();
    renderPage();

    const mathTutorTitle = await screen.findByText('Math Tutor');
    const cardWrapper = mathTutorTitle.closest('[role="button"]') as HTMLElement;
    cardWrapper.focus();

    await user.keyboard('{Enter}');

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/chatbots/bot-1');
  });

  it('navigates when Space is pressed on a card', async () => {
    const user = userEvent.setup();
    renderPage();

    const mathTutorTitle = await screen.findByText('Math Tutor');
    const cardWrapper = mathTutorTitle.closest('[role="button"]') as HTMLElement;
    cardWrapper.focus();

    await user.keyboard(' ');

    expect(mockedUseNavigate).toHaveBeenCalledWith('/student/chatbots/bot-1');
  });

  // ── 8. Empty state (no chatbots at all) ───────────────────────────────────────

  it('shows "No tutors available" when the API returns an empty array', async () => {
    mockedList.mockResolvedValue({ data: [] });
    renderPage();
    expect(await screen.findByText('No tutors available')).toBeInTheDocument();
  });

  it('hides the search input when no chatbots are loaded', async () => {
    mockedList.mockResolvedValue({ data: [] });
    renderPage();

    await screen.findByText('No tutors available');
    expect(screen.queryByPlaceholderText(/search tutors/i)).not.toBeInTheDocument();
  });

  it('shows the "teachers haven\'t created any tutors" hint in the empty state', async () => {
    mockedList.mockResolvedValue({ data: [] });
    renderPage();
    expect(
      await screen.findByText(/your teachers haven't created any tutors/i),
    ).toBeInTheDocument();
  });

  // ── 9. chatbotStudentApi.list is called once on mount ─────────────────────────

  it('calls chatbotStudentApi.list exactly once when the component mounts', async () => {
    renderPage();
    await screen.findByText('Math Tutor');
    expect(mockedList).toHaveBeenCalledTimes(1);
  });

  // ── 10. Inactive chatbot is still rendered ────────────────────────────────────

  it('renders an inactive chatbot card in the grid', async () => {
    renderPage();
    // 'History Guide' has is_active: false but should still appear
    expect(await screen.findByText('History Guide')).toBeInTheDocument();
  });
});
