// src/pages/teacher/ChatbotListPage.test.tsx
//
// FE-058: Tests for the Teacher AI Tutors (ChatbotListPage).
// Covers: page header, loading spinner, error state, chatbot grid via ChatbotCard stubs,
//         "No tutors yet" empty state, "New Tutor" navigation, search filtering,
//         section filter dropdown, delete flow (ConfirmDialog → chatbotApi.delete → removeChatbot),
//         clone flow (chatbotApi.clone → addChatbot → success toast).
//
// Mocking strategy:
//   - chatbotApi (list, delete, clone) via vi.mock('../../services/openmaicService')
//   - Real Zustand chatbotStore, reset via useChatbotStore.setState() in beforeEach
//   - ChatbotCard stubbed to expose Delete/Clone trigger buttons
//   - ConfirmDialog stubbed as minimal confirm/cancel UI
//   - useToast mocked via importOriginal spread
//   - useNavigate mocked via importOriginal spread
//   - usePageTitle stubbed

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChatbotListPage } from './ChatbotListPage';
import { useChatbotStore } from '../../stores/chatbotStore';
import type { AIChatbot } from '../../types/chatbot';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/openmaicService', () => ({
  chatbotApi: {
    list: vi.fn(),
    delete: vi.fn(),
    clone: vi.fn(),
  },
}));

// Stub ChatbotCard to expose Delete/Clone callbacks
vi.mock('../../components/maic/ChatbotCard', () => ({
  ChatbotCard: ({
    chatbot,
    onDelete,
    onClone,
  }: {
    chatbot: AIChatbot;
    onDelete: (id: string) => void;
    onClone: (id: string) => void;
  }) => (
    <div data-testid={`chatbot-card-${chatbot.id}`}>
      <span>{chatbot.name}</span>
      <button onClick={() => onDelete(chatbot.id)}>Delete</button>
      <button onClick={() => onClone(chatbot.id)}>Clone</button>
    </div>
  ),
}));

// Stub ConfirmDialog
vi.mock('../../components/common/ConfirmDialog', () => ({
  ConfirmDialog: ({
    isOpen,
    onConfirm,
    onClose,
    title,
  }: {
    isOpen: boolean;
    onConfirm: () => void;
    onClose: () => void;
    title: string;
  }) =>
    isOpen ? (
      <div data-testid="confirm-dialog">
        <p>{title}</p>
        <button onClick={onConfirm}>Confirm</button>
        <button onClick={onClose}>Cancel</button>
      </div>
    ) : null,
}));

const mockToast = { error: vi.fn(), success: vi.fn(), info: vi.fn() };
vi.mock('../../components/common', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../components/common')>();
  return { ...actual, useToast: () => mockToast };
});

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { chatbotApi } from '../../services/openmaicService';
const mockList = chatbotApi.list as ReturnType<typeof vi.fn>;
const mockDelete = chatbotApi.delete as ReturnType<typeof vi.fn>;
const mockClone = chatbotApi.clone as ReturnType<typeof vi.fn>;

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeBot(overrides: Partial<AIChatbot> = {}): AIChatbot {
  return {
    id: 'bot-1',
    name: 'Math Tutor',
    avatar_url: '',
    persona_preset: 'FRIENDLY' as AIChatbot['persona_preset'],
    persona_description: '',
    custom_rules: '',
    block_off_topic: false,
    welcome_message: 'Hi there!',
    is_active: true,
    knowledge_count: 0,
    conversation_count: 0,
    sections: [],
    created_at: '2024-01-01T00:00:00Z',
    updated_at: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

const bot1 = makeBot({ id: 'bot-1', name: 'Math Tutor' });
const bot2 = makeBot({
  id: 'bot-2',
  name: 'Science Tutor',
  sections: [{ id: 'sec-1', name: 'A', grade_name: 'Grade 5', grade_short_code: 'G5' }],
});

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderPage() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <ChatbotListPage />
    </MemoryRouter>,
  );
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ChatbotListPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    // Reset Zustand store to initial state before each test
    useChatbotStore.setState({ chatbots: [], isLoading: false, error: null });
    mockDelete.mockResolvedValue({});
    mockClone.mockResolvedValue({ data: makeBot({ id: 'bot-3', name: 'Math Tutor (Clone)' }) });
  });

  // ── Loading ─────────────────────────────────────────────────────────────────

  it('shows loading spinner while fetch is pending', () => {
    mockList.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument();
  });

  // ── Page header ─────────────────────────────────────────────────────────────

  it('renders "AI Tutors" heading', async () => {
    mockList.mockResolvedValue({ data: [] });
    renderPage();
    expect(await screen.findByRole('heading', { level: 1, name: /ai tutors/i })).toBeInTheDocument();
  });

  it('renders subtitle text', async () => {
    mockList.mockResolvedValue({ data: [] });
    renderPage();
    expect(
      await screen.findByText(/create and manage ai-powered tutors/i),
    ).toBeInTheDocument();
  });

  // ── Error state ─────────────────────────────────────────────────────────────

  it('shows error message when fetch fails', async () => {
    mockList.mockRejectedValue(new Error('Network error'));
    renderPage();
    expect(await screen.findByText('Network error')).toBeInTheDocument();
  });

  // ── Chatbot grid ────────────────────────────────────────────────────────────

  it('renders ChatbotCard stubs for each chatbot', async () => {
    mockList.mockResolvedValue({ data: [bot1, bot2] });
    renderPage();
    expect(await screen.findByTestId('chatbot-card-bot-1')).toBeInTheDocument();
    expect(screen.getByTestId('chatbot-card-bot-2')).toBeInTheDocument();
    expect(screen.getByText('Math Tutor')).toBeInTheDocument();
    expect(screen.getByText('Science Tutor')).toBeInTheDocument();
  });

  // ── Empty state ─────────────────────────────────────────────────────────────

  it('shows "No tutors yet" empty state when list is empty', async () => {
    mockList.mockResolvedValue({ data: [] });
    renderPage();
    expect(await screen.findByText('No tutors yet')).toBeInTheDocument();
  });

  it('shows "Create Tutor" button in empty state', async () => {
    mockList.mockResolvedValue({ data: [] });
    renderPage();
    expect(await screen.findByRole('button', { name: /create tutor/i })).toBeInTheDocument();
  });

  it('"Create Tutor" button navigates to /teacher/chatbots/new', async () => {
    const user = userEvent.setup();
    mockList.mockResolvedValue({ data: [] });
    renderPage();
    await user.click(await screen.findByRole('button', { name: /create tutor/i }));
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/chatbots/new');
  });

  // ── New Tutor button ────────────────────────────────────────────────────────

  it('"New Tutor" header button navigates to /teacher/chatbots/new', async () => {
    const user = userEvent.setup();
    mockList.mockResolvedValue({ data: [bot1] });
    renderPage();
    await screen.findByTestId('chatbot-card-bot-1');
    await user.click(screen.getByRole('button', { name: /new tutor/i }));
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/chatbots/new');
  });

  // ── Search filtering ────────────────────────────────────────────────────────

  it('search input filters chatbots by name', async () => {
    const user = userEvent.setup();
    mockList.mockResolvedValue({ data: [bot1, bot2] });
    renderPage();
    await screen.findByTestId('chatbot-card-bot-1');
    await user.type(screen.getByPlaceholderText(/search tutors/i), 'Science');
    expect(screen.getByTestId('chatbot-card-bot-2')).toBeInTheDocument();
    expect(screen.queryByTestId('chatbot-card-bot-1')).not.toBeInTheDocument();
  });

  it('shows "No tutors match your filters" when search has no results', async () => {
    const user = userEvent.setup();
    mockList.mockResolvedValue({ data: [bot1] });
    renderPage();
    await screen.findByTestId('chatbot-card-bot-1');
    await user.type(screen.getByPlaceholderText(/search tutors/i), 'zzznomatch');
    expect(await screen.findByText('No tutors match your filters')).toBeInTheDocument();
  });

  // ── Section filter ──────────────────────────────────────────────────────────

  it('shows section filter dropdown when chatbots have sections', async () => {
    mockList.mockResolvedValue({ data: [bot2] });
    renderPage();
    await screen.findByTestId('chatbot-card-bot-2');
    // Section filter select should show "All Sections" + the section option
    expect(screen.getByRole('option', { name: /all sections/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'G5-A' })).toBeInTheDocument();
  });

  it('does not show section filter when no chatbot has sections', async () => {
    mockList.mockResolvedValue({ data: [bot1] }); // bot1 has no sections
    renderPage();
    await screen.findByTestId('chatbot-card-bot-1');
    expect(screen.queryByRole('option', { name: /all sections/i })).not.toBeInTheDocument();
  });

  // ── Delete flow ─────────────────────────────────────────────────────────────

  it('opens ConfirmDialog when Delete is triggered', async () => {
    const user = userEvent.setup();
    mockList.mockResolvedValue({ data: [bot1] });
    renderPage();
    await screen.findByTestId('chatbot-card-bot-1');
    await user.click(screen.getByRole('button', { name: /delete/i }));
    expect(screen.getByTestId('confirm-dialog')).toBeInTheDocument();
    expect(screen.getByText('Delete Tutor')).toBeInTheDocument();
  });

  it('calls chatbotApi.delete and removes chatbot on confirm', async () => {
    const user = userEvent.setup();
    mockList.mockResolvedValue({ data: [bot1] });
    renderPage();
    await screen.findByTestId('chatbot-card-bot-1');
    await user.click(screen.getByRole('button', { name: /delete/i }));
    await user.click(screen.getByRole('button', { name: /confirm/i }));
    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith('bot-1');
    });
    // Card should be removed from DOM
    await waitFor(() => {
      expect(screen.queryByTestId('chatbot-card-bot-1')).not.toBeInTheDocument();
    });
  });

  it('dismisses ConfirmDialog on cancel without calling delete', async () => {
    const user = userEvent.setup();
    mockList.mockResolvedValue({ data: [bot1] });
    renderPage();
    await screen.findByTestId('chatbot-card-bot-1');
    await user.click(screen.getByRole('button', { name: /delete/i }));
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(mockDelete).not.toHaveBeenCalled();
    expect(screen.queryByTestId('confirm-dialog')).not.toBeInTheDocument();
  });

  // ── Clone flow ──────────────────────────────────────────────────────────────

  it('calls chatbotApi.clone and adds cloned chatbot on Clone click', async () => {
    const user = userEvent.setup();
    mockList.mockResolvedValue({ data: [bot1] });
    renderPage();
    await screen.findByTestId('chatbot-card-bot-1');
    await user.click(screen.getByRole('button', { name: /clone/i }));
    await waitFor(() => {
      expect(mockClone).toHaveBeenCalledWith('bot-1');
    });
    await waitFor(() => {
      expect(screen.getByTestId('chatbot-card-bot-3')).toBeInTheDocument();
    });
  });

  it('shows success toast after successful clone', async () => {
    const user = userEvent.setup();
    mockList.mockResolvedValue({ data: [bot1] });
    renderPage();
    await screen.findByTestId('chatbot-card-bot-1');
    await user.click(screen.getByRole('button', { name: /clone/i }));
    await waitFor(() => {
      expect(mockToast.success).toHaveBeenCalledWith('Cloned', expect.stringContaining('cloned successfully'));
    });
  });
});
