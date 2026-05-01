// src/pages/teacher/ChatbotBuilderPage.test.tsx
//
// FE-068: Tests for the Teacher Chatbot / AI Tutor Builder page.
// Covers: create mode (heading, name input, welcome textarea, sources placeholder,
//         validation, Save→create API, navigate after create, Cancel/Back),
//         edit mode (loading state, Edit heading, name hydration, Save→update API),
//         section picker renders when sections available.
//
// Mocking strategy:
//   - chatbotApi (mySections, detail, create, update) via
//     vi.mock('../../services/openmaicService')
//   - GuardrailConfig / KnowledgeUploader / ChatbotChat → stubs
//   - useToast via vi.mock('../../components/common')
//   - useNavigate via importOriginal spread
//   - usePageTitle stubbed
//
// Route: create mode = /teacher/chatbots/new (no :id param)
//         edit mode   = /teacher/chatbots/:id

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ChatbotBuilderPage } from './ChatbotBuilderPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();
const mockToast = {
  success: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
  info: vi.fn(),
  showToast: vi.fn(),
};

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('../../services/openmaicService', () => ({
  maicApi: {
    listClassrooms: vi.fn(),
    deleteClassroom: vi.fn(),
    updateClassroom: vi.fn(),
  },
  chatbotApi: {
    mySections: vi.fn(),
    detail: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
  },
}));

vi.mock('../../components/maic/GuardrailConfig', () => ({
  GuardrailConfig: () => <div data-testid="guardrail-config" />,
}));

vi.mock('../../components/maic/KnowledgeUploader', () => ({
  KnowledgeUploader: ({ chatbotId }: { chatbotId: string }) => (
    <div data-testid={`knowledge-uploader-${chatbotId}`} />
  ),
}));

vi.mock('../../components/maic/ChatbotChat', () => ({
  ChatbotChat: () => <div data-testid="chatbot-chat" />,
}));

vi.mock('../../components/common', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('../../components/common')>();
  return { ...actual, useToast: () => mockToast };
});

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { chatbotApi } from '../../services/openmaicService';

const mockDetail = chatbotApi.detail as ReturnType<typeof vi.fn>;
const mockCreate = chatbotApi.create as ReturnType<typeof vi.fn>;
const mockUpdate = chatbotApi.update as ReturnType<typeof vi.fn>;
const mockMySections = chatbotApi.mySections as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderCreate() {
  return render(
    <MemoryRouter initialEntries={['/teacher/chatbots/new']}>
      <Routes>
        <Route path="/teacher/chatbots/new" element={<ChatbotBuilderPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function renderEdit(id = 'bot-1') {
  return render(
    <MemoryRouter initialEntries={[`/teacher/chatbots/${id}`]}>
      <Routes>
        <Route path="/teacher/chatbots/:id" element={<ChatbotBuilderPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeChatbot(overrides: Record<string, unknown> = {}) {
  return {
    id: 'bot-1',
    name: 'Physics Study Buddy',
    avatar_url: '',
    persona_preset: 'study_buddy',
    persona_description: '',
    custom_rules: 'Focus on exam prep.',
    block_off_topic: true,
    welcome_message: 'Hi! Ready to learn physics?',
    is_active: true,
    knowledge_count: 3,
    conversation_count: 12,
    sections: [],
    created_at: '2024-03-01T00:00:00Z',
    updated_at: '2024-03-01T00:00:00Z',
    ...overrides,
  };
}

function makeSection() {
  return {
    id: 'sec-1',
    name: 'Section A',
    grade_name: 'Grade 10',
    grade_short_code: 'G10',
    academic_year: '2024-25',
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ChatbotBuilderPage — create mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockMySections.mockResolvedValue({ data: [] });
    mockCreate.mockResolvedValue({ data: { ...makeChatbot(), id: 'new-bot-42' } });
    mockUpdate.mockResolvedValue({ data: makeChatbot() });
  });

  it('renders "Create Tutor" heading in create mode', () => {
    renderCreate();
    expect(
      screen.getByRole('heading', { level: 1, name: /create tutor/i }),
    ).toBeInTheDocument();
  });

  it('renders Tutor Name input with placeholder', () => {
    renderCreate();
    expect(
      screen.getByPlaceholderText(/physics study buddy/i),
    ).toBeInTheDocument();
  });

  it('renders Welcome Message textarea', () => {
    renderCreate();
    expect(
      screen.getByPlaceholderText(/the first message students see/i),
    ).toBeInTheDocument();
  });

  it('shows "Save the tutor first" placeholder when no chatbotId', () => {
    renderCreate();
    expect(
      screen.getByText(/save the tutor first to start adding sources/i),
    ).toBeInTheDocument();
  });

  it('does not show Test Chat button before first save', () => {
    renderCreate();
    expect(
      screen.queryByRole('button', { name: /test chat/i }),
    ).not.toBeInTheDocument();
  });

  it('shows validation error and does not call create when name empty', async () => {
    const user = userEvent.setup();
    renderCreate();
    await user.click(screen.getByRole('button', { name: /save tutor/i }));
    expect(mockToast.error).toHaveBeenCalledWith('Validation', 'Please enter a tutor name.');
    expect(mockCreate).not.toHaveBeenCalled();
  });

  it('calls chatbotApi.create with trimmed name on save', async () => {
    const user = userEvent.setup();
    renderCreate();
    await user.type(
      screen.getByPlaceholderText(/physics study buddy/i),
      'Physics Study Buddy',
    );
    await user.click(screen.getByRole('button', { name: /save tutor/i }));
    await waitFor(() => expect(mockCreate).toHaveBeenCalledTimes(1));
    const payload = mockCreate.mock.calls[0][0];
    expect(payload.name).toBe('Physics Study Buddy');
  });

  it('navigates to edit route after successful create', async () => {
    const user = userEvent.setup();
    renderCreate();
    await user.type(
      screen.getByPlaceholderText(/physics study buddy/i),
      'My Tutor',
    );
    await user.click(screen.getByRole('button', { name: /save tutor/i }));
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith(
        '/teacher/chatbots/new-bot-42',
        { replace: true },
      ),
    );
  });

  it('Back to Tutors navigates to /teacher/chatbots', async () => {
    const user = userEvent.setup();
    renderCreate();
    await user.click(screen.getByRole('button', { name: /back to tutors/i }));
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/chatbots');
  });

  it('Cancel button navigates to /teacher/chatbots', async () => {
    const user = userEvent.setup();
    renderCreate();
    await user.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/chatbots');
  });

  it('renders section picker when sections are available', async () => {
    mockMySections.mockResolvedValue({ data: [makeSection()] });
    renderCreate();
    // The section button shows grade_short_code-name
    expect(await screen.findByRole('button', { name: 'G10-Section A' })).toBeInTheDocument();
    // Grade header
    expect(screen.getByText('Grade 10')).toBeInTheDocument();
  });

  it('shows warning when no sections selected and sections are available', async () => {
    mockMySections.mockResolvedValue({ data: [makeSection()] });
    renderCreate();
    expect(
      await screen.findByText(/no sections selected/i),
    ).toBeInTheDocument();
  });
});

describe('ChatbotBuilderPage — edit mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockMySections.mockResolvedValue({ data: [] });
    mockDetail.mockResolvedValue({ data: makeChatbot() });
    mockUpdate.mockResolvedValue({ data: makeChatbot() });
  });

  it('shows loading spinner while chatbot details load', () => {
    mockDetail.mockReturnValue(new Promise(() => {}));
    renderEdit();
    expect(screen.getByRole('status', { name: /loading/i })).toBeInTheDocument();
  });

  it('renders "Edit Tutor" heading after chatbot loads', async () => {
    renderEdit();
    expect(
      await screen.findByRole('heading', { level: 1, name: /edit tutor/i }),
    ).toBeInTheDocument();
  });

  it('hydrates name input with chatbot name', async () => {
    renderEdit();
    await screen.findByRole('heading', { level: 1, name: /edit tutor/i });
    const input = screen.getByPlaceholderText(
      /physics study buddy/i,
    ) as HTMLInputElement;
    expect(input.value).toBe('Physics Study Buddy');
  });

  it('hydrates welcome message textarea', async () => {
    renderEdit();
    await screen.findByRole('heading', { level: 1, name: /edit tutor/i });
    const textarea = screen.getByPlaceholderText(
      /the first message students see/i,
    ) as HTMLTextAreaElement;
    expect(textarea.value).toBe('Hi! Ready to learn physics?');
  });

  it('shows KnowledgeUploader (chatbotId known in edit mode)', async () => {
    renderEdit('bot-1');
    await screen.findByRole('heading', { level: 1, name: /edit tutor/i });
    expect(screen.getByTestId('knowledge-uploader-bot-1')).toBeInTheDocument();
  });

  it('shows Test Chat button in edit mode (chatbotId is known)', async () => {
    renderEdit();
    await screen.findByRole('heading', { level: 1, name: /edit tutor/i });
    expect(screen.getByRole('button', { name: /test chat/i })).toBeInTheDocument();
  });

  it('calls chatbotApi.update (not create) on Save', async () => {
    const user = userEvent.setup();
    renderEdit();
    await screen.findByRole('heading', { level: 1, name: /edit tutor/i });
    await user.click(screen.getByRole('button', { name: /save tutor/i }));
    await waitFor(() => expect(mockUpdate).toHaveBeenCalledWith('bot-1', expect.objectContaining({ name: 'Physics Study Buddy' })));
    expect(mockCreate).not.toHaveBeenCalled();
  });
});
