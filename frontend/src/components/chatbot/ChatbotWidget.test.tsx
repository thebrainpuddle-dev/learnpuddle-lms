// src/components/chatbot/ChatbotWidget.test.tsx
//
// Tests for the RAG-backed chatbot widget (TASK-061).
// Runner: Vitest + @testing-library/react + happy-dom

import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { ChatbotLauncher } from './ChatbotLauncher';
import { ChatbotMessage } from './ChatbotMessage';
import { ChatbotHistory } from './ChatbotHistory';
import { chatbotService } from '../../services/chatbotService';
import { useRagChatbotStore } from '../../stores/ragChatbotStore';
import type { AskResponse, ChatbotHistoryItem } from '../../services/chatbotService';

// ─── Mocks ────────────────────────────────────────────────────────────────────
vi.mock('../../services/chatbotService', () => ({
  chatbotService: {
    askQuestion: vi.fn(),
    getHistory: vi.fn(),
    deleteHistoryItem: vi.fn(),
  },
}));

// Module-scope toast mock so tests can assert on toast calls.
const toastCalls = { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn(), showToast: vi.fn() };
vi.mock('../common', async () => {
  const actual = await vi.importActual<typeof import('../common')>('../common');
  return {
    ...actual,
    useToast: () => toastCalls,
  };
});

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// ─── Helpers ─────────────────────────────────────────────────────────────────

function resetStore() {
  useRagChatbotStore.setState({
    status: 'IDLE',
    question: '',
    lastAnswer: null,
    errorKind: null,
    errorMessage: null,
    history: [],
    historyLoaded: false,
    showHistory: false,
  });
}

function renderLauncher(courseId = 'course-abc') {
  return render(
    <MemoryRouter>
      <ChatbotLauncher courseId={courseId} />
    </MemoryRouter>,
  );
}

const happyAnswer: AskResponse = {
  query_id: 'q-1',
  answer: 'The answer is 42. See [1] for details.',
  citations: [
    { block: 1, source_type: 'content', source_id: 'content-x', title: 'Lesson 1', score: 0.9 },
  ],
  grounded: true,
};

const ungroundedAnswer: AskResponse = {
  query_id: 'q-2',
  answer: 'I could not find specific information about this topic.',
  citations: [],
  grounded: false,
};

const historyItems: ChatbotHistoryItem[] = [
  {
    id: 'hist-1',
    course_id: 'course-abc',
    answer: 'This is a previous answer about something important.',
    citations: [],
    grounded: true,
    provider: 'openrouter',
    model: 'gpt-4o',
    tokens_prompt: 100,
    tokens_completion: 50,
    latency_ms: 1200,
    created_at: new Date(Date.now() - 60_000).toISOString(),
  },
];

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ChatbotWidget — open/close panel', () => {
  beforeEach(() => {
    resetStore();
    vi.resetAllMocks();
    (chatbotService.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
  });

  // TEST 1: open panel
  it('opens the panel when launcher is clicked', async () => {
    renderLauncher();
    expect(screen.queryByTestId('chatbot-panel')).not.toBeInTheDocument();

    await userEvent.click(screen.getByTestId('chatbot-launcher'));

    expect(await screen.findByTestId('chatbot-panel')).toBeInTheDocument();
  });

  // TEST 2: close panel via X button
  it('closes the panel when close button is clicked', async () => {
    renderLauncher();

    await userEvent.click(screen.getByTestId('chatbot-launcher'));
    expect(await screen.findByTestId('chatbot-panel')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /close q&a assistant/i }));

    await waitFor(() => {
      expect(screen.queryByTestId('chatbot-panel')).not.toBeInTheDocument();
    });
  });
});

describe('ChatbotWidget — submit happy path', () => {
  beforeEach(() => {
    resetStore();
    vi.resetAllMocks();
    (chatbotService.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    (chatbotService.askQuestion as ReturnType<typeof vi.fn>).mockResolvedValue(happyAnswer);
  });

  // TEST 3: happy path submit
  it('submits question and renders answer card', async () => {
    renderLauncher('course-abc');

    await userEvent.click(screen.getByTestId('chatbot-launcher'));
    const textarea = await screen.findByRole('textbox', { name: /question input/i });

    await userEvent.type(textarea, 'What is the main topic?');
    await userEvent.click(screen.getByRole('button', { name: /submit question/i }));

    await waitFor(() => {
      expect(chatbotService.askQuestion).toHaveBeenCalledWith({
        question: 'What is the main topic?',
        course_id: 'course-abc',
        top_k: 5,
      });
    });

    expect(await screen.findByTestId('chatbot-answer-card')).toBeInTheDocument();
    expect(screen.getByText(/The answer is 42/)).toBeInTheDocument();
  });
});

describe('ChatbotWidget — 2000-char cap validation', () => {
  beforeEach(() => {
    resetStore();
    vi.resetAllMocks();
    (chatbotService.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
  });

  // TEST 4: 2000-char validation — use fireEvent for performance (avoids 2001 keystrokes)
  it('disables submit and turns counter red when question exceeds 2000 chars', async () => {
    const { fireEvent } = await import('@testing-library/react');

    renderLauncher();

    await userEvent.click(screen.getByTestId('chatbot-launcher'));
    const textarea = await screen.findByRole('textbox', { name: /question input/i });

    // Directly fire a change event with a 2001-char string (much faster than userEvent.type)
    const longText = 'a'.repeat(2001);
    fireEvent.change(textarea, { target: { value: longText } });

    const submitBtn = screen.getByRole('button', { name: /submit question/i });
    expect(submitBtn).toBeDisabled();

    const counter = screen.getByLabelText(/characters used/i);
    expect(counter).toHaveClass('text-red-500');
  });
});

describe('ChatbotWidget — 403 FORBIDDEN error', () => {
  beforeEach(() => {
    resetStore();
    vi.resetAllMocks();
    (chatbotService.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
  });

  // TEST 4b: 403 FORBIDDEN shows the correct user-facing error message
  it('shows "No access to this course\'s assistant" on 403 FORBIDDEN', async () => {
    const err = { response: { status: 403, data: { error: 'FORBIDDEN' } } };
    (chatbotService.askQuestion as ReturnType<typeof vi.fn>).mockRejectedValue(err);

    renderLauncher('course-abc');
    await userEvent.click(screen.getByTestId('chatbot-launcher'));

    const textarea = await screen.findByRole('textbox', { name: /question input/i });
    await userEvent.type(textarea, 'Am I allowed?');
    await userEvent.click(screen.getByRole('button', { name: /submit question/i }));

    expect(
      await screen.findByText(/no access to this course's assistant/i),
    ).toBeInTheDocument();

    // Retry button should NOT appear for FORBIDDEN (not retryable)
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument();
  });
});

describe('ChatbotWidget — 503 error + retry', () => {
  beforeEach(() => {
    resetStore();
    vi.resetAllMocks();
    (chatbotService.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
  });

  // TEST 5: 503 error card + retry button
  it('shows error card with retry button on 503 error', async () => {
    const err = { response: { status: 503, data: { error: 'SERVICE_UNAVAILABLE' } } };
    (chatbotService.askQuestion as ReturnType<typeof vi.fn>).mockRejectedValue(err);

    renderLauncher('course-abc');
    await userEvent.click(screen.getByTestId('chatbot-launcher'));

    const textarea = await screen.findByRole('textbox', { name: /question input/i });
    await userEvent.type(textarea, 'Will this fail?');
    await userEvent.click(screen.getByRole('button', { name: /submit question/i }));

    expect(await screen.findByText(/chatbot temporarily unavailable/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  // TEST 6: retry submits the same question again
  it('retry button resubmits the same question', async () => {
    const err = { response: { status: 503, data: {} } };
    (chatbotService.askQuestion as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(err)
      .mockResolvedValueOnce(happyAnswer);

    renderLauncher('course-abc');
    await userEvent.click(screen.getByTestId('chatbot-launcher'));

    const textarea = await screen.findByRole('textbox', { name: /question input/i });
    await userEvent.type(textarea, 'Will retry work?');
    await userEvent.click(screen.getByRole('button', { name: /submit question/i }));

    await screen.findByText(/chatbot temporarily unavailable/i);
    await userEvent.click(screen.getByRole('button', { name: /retry/i }));

    await waitFor(() => {
      expect(chatbotService.askQuestion).toHaveBeenCalledTimes(2);
    });

    expect(await screen.findByTestId('chatbot-answer-card')).toBeInTheDocument();
  });
});

describe('ChatbotWidget — citation chip navigation', () => {
  beforeEach(() => {
    resetStore();
    vi.resetAllMocks();
    mockNavigate.mockClear();
  });

  // TEST 7: citation chip click navigates
  it('clicking a citation chip navigates to the correct content URL', async () => {
    render(
      <MemoryRouter>
        <ChatbotMessage answer={happyAnswer} courseId="course-abc" />
      </MemoryRouter>,
    );

    // The chip in the sources section
    const chips = screen.getAllByRole('button', { name: /go to citation 1/i });
    expect(chips.length).toBeGreaterThan(0);
    await userEvent.click(chips[0]);

    expect(mockNavigate).toHaveBeenCalledWith(
      '/teacher/courses/course-abc/contents/content-x',
    );
  });
});

describe('ChatbotWidget — history load on open', () => {
  beforeEach(() => {
    resetStore();
    vi.resetAllMocks();
  });

  // TEST 8: history loads when panel opens
  it('loads history when the panel is opened', async () => {
    (chatbotService.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: historyItems,
      total: 1,
      page: 1,
      page_size: 20,
    });

    renderLauncher('course-abc');
    await userEvent.click(screen.getByTestId('chatbot-launcher'));
    await screen.findByTestId('chatbot-panel');

    // Toggle history sidebar
    await userEvent.click(screen.getByRole('button', { name: /show question history/i }));

    await waitFor(() => {
      expect(chatbotService.getHistory).toHaveBeenCalledWith(20);
    });

    expect(await screen.findByText(/This is a previous answer/i)).toBeInTheDocument();
  });
});

describe('ChatbotWidget — history delete optimistic + rollback', () => {
  beforeEach(() => {
    resetStore();
    vi.resetAllMocks();
    useRagChatbotStore.setState({
      history: historyItems,
      historyLoaded: true,
    });
    // Reset toast spy counters between tests
    toastCalls.error.mockClear();
  });

  // TEST 9: optimistic delete removes item immediately
  it('optimistically removes history item on delete', async () => {
    (chatbotService.deleteHistoryItem as ReturnType<typeof vi.fn>).mockResolvedValue(undefined);
    (chatbotService.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: historyItems,
      total: 1,
      page: 1,
      page_size: 20,
    });

    renderLauncher('course-abc');
    await userEvent.click(screen.getByTestId('chatbot-launcher'));
    await screen.findByTestId('chatbot-panel');

    await userEvent.click(screen.getByRole('button', { name: /show question history/i }));

    const deleteBtn = await screen.findByRole('button', { name: /delete this query/i });
    await userEvent.click(deleteBtn);

    await waitFor(() => {
      expect(chatbotService.deleteHistoryItem).toHaveBeenCalledWith('hist-1');
    });
  });

  // TEST 10: rollback on delete failure
  it('rolls back optimistic delete when API call fails', async () => {
    (chatbotService.deleteHistoryItem as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Server error'),
    );
    (chatbotService.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: historyItems,
      total: 1,
      page: 1,
      page_size: 20,
    });

    renderLauncher('course-abc');
    await userEvent.click(screen.getByTestId('chatbot-launcher'));
    await screen.findByTestId('chatbot-panel');

    await userEvent.click(screen.getByRole('button', { name: /show question history/i }));

    const deleteBtn = await screen.findByRole('button', { name: /delete this query/i });
    await userEvent.click(deleteBtn);

    // After failure, item should be restored
    await waitFor(() => {
      const state = useRagChatbotStore.getState();
      expect(state.history.some((h) => h.id === 'hist-1')).toBe(true);
    });
  });

  // TEST 10b: toast fires on delete failure (TASK-061 M1)
  it('shows error toast with retry copy when delete API call fails', async () => {
    (chatbotService.deleteHistoryItem as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Server error'),
    );
    (chatbotService.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: historyItems,
      total: 1,
      page: 1,
      page_size: 20,
    });

    renderLauncher('course-abc');
    await userEvent.click(screen.getByTestId('chatbot-launcher'));
    await screen.findByTestId('chatbot-panel');

    await userEvent.click(screen.getByRole('button', { name: /show question history/i }));

    const deleteBtn = await screen.findByRole('button', { name: /delete this query/i });
    await userEvent.click(deleteBtn);

    // Item is rolled back AND an error toast is fired with the expected copy
    await waitFor(() => {
      const state = useRagChatbotStore.getState();
      expect(state.history.some((h) => h.id === 'hist-1')).toBe(true);
    });
    expect(toastCalls.error).toHaveBeenCalledWith("Couldn't delete — please retry");
  });
});

describe('ChatbotWidget — keyboard navigation', () => {
  beforeEach(() => {
    resetStore();
    vi.resetAllMocks();
    (chatbotService.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    (chatbotService.askQuestion as ReturnType<typeof vi.fn>).mockResolvedValue(happyAnswer);
  });

  // TEST 11: Enter submits the question
  it('pressing Enter in the textarea submits the question', async () => {
    renderLauncher('course-abc');

    await userEvent.click(screen.getByTestId('chatbot-launcher'));
    const textarea = await screen.findByRole('textbox', { name: /question input/i });

    await userEvent.type(textarea, 'Enter-submit test{Enter}');

    await waitFor(() => {
      expect(chatbotService.askQuestion).toHaveBeenCalled();
    });
  });

  // TEST 12: Esc closes the panel
  it('pressing Escape closes the panel', async () => {
    renderLauncher();

    await userEvent.click(screen.getByTestId('chatbot-launcher'));
    const panel = await screen.findByTestId('chatbot-panel');

    await act(async () => {
      panel.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });

    await waitFor(() => {
      expect(screen.queryByTestId('chatbot-panel')).not.toBeInTheDocument();
    });
  });
});

describe('ChatbotWidget — grounded=false fallback card', () => {
  // TEST 13: ungrounded answer shows fallback UI
  it('renders fallback card with helper text when grounded=false', () => {
    render(
      <MemoryRouter>
        <ChatbotMessage answer={ungroundedAnswer} courseId="course-abc" />
      </MemoryRouter>,
    );

    expect(
      screen.getByText(/not enough context — try rephrasing/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/low confidence — limited source material found/i),
    ).toBeInTheDocument();
  });
});

describe('ChatbotWidget — loading state', () => {
  beforeEach(() => {
    resetStore();
    vi.resetAllMocks();
    (chatbotService.getHistory as ReturnType<typeof vi.fn>).mockResolvedValue({
      results: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
  });

  // TEST 14: spinner shown + input disabled during loading
  it('shows spinner and disables textarea while loading', async () => {
    // Never resolve so we stay in loading state
    (chatbotService.askQuestion as ReturnType<typeof vi.fn>).mockReturnValue(
      new Promise(() => {}),
    );

    renderLauncher('course-abc');
    await userEvent.click(screen.getByTestId('chatbot-launcher'));

    const textarea = await screen.findByRole('textbox', { name: /question input/i });
    await userEvent.type(textarea, 'Loading state check');

    const submitBtn = screen.getByRole('button', { name: /submit question/i });
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: /question input/i })).toBeDisabled();
    });
    expect(submitBtn).toBeDisabled();
  });
});

describe('ChatbotHistory component', () => {
  // TEST 15: ChatbotHistory renders items
  it('renders history items correctly', () => {
    render(
      <MemoryRouter>
        <ChatbotHistory
          items={historyItems}
          isLoading={false}
          onDelete={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText(/This is a previous answer/i)).toBeInTheDocument();
  });

  it('renders empty state when no items', () => {
    render(
      <MemoryRouter>
        <ChatbotHistory items={[]} isLoading={false} onDelete={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.getByText(/no recent questions/i)).toBeInTheDocument();
  });

  it('renders loading spinner when isLoading=true', () => {
    render(
      <MemoryRouter>
        <ChatbotHistory items={[]} isLoading={true} onDelete={vi.fn()} />
      </MemoryRouter>,
    );

    expect(screen.getByLabelText(/loading history/i)).toBeInTheDocument();
  });
});

describe('ChatbotWidget — unknown source_type citation chip (TASK-061 L4)', () => {
  // TEST L4: citation with unknown source_type renders a non-clickable span, not an anchor/button
  it('renders a non-clickable span (not a link/button) for source_type "bogus"', () => {
    const answerWithBogusSource: AskResponse = {
      answer: 'Some answer [1]',
      grounded: true,
      citations: [
        {
          source_type: 'bogus' as any,
          source_id: 'bogus-id',
          title: 'Bogus source',
          relevance: 0.5,
        },
      ],
    };

    render(
      <MemoryRouter>
        <ChatbotMessage answer={answerWithBogusSource} courseId="course-abc" />
      </MemoryRouter>,
    );

    // The chip renders in two places: once inline in the answer text and once
    // in the Sources section. Both must be non-clickable spans.
    const chips = screen.getAllByTestId('citation-chip-unknown-0');
    expect(chips.length).toBeGreaterThanOrEqual(1);

    chips.forEach((chip) => {
      // Must NOT be a button or anchor (i.e., not clickable navigation)
      expect(chip.tagName).not.toBe('BUTTON');
      expect(chip.tagName).not.toBe('A');
      expect(chip.tagName).toBe('SPAN');
    });

    // No navigation should be triggered even if role="button" is somehow present
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });
});
