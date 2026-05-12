// src/components/maic/ChatPanel.test.tsx
//
// FE-027 — Focused tests for the clear-chat confirm path in ChatPanel.
//
// Coverage goals:
//   1. "Clear chat" button is hidden when there are no messages.
//   2. "Clear chat" button appears when there are messages.
//   3. Clicking "Clear chat" opens the ConfirmDialog (does NOT immediately clear).
//   4. Clicking "Keep messages" (Cancel) closes the dialog; messages are preserved.
//   5. Clicking "Clear chat" (Confirm) wipes the store, sessionStorage, and IndexedDB.
//   6. An in-flight stream is aborted before the messages are wiped.

import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ChatPanel } from './ChatPanel';
import { useMAICStageStore } from '../../stores/maicStageStore';
import { useAuthStore } from '../../stores/authStore';
import type { MAICChatMessage } from '../../types/maic';

// ─── Module mocks ─────────────────────────────────────────────────────────────

// Prevent IndexedDB calls from blowing up in happy-dom.
vi.mock('../../lib/maicDb', () => ({
  updateClassroomChat: vi.fn().mockResolvedValue(undefined),
}));

// Spy on session-persistence so we can assert the clear payload.
vi.mock('../../lib/maicChatSession', () => ({
  hydrateChatFromSession: vi.fn().mockReturnValue([]),
  persistChatToSession: vi.fn(),
  serializeChatHistoryForBackend: vi.fn().mockReturnValue([]),
}));

// Prevent real SSE requests.
vi.mock('../../lib/maicSSE', () => ({
  streamMAIC: vi.fn().mockResolvedValue(undefined),
}));

// Disable speech recognition — not relevant to clear-chat.
vi.mock('../../hooks/useSpeechInput', () => ({
  useSpeechInput: () => ({
    isSupported: false,
    listening: false,
    start: vi.fn(),
    stop: vi.fn(),
  }),
}));

// Suppress complex sub-components that are not under test.
vi.mock('./StreamMarkdown', () => ({
  StreamMarkdown: ({ content }: { content: string }) =>
    React.createElement('span', { 'data-testid': 'stream-md' }, content),
}));

vi.mock('./PromptInput', () => ({
  PromptInput: ({ placeholder, onSubmit }: { placeholder?: string; onSubmit?: (value: string) => void }) =>
    React.createElement('div', null,
      React.createElement('input', {
        'data-testid': 'prompt-input',
        placeholder,
        readOnly: true,
      }),
      React.createElement('button', {
        'data-testid': 'prompt-submit',
        type: 'button',
        onClick: () => onSubmit?.('Hello tutor'),
      }, 'Send test'),
    ),
}));

vi.mock('./ConversationContainer', () => ({
  ConversationContainer: ({ children, className }: { children: React.ReactNode; className?: string }) =>
    React.createElement('div', { 'data-testid': 'conv-container', className }, children),
}));

vi.mock('./AgentAvatar', () => ({
  AgentAvatar: () => React.createElement('div', { 'data-testid': 'agent-avatar' }),
}));

vi.mock('./ai-elements/ChainOfThought', () => ({
  ChainOfThought: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', null, children),
  ChainOfThoughtTrigger: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', null, children),
  ChainOfThoughtContent: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', null, children),
  ChainOfThoughtStep: ({ children }: { children: React.ReactNode }) =>
    React.createElement('div', null, children),
}));

vi.mock('./ai-elements/CodeBlock', () => ({
  CodeBlock: ({ code }: { code: string }) =>
    React.createElement('pre', null, code),
}));

// ─── Helpers ──────────────────────────────────────────────────────────────────

import { updateClassroomChat } from '../../lib/maicDb';
import { persistChatToSession } from '../../lib/maicChatSession';
import { streamMAIC } from '../../lib/maicSSE';

const CLASSROOM_ID = 'classroom-test-1';

function makeMessages(count = 2): MAICChatMessage[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `msg-${i}`,
    role: i % 2 === 0 ? 'user' : 'assistant',
    content: `Message ${i}`,
    timestamp: Date.now() - (count - i) * 1000,
  }));
}

function renderChatPanel(extraProps: Partial<React.ComponentProps<typeof ChatPanel>> = {}) {
  return render(
    React.createElement(ChatPanel, {
      role: 'teacher',
      classroomId: CLASSROOM_ID,
      ...extraProps,
    }),
  );
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ChatPanel — clear-chat confirm path', () => {
  beforeEach(() => {
    // Ensure a valid access token so the panel isn't in "disabled" state.
    useAuthStore.setState({ accessToken: 'test-token' });
    // Start each test with an empty chat so we control state precisely.
    useMAICStageStore.setState({ chatMessages: [], agents: [], scenes: [] });
    // Reset persistence mocks.
    vi.mocked(persistChatToSession).mockClear();
    vi.mocked(updateClassroomChat).mockClear();
    vi.mocked(streamMAIC).mockReset();
    vi.mocked(streamMAIC).mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does NOT render the "Clear chat" button when there are no messages', () => {
    renderChatPanel();
    expect(screen.queryByRole('button', { name: /clear chat/i })).not.toBeInTheDocument();
  });

  it('renders the "Clear chat" button when messages are present', () => {
    useMAICStageStore.setState({ chatMessages: makeMessages(3) });
    renderChatPanel();
    expect(screen.getByRole('button', { name: /clear chat/i })).toBeInTheDocument();
  });

  it('opens the ConfirmDialog without clearing messages when "Clear chat" is clicked', async () => {
    useMAICStageStore.setState({ chatMessages: makeMessages(2) });
    renderChatPanel();

    // Wait for mount effects to settle, then reset call counts for the
    // persistence mocks so we only assert on calls caused by the button click.
    await waitFor(() => screen.getByRole('button', { name: /clear chat/i }));
    vi.mocked(persistChatToSession).mockClear();
    vi.mocked(updateClassroomChat).mockClear();

    fireEvent.click(screen.getByRole('button', { name: /clear chat/i }));

    // Dialog title should now be visible
    await waitFor(() => {
      expect(screen.getByText('Clear all chat messages?')).toBeInTheDocument();
    });

    // Messages must NOT have been wiped yet
    expect(useMAICStageStore.getState().chatMessages).toHaveLength(2);
    expect(persistChatToSession).not.toHaveBeenCalled();
    expect(updateClassroomChat).not.toHaveBeenCalled();
  });

  it('closes the dialog and preserves messages when "Keep messages" is clicked', async () => {
    useMAICStageStore.setState({ chatMessages: makeMessages(2) });
    renderChatPanel();

    // Wait for mount effects to settle
    await waitFor(() => screen.getByRole('button', { name: /clear chat/i }));
    vi.mocked(persistChatToSession).mockClear();
    vi.mocked(updateClassroomChat).mockClear();

    // Open dialog
    fireEvent.click(screen.getByRole('button', { name: /clear chat/i }));
    await waitFor(() => screen.getByText('Clear all chat messages?'));

    // Click cancel
    fireEvent.click(screen.getByRole('button', { name: /keep messages/i }));

    // Dialog should be gone
    await waitFor(() => {
      expect(screen.queryByText('Clear all chat messages?')).not.toBeInTheDocument();
    });

    // Messages still intact
    expect(useMAICStageStore.getState().chatMessages).toHaveLength(2);
    // Neither persistence path should have been called after the button settled
    expect(persistChatToSession).not.toHaveBeenCalled();
    expect(updateClassroomChat).not.toHaveBeenCalled();
  });

  it('clears store, sessionStorage, and IndexedDB when the confirm button is clicked', async () => {
    useMAICStageStore.setState({ chatMessages: makeMessages(3) });
    const { getByText } = renderChatPanel();

    // Wait for mount effects to settle, then reset so we only catch the clear call
    await waitFor(() => screen.getByRole('button', { name: /clear chat/i }));
    vi.mocked(persistChatToSession).mockClear();
    vi.mocked(updateClassroomChat).mockClear();

    // Open dialog (toolbar button)
    fireEvent.click(screen.getByRole('button', { name: /clear chat/i }));
    await waitFor(() => screen.getByText('Clear all chat messages?'));

    // The ConfirmDialog renders a button whose visible text is the confirmLabel.
    // Use getByText to scope to the dialog confirm button specifically —
    // the toolbar button uses aria-label, not visible text in the button itself.
    fireEvent.click(getByText('Clear chat', { selector: 'button' }));

    // Store must be empty
    await waitFor(() => {
      expect(useMAICStageStore.getState().chatMessages).toHaveLength(0);
    });

    // sessionStorage persistence called with empty array
    expect(persistChatToSession).toHaveBeenCalledWith(CLASSROOM_ID, []);

    // IndexedDB record wiped
    expect(updateClassroomChat).toHaveBeenCalledWith(CLASSROOM_ID, []);
  });

  it('"Clear chat" button disappears from the toolbar after messages are wiped', async () => {
    useMAICStageStore.setState({ chatMessages: makeMessages(2) });
    const { getByText } = renderChatPanel();

    await waitFor(() => screen.getByRole('button', { name: /clear chat/i }));
    fireEvent.click(screen.getByRole('button', { name: /clear chat/i }));
    await waitFor(() => screen.getByText('Clear all chat messages?'));
    // Click the dialog confirm button (visible text "Clear chat")
    fireEvent.click(getByText('Clear chat', { selector: 'button' }));

    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /clear chat/i })).not.toBeInTheDocument();
    });
  });

  it('"Clear chat" button is not rendered and no side-effects fire when the store is already empty', () => {
    // Guard: when there are no messages, the toolbar button is hidden entirely —
    // there is no way to invoke the clear path, so no side-effects should occur.
    useMAICStageStore.setState({ chatMessages: [] });
    renderChatPanel();

    // Button not rendered (same assertion as the first test, but verifies the
    // guard holds even after previous tests may have mutated store state).
    expect(screen.queryByRole('button', { name: /clear chat/i })).not.toBeInTheDocument();
    // No side-effects
    expect(persistChatToSession).not.toHaveBeenCalled();
    expect(updateClassroomChat).not.toHaveBeenCalled();
  });

  it('resumes interrupted playback when the chat stream errors before onDone', async () => {
    const onPlaybackInterrupt = vi.fn();
    const onPlaybackResume = vi.fn();
    vi.mocked(streamMAIC).mockImplementation(async (opts: any) => {
      opts.onError(new Error('token expired'));
    });

    renderChatPanel({ onPlaybackInterrupt, onPlaybackResume });

    fireEvent.click(screen.getByTestId('prompt-submit'));

    await waitFor(() => {
      expect(onPlaybackInterrupt).toHaveBeenCalledWith('Hello tutor');
      expect(onPlaybackResume).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByText(/Couldn't reach the tutor: token expired/i)).toBeInTheDocument();
  });
});
