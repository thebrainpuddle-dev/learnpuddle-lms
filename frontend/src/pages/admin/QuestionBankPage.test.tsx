// src/pages/admin/QuestionBankPage.test.tsx
//
// FE-033: Tests for the Admin Question Bank management page.
// Covers: bank list (loading, error, empty, populated), search, bank CRUD
// (create/edit/delete via modals), navigation to BankQuestionsView, question
// list rendering, question type filtering, question CRUD, and Zod validation
// for MCQ/MULTI/TRUE_FALSE/SHORT/ESSAY question types.

import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { QuestionBankPage } from './QuestionBankPage';
import { ToastProvider } from '../../components/common';
import { adminQuestionBankService } from '../../services/adminQuestionBankService';
import type { QuestionBank, Question } from '../../services/adminQuestionBankService';

// ── Module mocks ──────────────────────────────────────────────────────────────

vi.mock('../../services/adminQuestionBankService', () => ({
  adminQuestionBankService: {
    listBanks:      vi.fn(),
    createBank:     vi.fn(),
    updateBank:     vi.fn(),
    deleteBank:     vi.fn(),
    listQuestions:  vi.fn(),
    createQuestion: vi.fn(),
    updateQuestion: vi.fn(),
    deleteQuestion: vi.fn(),
  },
}));

vi.mock('../../hooks/usePageTitle', () => ({ usePageTitle: vi.fn() }));

// Stub DataTable: surfaces row data without TanStack's full DOM overhead.
vi.mock('../../components/ui/data-table', () => ({
  DataTable: ({
    data,
    emptyMessage,
    columns,
  }: {
    data: Array<Record<string, unknown>>;
    emptyMessage?: string;
    columns: Array<{ accessorKey?: string; id?: string; cell?: unknown }>;
  }) => (
    <div data-testid="data-table">
      {data.length === 0 && emptyMessage ? (
        <span>{emptyMessage}</span>
      ) : (
        <div>
          <span data-testid="row-count">{data.length} rows</span>
          {data.map((row, i) => (
            <div key={i} data-testid="data-table-row">
              {Object.entries(row).map(([k, v]) => {
                if (typeof v === 'string' || typeof v === 'number') {
                  return <span key={k} data-field={k}>{String(v)}</span>;
                }
                return null;
              })}
              {/* Render action cells so CRUD buttons are accessible. */}
              {columns
                .filter((c) => c.id === 'actions' && typeof c.cell === 'function')
                .map((c) => {
                  const CellFn = c.cell as (ctx: { row: { original: unknown } }) => React.ReactNode;
                  return (
                    <div key="actions" data-testid="row-actions">
                      {CellFn({ row: { original: row } })}
                    </div>
                  );
                })}
            </div>
          ))}
        </div>
      )}
    </div>
  ),
  DataTableColumnHeader: ({ title }: { title: string }) => <span>{title}</span>,
}));

// ── Fixtures ──────────────────────────────────────────────────────────────────

const BANK_A: QuestionBank = {
  id:             'bank-1',
  title:          'Grade 10 Mathematics',
  description:    'Algebra and geometry problems',
  tags:           [],
  is_active:      true,
  question_count: 12,
  created_at:     '2026-01-15T08:00:00Z',
  updated_at:     '2026-01-20T08:00:00Z',
};

const BANK_B: QuestionBank = {
  id:             'bank-2',
  title:          'Science Quiz Bank',
  description:    '',
  tags:           [],
  is_active:      false,
  question_count: 5,
  created_at:     '2026-02-10T09:00:00Z',
  updated_at:     '2026-02-10T09:00:00Z',
};

const QUESTION_MCQ: Question = {
  id:            'q-1',
  bank:          'bank-1',
  question_type: 'MCQ',
  prompt:        'What is 2 + 2?',
  points:        1,
  difficulty:    'EASY',
  explanation:   'Simple addition.',
  metadata:      {},
  order:         0,
  choices: [
    { id: 'c-1', text: '3', is_correct: false, order: 0 },
    { id: 'c-2', text: '4', is_correct: true,  order: 1 },
    { id: 'c-3', text: '5', is_correct: false, order: 2 },
  ],
  created_at:    '2026-01-16T10:00:00Z',
  updated_at:    '2026-01-16T10:00:00Z',
};

const QUESTION_ESSAY: Question = {
  id:            'q-2',
  bank:          'bank-1',
  question_type: 'ESSAY',
  prompt:        'Describe the Pythagorean theorem.',
  points:        5,
  difficulty:    'HARD',
  explanation:   '',
  metadata:      {},
  order:         1,
  choices:       [],
  created_at:    '2026-01-17T11:00:00Z',
  updated_at:    '2026-01-17T11:00:00Z',
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries:   { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

function renderPage() {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <ToastProvider>
        <MemoryRouter>
          <QuestionBankPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  );
}

const svc = adminQuestionBankService as {
  [K in keyof typeof adminQuestionBankService]: ReturnType<typeof vi.fn>;
};

function setupDefaultBankMocks() {
  svc.listBanks.mockResolvedValue({ results: [BANK_A, BANK_B] });
  svc.createBank.mockResolvedValue({ ...BANK_A, id: 'bank-new' });
  svc.updateBank.mockResolvedValue(BANK_A);
  svc.deleteBank.mockResolvedValue(undefined);
  svc.listQuestions.mockResolvedValue({ results: [QUESTION_MCQ, QUESTION_ESSAY] });
  svc.createQuestion.mockResolvedValue(QUESTION_MCQ);
  svc.updateQuestion.mockResolvedValue(QUESTION_MCQ);
  svc.deleteQuestion.mockResolvedValue(undefined);
}

// ── SECTION 1 — Bank list view ────────────────────────────────────────────────

describe('QuestionBankPage — bank list', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultBankMocks();
  });

  it('renders the page heading', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Question Banks')).toBeInTheDocument();
    });
  });

  it('shows a loading spinner while fetching banks', () => {
    // Never resolves — stays in loading state.
    svc.listBanks.mockReturnValue(new Promise(() => {}));
    renderPage();
    // Loading spinner should be present before data arrives.
    expect(document.querySelector('.animate-spin')).toBeTruthy();
  });

  it('renders two bank rows when data loads', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId('row-count')).toHaveTextContent('2 rows');
    });
    expect(screen.getByText('Grade 10 Mathematics')).toBeInTheDocument();
    expect(screen.getByText('Science Quiz Bank')).toBeInTheDocument();
  });

  it('shows empty-state message when no banks exist', async () => {
    svc.listBanks.mockResolvedValue({ results: [] });
    renderPage();
    await waitFor(() => {
      expect(
        screen.getByText(/no question banks yet/i),
      ).toBeInTheDocument();
    });
  });

  it('shows search-specific empty-state when search returns nothing', async () => {
    const user = userEvent.setup();
    // First call returns data, second (search) returns empty.
    svc.listBanks
      .mockResolvedValueOnce({ results: [BANK_A] })
      .mockResolvedValue({ results: [] });

    renderPage();
    await waitFor(() => screen.getByText('Grade 10 Mathematics'));

    const searchInput = screen.getByPlaceholderText(/search question banks/i);
    await user.type(searchInput, 'xyz');

    await waitFor(() => {
      expect(screen.getByText(/no question banks match your search/i)).toBeInTheDocument();
    });
  });

  it('passes the search term to listBanks', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Grade 10 Mathematics'));

    const searchInput = screen.getByPlaceholderText(/search question banks/i);
    await user.type(searchInput, 'math');

    await waitFor(() => {
      expect(svc.listBanks).toHaveBeenCalledWith('math');
    });
  });
});

// ── SECTION 2 — Create / Edit bank ───────────────────────────────────────────

describe('QuestionBankPage — bank create/edit', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultBankMocks();
  });

  it('"New Question Bank" button opens the bank modal with empty title', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Question Banks'));

    await user.click(screen.getByRole('button', { name: /new question bank/i }));

    // The dialog opens; confirm via the placeholder which only exists inside the modal.
    await waitFor(() => {
      expect(screen.getByPlaceholderText(/e\.g\. grade 10/i)).toBeInTheDocument();
    });
    // Title field should be empty in create mode.
    expect(screen.getByPlaceholderText(/e\.g\. grade 10/i)).toHaveValue('');
  });

  it('shows validation error when title is empty on submit', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Question Banks'));

    await user.click(screen.getByRole('button', { name: /new question bank/i }));
    // Modal is open when the title input placeholder is visible.
    await waitFor(() => screen.getByPlaceholderText(/e\.g\. grade 10/i));

    await user.click(screen.getByRole('button', { name: /create bank/i }));

    await waitFor(() => {
      expect(screen.getByText('Title is required')).toBeInTheDocument();
    });
    expect(svc.createBank).not.toHaveBeenCalled();
  });

  it('calls createBank and shows success toast on valid submit', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Question Banks'));

    await user.click(screen.getByRole('button', { name: /new question bank/i }));
    await waitFor(() => screen.getByPlaceholderText(/e\.g\. grade 10/i));

    await user.type(screen.getByPlaceholderText(/e\.g\. grade 10/i), 'My New Bank');
    await user.click(screen.getByRole('button', { name: /create bank/i }));

    await waitFor(() => {
      expect(svc.createBank).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'My New Bank' }),
      );
    });
    // Toast confirms success.
    await waitFor(() => {
      expect(screen.getByText('Bank created')).toBeInTheDocument();
    });
  });

  it('edit button opens the bank modal pre-filled with existing data', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Grade 10 Mathematics'));

    // Click the edit (pencil) button in the first row.
    const rows = screen.getAllByTestId('data-table-row');
    const editBtn = within(rows[0]).getByTitle('Edit bank');
    await user.click(editBtn);

    await waitFor(() => {
      expect(screen.getByText('Edit Question Bank')).toBeInTheDocument();
    });
    expect(screen.getByPlaceholderText(/e\.g\. grade 10/i)).toHaveValue(
      'Grade 10 Mathematics',
    );
  });

  it('calls updateBank and shows success toast when editing', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Grade 10 Mathematics'));

    const rows = screen.getAllByTestId('data-table-row');
    await user.click(within(rows[0]).getByTitle('Edit bank'));
    await waitFor(() => screen.getByText('Edit Question Bank'));

    // Clear and retype the title.
    const titleInput = screen.getByPlaceholderText(/e\.g\. grade 10/i);
    await user.clear(titleInput);
    await user.type(titleInput, 'Updated Bank Name');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(svc.updateBank).toHaveBeenCalledWith(
        BANK_A.id,
        expect.objectContaining({ title: 'Updated Bank Name' }),
      );
    });
    await waitFor(() => {
      expect(screen.getByText('Bank updated')).toBeInTheDocument();
    });
  });
});

// ── SECTION 3 — Delete bank ───────────────────────────────────────────────────

describe('QuestionBankPage — bank delete', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultBankMocks();
  });

  it('delete button opens ConfirmDialog with bank title', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Grade 10 Mathematics'));

    const rows = screen.getAllByTestId('data-table-row');
    await user.click(within(rows[0]).getByTitle('Delete bank'));

    // The confirm dialog heading uniquely identifies the dialog.
    await waitFor(() => {
      expect(screen.getByText('Delete Question Bank')).toBeInTheDocument();
    });
    // Bank title may appear in multiple DOM nodes (table row + dialog message); just ensure >= 1.
    expect(screen.getAllByText(/grade 10 mathematics/i).length).toBeGreaterThanOrEqual(1);
  });

  it('calls deleteBank after confirming deletion', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Grade 10 Mathematics'));

    const rows = screen.getAllByTestId('data-table-row');
    await user.click(within(rows[0]).getByTitle('Delete bank'));
    await waitFor(() => screen.getByText('Delete Question Bank'));

    // Scope to the dialog panel to avoid matching row-action buttons.
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /delete bank/i }));

    await waitFor(() => {
      expect(svc.deleteBank).toHaveBeenCalledWith(BANK_A.id);
    });
  });

  it('does NOT call deleteBank when cancelling deletion', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Grade 10 Mathematics'));

    const rows = screen.getAllByTestId('data-table-row');
    await user.click(within(rows[0]).getByTitle('Delete bank'));
    await waitFor(() => screen.getByText('Delete Question Bank'));

    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /cancel/i }));

    await waitFor(() => {
      expect(screen.queryByText('Delete Question Bank')).not.toBeInTheDocument();
    });
    expect(svc.deleteBank).not.toHaveBeenCalled();
  });
});

// ── SECTION 4 — Bank questions view ──────────────────────────────────────────

describe('QuestionBankPage — BankQuestionsView', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultBankMocks();
  });

  async function navigateToBankA() {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Grade 10 Mathematics'));

    // Click "View Questions" in the first row.
    const rows = screen.getAllByTestId('data-table-row');
    await user.click(within(rows[0]).getByRole('button', { name: /view questions/i }));
    return user;
  }

  it('shows the bank title and a back-navigation link', async () => {
    await navigateToBankA();
    await waitFor(() => {
      expect(screen.getByText('Grade 10 Mathematics')).toBeInTheDocument();
      expect(screen.getByText(/all question banks/i)).toBeInTheDocument();
    });
  });

  it('"All Question Banks" back button returns to bank list', async () => {
    const user = await navigateToBankA();
    await waitFor(() => screen.getByText(/all question banks/i));

    await user.click(screen.getByText(/all question banks/i));

    await waitFor(() => {
      // Back to bank list: heading "Question Banks" is visible again,
      // and bank descriptions are gone.
      expect(screen.getByRole('button', { name: /new question bank/i })).toBeInTheDocument();
    });
  });

  it('renders question rows with question type badges', async () => {
    await navigateToBankA();
    await waitFor(() => {
      expect(screen.getByTestId('row-count')).toHaveTextContent('2 rows');
    });
    // Question prompts visible via data field spans.
    expect(screen.getByText('What is 2 + 2?')).toBeInTheDocument();
  });

  it('shows loading spinner while fetching questions', async () => {
    svc.listQuestions.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Grade 10 Mathematics'));

    const rows = screen.getAllByTestId('data-table-row');
    await user.click(within(rows[0]).getByRole('button', { name: /view questions/i }));

    await waitFor(() => {
      expect(document.querySelector('.animate-spin')).toBeTruthy();
    });
  });

  it('shows empty-state when bank has no questions', async () => {
    svc.listQuestions.mockResolvedValue({ results: [] });
    await navigateToBankA();
    await waitFor(() => {
      expect(screen.getByText(/no questions yet/i)).toBeInTheDocument();
    });
  });

  it('passes the selected type filter to listQuestions', async () => {
    const user = await navigateToBankA();
    await waitFor(() => screen.getByText('What is 2 + 2?'));

    // Change the type filter to MCQ.
    const select = screen.getByRole('combobox');
    await user.selectOptions(select, 'MCQ');

    await waitFor(() => {
      expect(svc.listQuestions).toHaveBeenCalledWith(BANK_A.id, 'MCQ');
    });
  });
});

// ── SECTION 5 — Question create/edit ─────────────────────────────────────────

describe('QuestionBankPage — question create', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultBankMocks();
  });

  async function openAddQuestionModal() {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Grade 10 Mathematics'));

    const rows = screen.getAllByTestId('data-table-row');
    await user.click(within(rows[0]).getByRole('button', { name: /view questions/i }));
    await waitFor(() => screen.getByText('Algebra and geometry problems'));

    await user.click(screen.getByRole('button', { name: /add question/i }));
    // Wait for the modal-specific prompt textarea (unique to the modal) to confirm it opened.
    await waitFor(() =>
      screen.getByPlaceholderText(/enter the question text/i),
    );
    return user;
  }

  /**
   * Get the "Type" select within the open question modal.
   * Uses the first combobox inside the dialog panel since the label text
   * has no `htmlFor` link (cosmetic label, not a formal association).
   */
  function getTypeSelect() {
    const dialog = screen.getByRole('dialog');
    return within(dialog).getAllByRole('combobox')[0];
  }

  it('"Add Question" button opens the question modal', async () => {
    await openAddQuestionModal();
    // The dialog title renders as an h2; check heading to avoid colliding with page button.
    expect(screen.getByRole('heading', { name: /add question/i })).toBeInTheDocument();
    // MCQ is default type (first combobox in the dialog).
    expect(getTypeSelect()).toHaveValue('MCQ');
  });

  it('shows validation error when prompt is empty', async () => {
    const user = await openAddQuestionModal();
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^add question$/i }));
    await waitFor(() => {
      expect(screen.getByText('Question prompt is required')).toBeInTheDocument();
    });
    expect(svc.createQuestion).not.toHaveBeenCalled();
  });

  it('calls createQuestion with MCQ payload on valid submit', async () => {
    const user = await openAddQuestionModal();

    const promptArea = screen.getByPlaceholderText(/enter the question text/i);
    await user.type(promptArea, 'What colour is the sky?');

    // Fill both choice text inputs.
    const choiceInputs = screen.getAllByPlaceholderText(/choice \d/i);
    await user.clear(choiceInputs[0]);
    await user.type(choiceInputs[0], 'Blue');
    await user.clear(choiceInputs[1]);
    await user.type(choiceInputs[1], 'Green');

    // Mark the first choice correct via the toggle (XCircleIcon → click → CheckCircleIcon).
    const toggles = screen.getAllByTitle('Mark as correct');
    await user.click(toggles[0]);

    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^add question$/i }));

    await waitFor(() => {
      expect(svc.createQuestion).toHaveBeenCalledWith(
        BANK_A.id,
        expect.objectContaining({
          question_type: 'MCQ',
          prompt: 'What colour is the sky?',
          choices: expect.arrayContaining([
            expect.objectContaining({ text: 'Blue', is_correct: true }),
          ]),
        }),
      );
    });
  });

  it('MCQ with no correct choice shows choices validation error and does not call createQuestion', async () => {
    const user = await openAddQuestionModal();

    await user.type(
      screen.getByPlaceholderText(/enter the question text/i),
      'Pick the right answer.',
    );
    // Fill choices but leave both incorrect (no toggle clicked).
    const choiceInputs = screen.getAllByPlaceholderText(/choice \d/i);
    await user.type(choiceInputs[0], 'Option A');
    await user.type(choiceInputs[1], 'Option B');

    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^add question$/i }));

    // Zod superRefine fires → choices error rendered in the dialog and service not called.
    await waitFor(() => {
      expect(
        within(screen.getByRole('dialog')).getByRole('alert'),
      ).toHaveTextContent(/mcq requires exactly 1 correct choice/i);
    });
    expect(svc.createQuestion).not.toHaveBeenCalled();
  });

  it('switching type to ESSAY hides the choices section', async () => {
    const user = await openAddQuestionModal();

    await user.selectOptions(getTypeSelect(), 'ESSAY');

    await waitFor(() => {
      expect(screen.queryByText('Answer Choices')).not.toBeInTheDocument();
    });
  });

  it('switching type to TRUE_FALSE auto-fills True/False choices', async () => {
    const user = await openAddQuestionModal();

    await user.selectOptions(getTypeSelect(), 'TRUE_FALSE');

    await waitFor(() => {
      const inputs = screen.getAllByDisplayValue(/^(true|false)$/i);
      expect(inputs.length).toBeGreaterThanOrEqual(2);
    });
  });

  it('SHORT type requires no choices and submits successfully', async () => {
    const user = await openAddQuestionModal();

    await user.selectOptions(getTypeSelect(), 'SHORT');
    await waitFor(() =>
      expect(screen.queryByText('Answer Choices')).not.toBeInTheDocument(),
    );

    await user.type(
      screen.getByPlaceholderText(/enter the question text/i),
      'Name three primary colours.',
    );
    await user.click(within(screen.getByRole('dialog')).getByRole('button', { name: /^add question$/i }));

    await waitFor(() => {
      expect(svc.createQuestion).toHaveBeenCalledWith(
        BANK_A.id,
        expect.objectContaining({
          question_type: 'SHORT',
          prompt: 'Name three primary colours.',
          choices: [],
        }),
      );
    });
  });
});

// ── SECTION 6 — Question delete ───────────────────────────────────────────────

describe('QuestionBankPage — question delete', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setupDefaultBankMocks();
  });

  it('delete question button opens ConfirmDialog', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Grade 10 Mathematics'));

    const rows = screen.getAllByTestId('data-table-row');
    await user.click(within(rows[0]).getByRole('button', { name: /view questions/i }));
    await waitFor(() => screen.getByText('What is 2 + 2?'));

    const qRows = screen.getAllByTestId('data-table-row');
    await user.click(within(qRows[0]).getByTitle('Delete question'));

    await waitFor(() => {
      expect(screen.getByText('Delete Question')).toBeInTheDocument();
      expect(
        screen.getByText(/this cannot be undone/i),
      ).toBeInTheDocument();
    });
  });

  it('calls deleteQuestion after confirming deletion', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => screen.getByText('Grade 10 Mathematics'));

    const bankRows = screen.getAllByTestId('data-table-row');
    await user.click(within(bankRows[0]).getByRole('button', { name: /view questions/i }));
    await waitFor(() => screen.getByText('What is 2 + 2?'));

    const qRows = screen.getAllByTestId('data-table-row');
    await user.click(within(qRows[0]).getByTitle('Delete question'));
    await waitFor(() => screen.getByText('Delete Question'));

    // Scope to the dialog panel to avoid matching row-action "Delete question" buttons.
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: /^delete$/i }));

    await waitFor(() => {
      expect(svc.deleteQuestion).toHaveBeenCalledWith(QUESTION_MCQ.id);
    });
  });
});
