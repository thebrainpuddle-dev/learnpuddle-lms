// src/pages/teacher/MAICLibraryPage.test.tsx
//
// FE-066: Tests for the Teacher AI Classroom Library page.
// Covers: loading spinner, empty state, classroom grid (title, status badge,
//         description, scene count), navigation (New Classroom, card click),
//         status filter select options, search input, delete via ConfirmDialog,
//         section assignment modal opening.
//
// Mocking strategy:
//   - maicApi (listClassrooms, deleteClassroom, updateClassroom) and
//     chatbotApi (mySections) via vi.mock('../../services/openmaicService')
//   - ConfirmDialog → stub with Confirm/Cancel buttons
//   - useNavigate via importOriginal spread
//   - usePageTitle stubbed

import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MAICLibraryPage } from './MAICLibraryPage';

// ── Module mocks ──────────────────────────────────────────────────────────────

const mockNavigate = vi.fn();

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
  },
}));

vi.mock('../../components/common/ConfirmDialog', () => ({
  ConfirmDialog: ({
    isOpen,
    onConfirm,
    onClose,
    title,
    message,
  }: {
    isOpen: boolean;
    onConfirm: () => void;
    onClose: () => void;
    title: string;
    message: string;
  }) =>
    isOpen ? (
      <div data-testid="confirm-dialog">
        <p>{title}</p>
        <p>{message}</p>
        <button onClick={onConfirm}>Confirm</button>
        <button onClick={onClose}>Cancel</button>
      </div>
    ) : null,
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// ── Typed mock helpers ────────────────────────────────────────────────────────

import { maicApi, chatbotApi } from '../../services/openmaicService';

const mockListClassrooms = maicApi.listClassrooms as ReturnType<typeof vi.fn>;
const mockDeleteClassroom = maicApi.deleteClassroom as ReturnType<typeof vi.fn>;
const mockMySections = chatbotApi.mySections as ReturnType<typeof vi.fn>;

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
}

function renderPage() {
  return render(
    <QueryClientProvider client={makeClient()}>
      <MemoryRouter>
        <MAICLibraryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeClassroom(overrides: Record<string, unknown> = {}) {
  return {
    id: 'cls-1',
    title: 'Photosynthesis Fundamentals',
    description: 'An interactive lesson on photosynthesis.',
    topic: 'Biology',
    status: 'READY',
    is_public: false,
    scene_count: 8,
    estimated_minutes: 25,
    course_id: null,
    assigned_sections: [],
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
  };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('MAICLibraryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: empty list
    mockListClassrooms.mockResolvedValue({ data: [] });
    mockMySections.mockResolvedValue({ data: [] });
    mockDeleteClassroom.mockResolvedValue({});
  });

  // ── Loading state ────────────────────────────────────────────────────────────

  it('shows loading spinner while classrooms load', () => {
    mockListClassrooms.mockReturnValue(new Promise(() => {}));
    renderPage();
    // Spinner has animate-spin class
    const spinner = document.querySelector('.animate-spin');
    expect(spinner).not.toBeNull();
  });

  // ── Page header ──────────────────────────────────────────────────────────────

  it('renders "AI Classroom" heading', async () => {
    renderPage();
    expect(
      await screen.findByRole('heading', { level: 1, name: /ai classroom/i }),
    ).toBeInTheDocument();
  });

  // ── Empty state ──────────────────────────────────────────────────────────────

  it('shows "No classrooms yet" when list is empty', async () => {
    renderPage();
    expect(await screen.findByText('No classrooms yet')).toBeInTheDocument();
  });

  it('shows "Create your first AI Classroom" subtitle in empty state', async () => {
    renderPage();
    expect(
      await screen.findByText(/create your first ai classroom/i),
    ).toBeInTheDocument();
  });

  // ── Classroom grid ───────────────────────────────────────────────────────────

  it('renders classroom title', async () => {
    mockListClassrooms.mockResolvedValue({
      data: [makeClassroom()],
    });
    renderPage();
    expect(await screen.findByText('Photosynthesis Fundamentals')).toBeInTheDocument();
  });

  it('renders classroom status badge', async () => {
    mockListClassrooms.mockResolvedValue({
      data: [makeClassroom({ status: 'READY' })],
    });
    renderPage();
    expect(await screen.findByText('READY')).toBeInTheDocument();
  });

  it('renders classroom description', async () => {
    mockListClassrooms.mockResolvedValue({
      data: [makeClassroom()],
    });
    renderPage();
    expect(
      await screen.findByText('An interactive lesson on photosynthesis.'),
    ).toBeInTheDocument();
  });

  it('renders scene count and estimated minutes', async () => {
    mockListClassrooms.mockResolvedValue({
      data: [makeClassroom({ scene_count: 8, estimated_minutes: 25 })],
    });
    renderPage();
    await screen.findByText('Photosynthesis Fundamentals');
    expect(screen.getByText('8 scenes')).toBeInTheDocument();
    expect(screen.getByText('25 min')).toBeInTheDocument();
  });

  it('renders DRAFT status badge in correct style', async () => {
    mockListClassrooms.mockResolvedValue({
      data: [makeClassroom({ status: 'DRAFT' })],
    });
    renderPage();
    expect(await screen.findByText('DRAFT')).toBeInTheDocument();
  });

  // ── Navigation ───────────────────────────────────────────────────────────────

  it('New Classroom button navigates to /teacher/ai-classroom/new', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    // There are 2 "New Classroom" buttons: in header and in empty state
    const buttons = screen.getAllByRole('button', { name: /new classroom/i });
    await user.click(buttons[0]);
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/ai-classroom/new');
  });

  it('clicking classroom card navigates to /teacher/ai-classroom/:id', async () => {
    const user = userEvent.setup();
    mockListClassrooms.mockResolvedValue({
      data: [makeClassroom({ id: 'cls-42' })],
    });
    renderPage();
    const cardTitle = await screen.findByText('Photosynthesis Fundamentals');
    await user.click(cardTitle);
    expect(mockNavigate).toHaveBeenCalledWith('/teacher/ai-classroom/cls-42');
  });

  // ── Filters ──────────────────────────────────────────────────────────────────

  it('status filter select has All, Draft, Ready, Archived options', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(screen.getByRole('option', { name: 'All' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Draft' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Ready' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Archived' })).toBeInTheDocument();
  });

  it('search input renders with placeholder text', async () => {
    renderPage();
    await screen.findByRole('heading', { level: 1 });
    expect(
      screen.getByPlaceholderText('Search classrooms...'),
    ).toBeInTheDocument();
  });

  // ── Delete ───────────────────────────────────────────────────────────────────

  it('clicking trash icon opens ConfirmDialog', async () => {
    const user = userEvent.setup();
    mockListClassrooms.mockResolvedValue({
      data: [makeClassroom()],
    });
    renderPage();
    await screen.findByText('Photosynthesis Fundamentals');
    const deleteBtn = screen.getByTitle('Delete classroom');
    await user.click(deleteBtn);
    expect(await screen.findByTestId('confirm-dialog')).toBeInTheDocument();
    expect(screen.getByText('Delete Classroom')).toBeInTheDocument();
  });

  it('confirming delete calls deleteClassroom with classroom id', async () => {
    const user = userEvent.setup();
    mockListClassrooms.mockResolvedValue({
      data: [makeClassroom({ id: 'cls-1' })],
    });
    renderPage();
    await screen.findByText('Photosynthesis Fundamentals');
    await user.click(screen.getByTitle('Delete classroom'));
    await screen.findByTestId('confirm-dialog');
    await user.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() =>
      expect(mockDeleteClassroom).toHaveBeenCalledWith('cls-1'),
    );
  });

  // ── Section Assignment Modal ─────────────────────────────────────────────────

  it('clicking Assign opens section assignment modal', async () => {
    const user = userEvent.setup();
    mockListClassrooms.mockResolvedValue({
      data: [makeClassroom()],
    });
    mockMySections.mockResolvedValue({ data: [makeSection()] });
    renderPage();
    await screen.findByText('Photosynthesis Fundamentals');
    await user.click(screen.getByTitle('Assign sections'));
    expect(
      await screen.findByRole('heading', { level: 3, name: /assign sections/i }),
    ).toBeInTheDocument();
  });
});
